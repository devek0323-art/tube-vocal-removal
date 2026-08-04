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


def drop_hallucinations(segments, onset: float, lead: float = 1.0):
    """노래가 시작하기 전 세그먼트를 버린다.

    가사를 initial_prompt로 넣으면 인식기가 0초에 그 문장을 그대로 뱉는 일이 있다.
    """
    return [s for s in segments if float(s["start"]) >= onset - lead]


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
    filled = [starts.get(index) for index in range(rows)]
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
