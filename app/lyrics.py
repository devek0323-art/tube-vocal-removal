# 곡 제목으로 가사를 조회해 저장하는 모듈 — 해외(싱크) 우선, 국내 가사 사이트 폴백
import html as _html
import re
import unicodedata
import urllib.parse
import urllib.request

from app.version import APP_VERSION

UA = f"Tube-Vocal-Removal/{APP_VERSION} (lyrics)"
_BROWSER_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
               "(KHTML, like Gecko) Chrome/120.0 Safari/537.36")
LRCLIB_BASE = "https://lrclib.net/api"
_KR_SEARCH = "https://music.bugs.co.kr/search/integrated?q="
_KR_TRACK = "https://music.bugs.co.kr/track/"
_TIMEOUT = 15

# 유튜브 제목에서 흔히 붙는 군더더기
_NOISE = re.compile(
    r"(?i)\b(official|m/?v|music\s*video|lyric[s]?|가사|audio|visualizer|"
    r"hd|4k|feat\.?|ft\.?|prod\.?)\b.*",
)
_BRACKETS = re.compile(r"[\[\(（【][^\]\)）】]*[\]\)）】]")
_SEPARATORS = (" - ", " – ", " — ", " _ ", "_")

# 제목 뒤에 붙는 채널명·영문 병기·시리즈명·공연장을 자르는 지점
_CUTS = (" - ", " – ", " — ", "｜", "|", " / ", "／", "～", "~", " @ ", "@")
# 곡 제목 끝에 붙는 부가 정보 낱말 (연도, No.2, full.ver 등)
_META_WORD = re.compile(
    r"^(19|20)\d{2}년?$"
    r"|^(no|vol|pt|part|ver|version|disc|track)\d*$"
    r"|^(full|official|live|inst|mr|audio|video|mv|lyric|lyrics|가사|반주|음원|자막)$"
    r"|^\d{1,3}$",
    re.I,
)
_YEAR = re.compile(r"^(19|20)\d{2}년?$")
_QUOTES = "'\"‘’“”「」『』《》"
_TRIM = " -–—_·|｜~,." + _QUOTES


def clean_title(raw: str) -> str:
    """괄호 묶음·MV·가사 등 군더더기를 제거한다."""
    text = unicodedata.normalize("NFC", str(raw))
    text = _BRACKETS.sub(" ", text)
    text = _NOISE.sub(" ", text)
    text = re.sub(r"\s+", " ", text).strip(" -–—_·|")
    return text


def split_artist_title(cleaned: str):
    """'가수 - 제목' 형태면 (가수, 제목)으로, 아니면 (None, 제목)으로 나눈다."""
    for sep in _SEPARATORS:
        if sep in cleaned:
            artist, title = cleaned.split(sep, 1)
            return artist.strip(), title.strip()
    return None, cleaned.strip()


def _is_meta(token: str) -> bool:
    """'full.ver', 'No.2'처럼 점으로 이어진 것도 부가 정보로 본다."""
    parts = [p for p in re.split(r"[.\s]+", token.strip(_TRIM)) if p]
    return bool(parts) and all(_META_WORD.match(p) for p in parts)


def title_candidates(title: str, limit: int = 4):
    """검색어 후보를 긴 것부터 짧은 것 순으로 만든다.

    업로더가 제목 뒤에 붙이는 말은 형태가 제각각이라 정규식 하나로 잡기 어렵다.
    대신 뒤에서부터 잘라낸 후보를 차례로 시도해 진짜 곡 제목에 도달한다.
    """
    found = []

    def add(text):
        text = re.sub(f"[{re.escape(_QUOTES)}]", " ", text)
        text = re.sub(r"\s+", " ", text).strip(_TRIM)
        if len(text) >= 2 and text not in found:
            found.append(text)

    add(title)
    if not found:
        return []
    base = found[0]
    # 구분자 앞부분만 남긴다
    for cut in _CUTS:
        if cut in base:
            add(base.split(cut)[0])
    # 연도가 중간에 있으면 그 앞까지만 남긴다
    for candidate in list(found):
        tokens = candidate.split()
        for index, token in enumerate(tokens):
            if index > 0 and _YEAR.match(token.strip(_TRIM)):
                add(" ".join(tokens[:index]))
                break
    # 뒤에서부터 부가 정보 토큰을 떼어낸다
    for candidate in list(found):
        tokens = candidate.split()
        while len(tokens) > 1 and _is_meta(tokens[-1]):
            tokens.pop()
            add(" ".join(tokens))
    return found[:limit]


def _norm(text: str) -> str:
    """비교용 정규화 — NFC, 소문자, 공백·기호 제거."""
    text = unicodedata.normalize("NFC", str(text)).lower()
    return re.sub(r"[^0-9a-z가-힣]", "", text)


def _similar(a: str, b: str) -> bool:
    """한쪽이 다른 쪽에 포함되면 같은 곡으로 본다 (짧은 쪽 길이 2 이상)."""
    na, nb = _norm(a), _norm(b)
    if not na or not nb:
        return False
    short, long = (na, nb) if len(na) <= len(nb) else (nb, na)
    return len(short) >= 2 and short in long


def _same_title(a: str, b: str) -> bool:
    """제목만으로 검색할 때 다른 곡의 부분 일치를 막는다."""
    return bool(_norm(a)) and _norm(a) == _norm(b)


def _lyrics_support_short_english_title(title: str, text: str) -> bool:
    """가수 정보가 없는 짧은 영문 제목은 가사 본문으로 한 번 더 검증한다.

    ``Drowning`` 검색이 아티스트 ``Drowning Pool``의 ``Bodies``로 튀는 것처럼
    검색 엔진이 제목과 가수명을 섞는 경우를 차단한다. 여러 단어/한글 제목은
    제목이 가사에 그대로 나오지 않는 곡이 많으므로 이 보수적 검사를 적용하지 않는다.
    """
    title = unicodedata.normalize("NFC", str(title)).strip()
    if not re.fullmatch(r"[A-Za-z][A-Za-z'-]{3,}", title):
        return True
    return re.search(rf"(?i)(?<![A-Za-z]){re.escape(title)}(?![A-Za-z])", text or "") is not None


def _http_get(url: str) -> bytes:
    """단순 GET — 테스트에서 이 함수를 대체(monkeypatch)한다."""
    ua = _BROWSER_UA if "bugs.co.kr" in url else UA
    request = urllib.request.Request(url, headers={"User-Agent": ua})
    with urllib.request.urlopen(request, timeout=_TIMEOUT) as response:
        return response.read()


def _strip_timestamps(synced: str) -> str:
    """LRC 싱크 가사의 [mm:ss.xx] 태그를 제거해 순수 텍스트로 만든다."""
    lines = []
    for line in synced.splitlines():
        text = re.sub(r"\[\d+:\d+(?:\.\d+)?\]", "", line).strip()
        if text:
            lines.append(text)
    return "\n".join(lines)


def _fetch_lrclib(artist, title, duration):
    """LRCLIB 조회. 싱크 가사(.lrc 원본)를 우선, 없으면 순수 텍스트를 반환."""
    import json

    # 1) 정확 매칭 — 가수+제목(+길이)
    if artist:
        params = {"artist_name": artist, "track_name": title}
        if duration:
            params["duration"] = int(duration)
        try:
            data = json.loads(_http_get(f"{LRCLIB_BASE}/get?{urllib.parse.urlencode(params)}"))
            hit = _lrclib_pick([data], artist, title, duration, strict=False)
            if hit:
                return hit
        except Exception:
            pass

    # 2) 검색 폴백 — 가수+제목, 이어서 제목만
    queries = []
    if artist:
        queries.append({"artist_name": artist, "track_name": title})
    queries.append({"q": title})
    for params in queries:
        try:
            rows = json.loads(_http_get(f"{LRCLIB_BASE}/search?{urllib.parse.urlencode(params)}"))
        except Exception:
            continue
        hit = _lrclib_pick(rows, artist, title, duration, strict=True)
        if hit:
            return hit
    return None


def _lrclib_pick(rows, artist, title, duration, strict):
    """검색 결과에서 제목/가수/길이로 검증해 가장 알맞은 가사를 고른다."""
    if isinstance(rows, dict):
        rows = [rows]
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        if strict:
            track_name = row.get("trackName", "")
            if (not _similar(title, track_name) if artist else not _same_title(title, track_name)):
                continue
            if artist and not _similar(artist, row.get("artistName", "")):
                continue
            if duration and row.get("duration") and abs(row["duration"] - duration) > 4:
                continue
        synced = row.get("syncedLyrics")
        plain = row.get("plainLyrics")
        if synced:
            return {"text": _strip_timestamps(synced), "synced": synced, "source": "LRCLIB"}
        if plain:
            return {"text": plain, "synced": None, "source": "LRCLIB"}
    return None


_KR_TRACK_ID = re.compile(r"/track/(\d+)")
_KR_TITLE = re.compile(r"<title>([^<]+)</title>")
_KR_LYRICS = re.compile(r"(?is)<xmp[^>]*>(.*?)</xmp>")


def _fetch_kr(artist, title):
    """국내 가사 사이트 폴백 — 제목으로 검색해 곡을 찾고 트랙 페이지에서 가사를 가져온다."""
    keyword = urllib.parse.quote(f"{artist} {title}" if artist else title)
    try:
        page = _http_get(f"{_KR_SEARCH}{keyword}").decode("utf-8", "ignore")
    except Exception:
        return None

    seen = []
    for track_id in _KR_TRACK_ID.findall(page):
        if track_id not in seen:
            seen.append(track_id)
        if len(seen) >= 10:
            break

    for track_id in seen:
        try:
            track = _http_get(f"{_KR_TRACK}{track_id}").decode("utf-8", "ignore")
        except Exception:
            continue
        head = _KR_TITLE.search(track)
        if head:
            # "제목/가수(영문) - 사이트" 형태에서 제목·가수를 검증한다.
            label = re.sub(r"\s*-\s*[^-/]+$", "", head.group(1)).strip()
            page_title, _, page_artist = label.partition("/")
            page_artist = re.sub(r"\(.*?\)", "", page_artist).strip()
            # 가수가 확인되지 않은 커버곡 검색에서는 부분 일치를 허용하면
            # Drowning -> Drowning Shadows 같은 동명이곡을 집을 수 있다.
            if (not _similar(title, page_title) if artist else not _same_title(title, page_title)):
                continue
            if artist and page_artist and not _similar(artist, page_artist):
                continue
        body = _KR_LYRICS.search(track)
        if not body:
            continue
        text = _html.unescape(body.group(1)).strip()
        lines = [ln.strip() for ln in text.splitlines()]
        clean_text = "\n".join(lines).strip("\n")
        if not artist and not _lyrics_support_short_english_title(title, clean_text):
            continue
        if sum(1 for ln in lines if ln) >= 4:
            return {"text": clean_text, "synced": None, "source": "web"}
    return None


def fetch_lyrics(title, duration=None, artist=None):
    """제목(+길이·가수)으로 가사를 조회한다. 못 찾으면 None.

    제목 뒤 군더더기를 잘라낸 후보를 차례로 시도한다. 가수를 붙인 검색이 먼저지만,
    제목에서 가수를 잘못 뽑았을 수 있으므로 가수 없이도 한 번 더 시도한다.
    """
    cleaned = clean_title(title)
    parsed_artist, parsed_title = split_artist_title(cleaned)
    artist = artist or parsed_artist
    for candidate in title_candidates(parsed_title or cleaned):
        for name in ([artist, None] if artist else [None]):
            found = _fetch_lrclib(name, candidate, duration) or _fetch_kr(name, candidate)
            if found:
                return found
    return None


def search_candidates(artist, track, limit=8):
    """가수·곡명으로 후보를 모아 돌려준다. 자동 조회가 실패했을 때 직접 고르는 용도다.

    fetch_lyrics는 길이·제목을 대조해 하나만 고르지만, 여기서는 거르지 않는다.
    이미 자동으로 못 찾은 상황이라 사람이 보고 판단하는 편이 낫다.
    """
    import json

    track = str(track or "").strip()
    artist = str(artist or "").strip()
    if not track and not artist:
        return []
    params = {"artist_name": artist, "track_name": track} if artist and track else {"q": track or artist}
    try:
        rows = json.loads(_http_get(f"{LRCLIB_BASE}/search?{urllib.parse.urlencode(params)}"))
    except Exception:
        return []
    found = []
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        synced, plain = row.get("syncedLyrics"), row.get("plainLyrics")
        if not (synced or plain):
            continue
        found.append({
            "track": row.get("trackName") or "",
            "artist": row.get("artistName") or "",
            "duration": int(row.get("duration") or 0),
            "hasSynced": bool(synced),
            "result": {"text": _strip_timestamps(synced) if synced else plain,
                       "synced": synced or None, "source": "LRCLIB"},
        })
        if len(found) >= limit:
            break
    return found


def save_lyrics(result, destination):
    """조회 결과를 텍스트(.txt) 파일로만 저장한다."""
    from pathlib import Path

    dest = Path(destination)
    dest.write_text(result["text"], encoding="utf-8")
    return dest
