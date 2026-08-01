# 곡 제목으로 가사를 조회해 저장하는 모듈 — 해외(싱크) 우선, 국내 가사 사이트 폴백
import html as _html
import re
import unicodedata
import urllib.parse
import urllib.request

UA = "Tube-Vocal-Removal/2.03 (lyrics)"
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
            if not _similar(title, row.get("trackName", "")):
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
        if len(seen) >= 4:
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
            if not _similar(title, page_title):
                continue
            if artist and page_artist and not _similar(artist, page_artist):
                continue
        body = _KR_LYRICS.search(track)
        if not body:
            continue
        text = _html.unescape(body.group(1)).strip()
        lines = [ln.strip() for ln in text.splitlines()]
        if sum(1 for ln in lines if ln) >= 4:
            return {"text": "\n".join(lines).strip("\n"), "synced": None, "source": "web"}
    return None


def fetch_lyrics(title, duration=None, artist=None):
    """제목(+길이)으로 가사를 조회한다. 정제된 제목/가수를 우선 쓰고, 못 찾으면 None."""
    cleaned = clean_title(title)
    parsed_artist, parsed_title = split_artist_title(cleaned)
    artist = artist or parsed_artist
    title = parsed_title or cleaned
    return _fetch_lrclib(artist, title, duration) or _fetch_kr(artist, title)


def save_lyrics(result, destination):
    """조회 결과를 텍스트(.txt) 파일로만 저장한다."""
    from pathlib import Path

    dest = Path(destination)
    dest.write_text(result["text"], encoding="utf-8")
    return dest
