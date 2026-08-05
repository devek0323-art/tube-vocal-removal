# 노래방 영상 만들기 — 가사 타이밍을 만들고 ASS 자막을 얹어 MP4로 굽는다
import hashlib
import os
import re
import shutil
import subprocess
import urllib.request
from pathlib import Path

from app.cover import FONT
from app.platform_support import IS_MACOS, IS_WINDOWS, hidden_process_kwargs

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


def _sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(4 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def ensure_model(name, models_dir, on_progress=None, should_cancel=None):
    """위스퍼 체크포인트를 받아 둔다. 이미 있으면 그대로 쓴다.

    whisper.load_model에 맡기면 안 된다. 그쪽 다운로드는 진행바를 stderr에 그리는데
    창 모드로 빌드한 exe에는 stderr가 없어서 받자마자 죽는다. 직접 받으면
    진행률도 알려줄 수 있다.
    """
    import whisper

    target = Path(models_dir) / f"{name}.pt"
    url = whisper._MODELS[name]
    expected = url.split("/")[-2]  # 내려받을 파일의 SHA-256이 주소에 박혀 있다.
    if target.is_file():
        # 있다고 믿으면 안 된다. 반쯤 받다 끊긴 파일이 남아 있으면 whisper가 스스로
        # 다시 받으려 들고, 그쪽 다운로드는 창 모드 exe에서 죽는다.
        if _sha256(target) == expected:
            return target
        target.unlink(missing_ok=True)
    target.parent.mkdir(parents=True, exist_ok=True)
    partial = target.with_name(target.name + ".part")
    digest = hashlib.sha256()
    received = 0
    try:
        with urllib.request.urlopen(url, timeout=60) as source, partial.open("wb") as output:
            total = int(source.info().get("Content-Length") or 0)
            while True:
                if should_cancel is not None and should_cancel():
                    raise RuntimeError("취소되었습니다.")
                chunk = source.read(1024 * 1024)
                if not chunk:
                    break
                output.write(chunk)
                digest.update(chunk)
                received += len(chunk)
                if on_progress is not None:
                    on_progress(received, total)
        if digest.hexdigest() != expected:
            raise RuntimeError("받은 파일이 손상되었습니다. 다시 시도해 주세요.")
        os.replace(partial, target)
    except BaseException:
        partial.unlink(missing_ok=True)
        raise
    return target


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


def _codecs(gpu):
    """쓸 인코더를 순서대로. 앞에서부터 시도하고 실패하면 다음으로 넘어간다.

    가속 인코더는 장치나 드라이버가 없으면 그 자리에서 실패한다. NVIDIA 전용
    nvenc를 맥에서 고르면 영상이 아예 안 나오므로 플랫폼을 보고 고른다.
    """
    software = ["-c:v", "libx264", "-preset", "veryfast", "-crf", "23"]
    if not gpu:
        return [software]
    if IS_WINDOWS:
        return [["-c:v", "h264_nvenc", "-preset", "p4", "-cq", "23"], software]
    if IS_MACOS:
        return [["-c:v", "h264_videotoolbox", "-b:v", "3M"], software]
    return [software]


def render(ffmpeg, audio, background, ass_path, destination, duration, gpu=False, on_proc=None):
    """정지 배경을 반복하며 자막과 반주를 얹어 MP4로 굽는다.

    자막 경로는 필터 문자열에 넣지 않고 작업 디렉터리를 옮겨 파일명만 넘긴다.
    ffmpeg 필터 문법에는 작은따옴표를 넣을 방법이 없어서, 제목에 따옴표가 있으면
    (`IU 'Through the Night'`) 경로를 어떻게 이스케이프해도 깨진다.
    """
    chain = "[0:v]null[v]"
    work = None
    if ass_path:
        work = Path(ass_path).parent
        # 글꼴도 같은 폴더에 둔다. fontsdir에도 경로를 넘기지 않기 위해서다.
        if not (work / FONT.name).is_file():
            shutil.copy2(FONT, work / FONT.name)
        chain = f"[0:v]subtitles={Path(ass_path).name}:fontsdir=.[v]"
    error = ""
    for codec in _codecs(gpu):
        command = [str(ffmpeg), "-hide_banner", "-nostats", "-y",
                   "-loop", "1", "-framerate", "24", "-t", f"{duration:.2f}", "-i", str(background),
                   "-i", str(audio), "-filter_complex", chain,
                   "-map", "[v]", "-map", "1:a", *codec, "-pix_fmt", "yuv420p",
                   "-c:a", "aac", "-b:a", "192k", "-shortest", str(Path(destination).resolve())]
        proc = subprocess.Popen(command, cwd=str(work) if work else None,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                **hidden_process_kwargs())
        if on_proc is not None:
            on_proc(proc)
        _, stderr = proc.communicate()
        if proc.returncode == 0 and Path(destination).is_file():
            return destination
        Path(destination).unlink(missing_ok=True)     # 만들다 만 파일을 남기지 않는다
        error = (stderr or b"").decode("utf-8", "replace").strip().splitlines()[-1:] or [""]
        error = error[0][:200]
    raise RuntimeError(f"노래방 영상을 만들지 못했습니다. ({error})")
