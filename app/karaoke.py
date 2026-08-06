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


_MODEL_CACHE = {}


def _load(models_dir, use_gpu):
    """모델을 한 번만 올린다. 받아쓰기와 강제 정렬이 같은 모델을 쓴다."""
    import torch
    import whisper

    cuda = bool(use_gpu) and torch.cuda.is_available()
    name, device = ("medium", "cuda") if cuda else ("small", "cpu")
    key = (name, device)
    if key not in _MODEL_CACHE:
        _MODEL_CACHE[key] = whisper.load_model(name, device=device,
                                               download_root=str(models_dir))
    return _MODEL_CACHE[key], cuda


def whisper_segments(vocal_path, prompt, models_dir, use_gpu):
    """보컬 스템에서 타이밍을 뽑는다. 받아쓴 글자는 버리고 시각만 쓴다.

    MPS는 쓰지 않는다. torch MPS에서 일부 연산이 실패하거나 CPU로 떨어지는데
    맥 실기기로 확인할 방법이 없어 CPU로 간다.
    """
    model, cuda = _load(models_dir, use_gpu)
    # word_timestamps — 단어별 시각까지 받는다. 세그먼트는 30초 덩어리라 줄 경계를
    # 잡기에는 너무 굵다. 단어가 있으면 그 줄이 실제로 언제 시작하는지 알 수 있다.
    result = model.transcribe(str(vocal_path), initial_prompt=(prompt or "")[:200],
                              condition_on_previous_text=False, fp16=cuda,
                              word_timestamps=True)
    segments, words = [], []
    for segment in result["segments"]:
        if str(segment["text"]).strip():
            segments.append({"start": segment["start"], "end": segment["end"],
                             "text": segment["text"]})
        for word in segment.get("words") or []:
            if str(word.get("word", "")).strip():
                words.append({"start": word["start"], "end": word["end"],
                              "word": word["word"]})
    return segments, words


def force_align(vocal_path, lyric_lines, rough_starts, models_dir, use_gpu):
    """가사를 정답으로 두고 오디오에서 위치만 찾는다 (강제 정렬).

    받아쓴 결과에 가사를 짝지으면 잘못 들은 곳에서 줄이 통째로 끌려간다. 여기서는
    가사 토큰을 그대로 넣고 모델은 그것이 언제 발음됐는지만 계산하므로 그 오류가
    구조적으로 생기지 않는다.

    위스퍼는 30초 창만 본다. 창을 20초씩 겹쳐 가며 훑고, 각 줄은 신뢰도가 가장
    높게 나온 창의 결과를 쓴다. 창의 첫 단어는 앞쪽 오디오를 혼자 떠안아 창
    시작으로 늘어나므로, 바로 앞 줄을 미끼로 함께 넣어 그 몫을 대신 받게 한다.
    """
    import torch
    import whisper
    from whisper.audio import N_FRAMES, SAMPLE_RATE, log_mel_spectrogram, pad_or_trim
    from whisper.timing import find_alignment

    lines = [line.strip() for line in lyric_lines if line.strip()]
    if not lines or len(rough_starts) != len(lines):
        return []
    model, _ = _load(models_dir, use_gpu)
    language = "ko" if re.search(r"[가-힣]", " ".join(lines)) else "en"
    tokenizer = whisper.tokenizer.get_tokenizer(model.is_multilingual, language=language,
                                                num_languages=model.num_languages)
    audio = whisper.load_audio(str(vocal_path))
    duration = len(audio) / SAMPLE_RATE

    best = [None] * len(lines)
    trust = [-1.0] * len(lines)
    window, step = 30.0, 20.0
    start = 0.0
    while start < duration:
        # 창 가장자리는 신뢰할 수 없으므로 안쪽에 들어오는 줄만 이 창에서 맞춘다.
        members = [i for i, at in enumerate(rough_starts)
                   if start + 0.5 <= at < start + window - 4.0]
        if members:
            lead = members[0] - 1 if members[0] > 0 else None
            group = ([lead] if lead is not None else []) + members
            tokens, owner = [], []
            for index in group:
                encoded = tokenizer.encode(" " + lines[index])
                tokens.extend(encoded)
                owner.extend([index] * len(encoded))
            begin = int(start * SAMPLE_RATE)
            chunk = pad_or_trim(audio[begin:begin + int(window * SAMPLE_RATE)],
                                int(window * SAMPLE_RATE))
            mel = log_mel_spectrogram(chunk, model.dims.n_mels).to(model.device)
            try:
                with torch.no_grad():
                    timings = find_alignment(model, tokenizer, tokens, mel, N_FRAMES)
            except Exception:
                timings = []
            cursor = 0
            seen = {}
            for word in timings:
                for _ in word.tokens:
                    if cursor < len(owner):
                        index = owner[cursor]
                        if index not in seen:
                            seen[index] = (start + float(word.start), float(word.probability))
                    cursor += 1
            for index, (at, score) in seen.items():
                if index != lead and score > trust[index]:
                    best[index], trust[index] = at, score
        start += step
    return best


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
