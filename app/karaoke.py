# 노래방 영상 만들기 — 가사 타이밍을 만들고 ASS 자막을 얹어 MP4로 굽는다
import re
import subprocess
from pathlib import Path

from app.cover import FONT
from app.platform_support import hidden_process_kwargs

_STAMP = re.compile(r"\[(\d+):(\d+(?:\.\d+)?)\]")


def parse_lrc(text):
    """LRC를 (시작초, 가사) 목록으로. 한 줄에 태그가 여러 개 붙는 경우도 처리한다."""
    lines = []
    for raw in str(text or "").splitlines():
        body = re.sub(r"\[[^\]]*\]", "", raw).strip()
        if not body:
            continue
        for minute, second in _STAMP.findall(raw):
            lines.append((int(minute) * 60 + float(second), body))
    lines.sort(key=lambda item: item[0])
    return lines


def whisper_segments(vocal_path, prompt, models_dir, use_gpu):
    """보컬 스템에서 타이밍을 뽑는다. 받아쓴 글자는 버리고 시각만 쓴다.

    MPS는 쓰지 않는다. torch MPS에서 일부 연산이 실패하거나 CPU로 떨어지는데
    맥 실기기로 확인할 방법이 없어 CPU로 간다.
    """
    import torch
    import whisper

    cuda = bool(use_gpu) and torch.cuda.is_available()
    name = "medium" if cuda else "small"
    model = whisper.load_model(name, device="cuda" if cuda else "cpu",
                               download_root=str(models_dir))
    result = model.transcribe(str(vocal_path), initial_prompt=(prompt or "")[:200],
                              condition_on_previous_text=False, fp16=cuda)
    return [{"start": s["start"], "end": s["end"], "text": s["text"]}
            for s in result["segments"] if str(s["text"]).strip()]


def whisper_model_name(use_gpu):
    """설치 확인·안내 문구에서 쓸 모델 이름."""
    try:
        import torch
        return "medium" if use_gpu and torch.cuda.is_available() else "small"
    except Exception:
        return "small"


def _ass_time(seconds):
    seconds = max(0.0, float(seconds))
    hours, rest = divmod(seconds, 3600)
    minutes, secs = divmod(rest, 60)
    return f"{int(hours)}:{int(minutes):02d}:{secs:05.2f}"


_HEAD = """[Script Info]
ScriptType: v4.00+
PlayResX: 1280
PlayResY: 720
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, OutlineColour, BackColour, Bold, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Now,Pretendard Variable,58,&H00FFFFFF,&H00181818,&H80000000,1,1,3,2,2,80,80,150,1
Style: Next,Pretendard Variable,34,&H00918C84,&H00181818,&H80000000,0,1,2,1,2,80,80,92,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""


def write_ass(lines, destination, duration):
    """현재 줄은 크게, 다음 줄은 흐리게 미리 보여주는 두 줄 자막."""
    rows = []
    for index, (start, text) in enumerate(lines):
        end = lines[index + 1][0] if index + 1 < len(lines) else duration
        end = min(end, duration)
        if end <= start:
            continue
        safe = str(text).replace("\n", " ").replace("{", "(").replace("}", ")")
        stamp = f"{_ass_time(start)},{_ass_time(end)}"
        rows.append(f"Dialogue: 0,{stamp},Now,,0,0,0,,{safe}")
        if index + 1 < len(lines):
            nxt = str(lines[index + 1][1]).replace("\n", " ").replace("{", "(").replace("}", ")")
            rows.append(f"Dialogue: 0,{stamp},Next,,0,0,0,,{nxt}")
    Path(destination).write_text(_HEAD + "\n".join(rows) + "\n", encoding="utf-8")
    return destination


def _escape(path):
    return str(path).replace("\\", "/").replace(":", r"\:")


def render(ffmpeg, audio, background, ass_path, destination, duration, gpu=False):
    """정지 배경을 반복하며 자막과 반주를 얹어 MP4로 굽는다."""
    codec = (["-c:v", "h264_nvenc", "-preset", "p4", "-cq", "23"] if gpu
             else ["-c:v", "libx264", "-preset", "veryfast", "-crf", "23"])
    chain = f"[0:v]subtitles='{_escape(ass_path)}':fontsdir='{_escape(FONT.parent)}'[v]" \
        if ass_path else "[0:v]null[v]"
    result = subprocess.run(
        [str(ffmpeg), "-hide_banner", "-nostats", "-y",
         "-loop", "1", "-framerate", "24", "-t", f"{duration:.2f}", "-i", str(background),
         "-i", str(audio), "-filter_complex", chain,
         "-map", "[v]", "-map", "1:a", *codec, "-pix_fmt", "yuv420p",
         "-c:a", "aac", "-b:a", "192k", "-shortest", str(destination)],
        capture_output=True, **hidden_process_kwargs(),
    )
    if result.returncode != 0 or not Path(destination).is_file():
        raise RuntimeError("노래방 영상을 만들지 못했습니다.")
    return destination
