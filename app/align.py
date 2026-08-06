# 확보한 가사 텍스트에 음성 인식이 뽑은 타이밍만 붙인다 (인식된 글자는 쓰지 않는다)
import re
from difflib import SequenceMatcher

_KEEP = re.compile(r"[^가-힣a-z0-9]")


def _norm(text: str) -> str:
    return _KEEP.sub("", str(text).lower())


def vocal_onset(vocal_path, floor_ratio: float = 0.06) -> float:
    """보컬 스템에서 노래가 실제로 시작하는 시각(초). 못 구하면 0."""
    import numpy as np
    import soundfile as sf

    try:
        data, rate = sf.read(str(vocal_path))
    except Exception:
        return 0.0
    mono = data.mean(1) if data.ndim > 1 else data
    width = max(rate // 2, 1)
    count = len(mono) // width
    if not count:
        return 0.0
    frames = np.sqrt((mono[:count * width].reshape(count, width) ** 2).mean(axis=1))
    loud = np.flatnonzero(frames > frames.max() * floor_ratio)
    return float(loud[0]) * 0.5 if len(loud) else 0.0


def drop_hallucinations(items, onset: float, lead: float = 1.0, key: str = "start"):
    """노래가 시작하기 전 세그먼트(또는 단어)를 버린다.

    가사를 initial_prompt로 넣으면 인식기가 0초에 그 문장을 그대로 뱉는 일이 있다.
    """
    return [item for item in items if float(item[key]) >= onset - lead]


def align_words(lyric_lines, words, onset=None):
    """가사 줄과 인식된 '단어'를 글자 단위로 맞춰 (시작초, 가사)를 만든다.

    세그먼트(30초 덩어리) 단위로 맞추면 한 덩어리가 여러 줄을 덮을 때 글자 수
    비율로 나눌 수밖에 없고, 그만큼 줄 경계가 실제 발음과 어긋난다. 단어 시각이
    있으면 그 줄의 첫 글자가 실제로 언제 발음됐는지 바로 읽을 수 있다.
    """
    lyrics = [line.strip() for line in lyric_lines if line.strip()]
    if not lyrics or not words:
        return []

    # 인식 결과를 글자 흐름으로 펴고, 글자마다 시각을 매단다.
    heard, times = [], []
    for word in words:
        text = _norm(word.get("word", ""))
        if not text:
            continue
        begin, finish = float(word["start"]), float(word["end"])
        step = max(finish - begin, 0.0) / len(text)
        for position, letter in enumerate(text):
            heard.append(letter)
            times.append(begin + step * position)
    if not heard:
        return []

    # 가사도 같은 방식으로 펴되 글자마다 몇 번째 줄인지 기억해 둔다.
    keys = [_norm(line) for line in lyrics]
    flat, owner = [], []
    for index, key in enumerate(keys):
        for letter in key:
            flat.append(letter)
            owner.append(index)
    if not flat:
        return []

    starts = {}
    matcher = SequenceMatcher(None, flat, heard, autojunk=False)
    for lyric_at, heard_at, size in matcher.get_matching_blocks():
        for step in range(size):
            line = owner[lyric_at + step]
            if line not in starts:
                starts[line] = times[heard_at + step]

    first = onset if onset is not None else times[0]
    return _fill_and_order(lyrics, keys, [starts.get(i) for i in range(len(lyrics))], first)


def settle(rough, exact, onset=None):
    """강제 정렬 결과를 받아들이되, 못 맞춘 줄은 대략 위치로 메운다.

    강제 정렬은 창 안쪽 줄에만 답을 준다. 가장자리로 밀려 답이 없는 줄은 앞뒤
    확정된 줄 사이에 끼워 넣는다.
    """
    lyrics = [text for _, text in rough]
    keys = [_norm(text) for text in lyrics]
    filled = [None if at is None else float(at) for at in exact]
    if not any(value is not None for value in filled):
        return rough
    # 첫 줄이 창 시작에 눌려 앞당겨지는 자리는 대략 위치를 그대로 쓴다.
    anchored = next(index for index, value in enumerate(filled) if value is not None)
    if anchored == 0 and len(filled) > 1 and filled[1] is not None:
        if filled[1] - filled[0] > 12.0:
            filled[0] = rough[0][0]
    # onset은 라이브 녹음에서 크게 틀리기도 한다. 확정된 줄보다 뒤면 믿지 않는다.
    anchor = min(v for v in filled if v is not None)
    first = min(onset, anchor) if onset is not None else anchor
    return _fill_and_order(lyrics, keys, filled, first)


def _fill_and_order(lyrics, keys, filled, first):
    """못 맞춘 줄을 앞뒤 기준점 사이에 끼우고, 순서와 최소 간격을 지킨다."""
    rows = len(lyrics)
    for index in range(rows):
        if filled[index] is not None:
            continue
        prev = next((k for k in reversed(range(index)) if filled[k] is not None), None)
        nxt = next((k for k in range(index + 1, rows) if filled[k] is not None), None)
        begin = filled[prev] if prev is not None else first
        run = [k for k in range(prev + 1 if prev is not None else 0,
                                nxt if nxt is not None else rows) if filled[k] is None]
        finish = filled[nxt] if nxt is not None else begin + 0.8 * len(run)
        weights = [max(len(keys[k]), 1) for k in run]
        total = sum(weights)
        span = max(finish - begin, 0.6 * len(run))
        offset = 0
        for k, weight in zip(run, weights):
            filled[k] = begin + span * (offset / total)
            offset += weight

    out = []
    last = None
    for index, line in enumerate(lyrics):
        start = max(filled[index], first)
        if last is not None:
            start = max(start, last + 0.35)     # 순식간에 스쳐 지나가지 않게
        out.append((start, line))
        last = start
    return out


def align(lyric_lines, segments, onset=None):
    """가사 줄과 인식 세그먼트를 순서를 지키며 짝지어 (시작초, 가사)를 만든다.

    인식기는 한 줄을 둘로 쪼개거나 두 줄을 합치므로 1:1로 보면 안 된다. 글자
    유사도를 점수로 두고 단조 정렬(DP)한 뒤, 한 세그먼트가 여러 줄을 덮으면 그
    구간 안에서 글자 수 비율로 나눠 넣는다.
    """
    lyrics = [line.strip() for line in lyric_lines if line.strip()]
    heard = [(float(s["start"]), float(s["end"]), _norm(s["text"]))
             for s in segments if _norm(s.get("text", ""))]
    if not lyrics or not heard:
        return []

    rows, cols = len(lyrics), len(heard)
    keys = [_norm(line) for line in lyrics]
    score = [[0.0] * (cols + 1) for _ in range(rows + 1)]
    back = [[None] * (cols + 1) for _ in range(rows + 1)]

    for i in range(1, rows + 1):
        for j in range(1, cols + 1):
            match = SequenceMatcher(None, keys[i - 1], heard[j - 1][2]).ratio()
            score[i][j], back[i][j] = max(
                (score[i - 1][j - 1] + match, "pair"),          # 한 줄 ↔ 한 세그먼트
                (score[i - 1][j] + match * 0.55, "up"),         # 한 세그먼트가 여러 줄을 덮음
                (score[i][j - 1], "left"),                      # 세그먼트가 남음(간주·군말)
            )

    owner = {}
    i, j = rows, cols
    while i > 0 and j > 0:
        move = back[i][j]
        if move == "left":
            j -= 1
            continue
        owner[i - 1] = j - 1
        i -= 1
        if move == "pair":
            j -= 1

    grouped = {}
    for index, seg in owner.items():
        grouped.setdefault(seg, []).append(index)
    starts = {}
    for seg, members in grouped.items():
        begin, finish, _ = heard[seg]
        members.sort()
        span = max(finish - begin, 0.4)
        weights = [max(len(keys[k]), 1) for k in members]
        total = sum(weights)
        offset = 0
        for k, weight in zip(members, weights):
            starts[k] = begin + span * (offset / total)
            offset += weight

    # 인식기가 놓친 줄은 앞뒤 기준점 사이에 끼워 넣는다. 앞줄에 이어 붙이면
    # 어긋남이 뒤로 계속 전파된다.
    first = onset if onset is not None else heard[0][0]
    return _fill_and_order(lyrics, keys, [starts.get(index) for index in range(rows)], first)
