# OS 표준 사용자 데이터 폴더에 설정과 모델을 저장/로드하는 모듈
import json
import os
import sys
from pathlib import Path
from app.version import APP_VERSION

APP_NAME = "TubeVocalRemoval"

if sys.platform == "win32":
    CONFIG_DIR = Path(os.environ.get("APPDATA", str(Path.home()))) / APP_NAME
elif sys.platform == "darwin":
    CONFIG_DIR = Path.home() / "Library" / "Application Support" / APP_NAME
else:
    CONFIG_DIR = Path(os.environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config"))) / APP_NAME
CONFIG_PATH = CONFIG_DIR / "config.json"
TEMP_DIR = CONFIG_DIR / "temp"
MODELS_DIR = CONFIG_DIR / "models"

DEFAULTS = {
    # 모든 분리 결과가 저장되는 폴더 (곡별 하위 폴더 생성)
    "output_dir": str(Path.home() / "Music" / "Tube Vocal Removal"),
    "output_format": "MP3",          # MP3 | WAV | FLAC
    "mp3_bitrate": "320k",           # MP3일 때만 사용
    "keep_source": False,            # 분리 후 다운로드 원본 보관 여부
    "use_gpu": False,               # 기본 CPU, 선택 시 Windows CUDA 또는 macOS MPS/CoreML 사용
    "mode": "best",                 # 마지막으로 선택한 분리 프로그램 (P1~P5) 복원용
    "volume_fix": True,             # 구간 평탄화 + -14 LUFS 볼륨 보정 (악기별 분리 제외)
    "download_lyrics": True,         # 분리 시 곡 폴더에 가사(.txt) 함께 저장
    "key_shift": 0,                  # 반주/보컬 키 이동 반음 수 (-6~+6, 0은 원키). 악기별 분리 제외
}


def load() -> dict:
    cfg = dict(DEFAULTS)
    try:
        if CONFIG_PATH.exists():
            saved = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
            cfg.update({k: v for k, v in saved.items() if k in DEFAULTS})
    except (OSError, json.JSONDecodeError):
        pass  # 설정 파일이 깨졌으면 기본값으로 시작
    return cfg


def save(cfg: dict) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    data = {k: cfg[k] for k in DEFAULTS if k in cfg}
    CONFIG_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def validated(values: dict | None) -> dict:
    """UI에서 받은 설정을 허용된 값과 타입으로 제한한다."""
    values = values or {}
    result = {}
    if values.get("output_format") in {"WAV", "FLAC", "MP3"}:
        result["output_format"] = values["output_format"]
    if values.get("mp3_bitrate") in {"128k", "192k", "256k", "320k"}:
        result["mp3_bitrate"] = values["mp3_bitrate"]
    if values.get("mode") in {"karaoke_fast", "karaoke", "best", "vocals", "demucs"}:
        result["mode"] = values["mode"]
    for key in ("keep_source", "use_gpu", "volume_fix", "download_lyrics"):
        if key in values and isinstance(values[key], bool):
            result[key] = values[key]
    if "key_shift" in values:
        try:
            result["key_shift"] = max(-6, min(6, int(values["key_shift"])))
        except (TypeError, ValueError):
            pass
    output_dir = values.get("output_dir")
    if isinstance(output_dir, str) and output_dir.strip():
        result["output_dir"] = str(Path(output_dir).expanduser())
    return result


def ensure_dirs(cfg: dict) -> None:
    Path(cfg["output_dir"]).mkdir(parents=True, exist_ok=True)
    TEMP_DIR.mkdir(parents=True, exist_ok=True)
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
