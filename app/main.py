import json
import os
import subprocess
import sys
import time
from pathlib import Path

from app.platform_support import accelerator_info, hidden_process_kwargs, tool_name

RESOURCE_ROOT = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
UI_PATH = RESOURCE_ROOT / "app" / "ui" / "index.html"


def dropped_paths(event: dict) -> list[str]:
    """Extract absolute paths injected by pywebview's native drop bridge."""
    transfer = (event or {}).get("dataTransfer") or {}
    files = transfer.get("files") or []
    return [
        file["pywebviewFullPath"]
        for file in files
        if isinstance(file, dict) and file.get("pywebviewFullPath")
    ]


def write_smoke_report(report_path: str, payload: dict) -> int:
    path = Path(report_path).resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0 if payload.get("ok") else 1


def smoke_test(report_path: str) -> int:
    """패키징된 실행 파일의 필수 자원과 GPU 런타임을 빠르게 검사한다."""
    try:
        import torch
        import audio_separator  # noqa: F401

        checks = {
            "ui": UI_PATH.is_file(),
            "yt_dlp": (RESOURCE_ROOT / "bin" / tool_name("yt-dlp")).is_file(),
            "deno": (RESOURCE_ROOT / "bin" / tool_name("deno")).is_file(),
        }
        ffmpeg = subprocess.run(
            [str(RESOURCE_ROOT / "bin" / tool_name("ffmpeg")), "-version"],
            capture_output=True,
            timeout=15,
            **hidden_process_kwargs(),
        )
        checks["ffmpeg"] = ffmpeg.returncode == 0
        checks["audio_separator"] = True
        accelerator = accelerator_info()
        checks["accelerator"] = accelerator["available"]
        checks["cuda"] = accelerator["backend"] == "cuda"
        checks["mps"] = accelerator["backend"] == "mps"
        gpu = accelerator["name"]
        required = ("ui", "yt_dlp", "deno", "ffmpeg", "audio_separator")
        return write_smoke_report(report_path, {"ok": all(checks[name] for name in required), "checks": checks, "gpu": gpu})
    except Exception as exc:
        return write_smoke_report(report_path, {"ok": False, "checks": {}, "error": str(exc)})


def smoke_audio(source: str, output_dir: str, report_path: str) -> int:
    """빌드된 EXE 안의 실제 파이프라인으로 한 파일을 분리한다."""
    from app import config
    from app.pipeline import Pipeline

    events = []
    pipeline = Pipeline(events.append)
    if not pipeline.add_files([source]):
        return write_smoke_report(report_path, {"ok": False, "error": "입력 오디오를 읽지 못했습니다."})
    cfg = dict(config.DEFAULTS, output_dir=str(Path(output_dir).resolve()), output_format="WAV")
    pipeline.start("karaoke", cfg)
    deadline = time.time() + 900
    while pipeline.running and time.time() < deadline:
        time.sleep(0.1)
    item = pipeline.items[0]
    outputs = list(Path(item.out_dir).glob("*.wav")) if item.out_dir else []
    return write_smoke_report(
        report_path,
        {
            "ok": item.status == "done" and len(outputs) == 1 and "반주" in outputs[0].name,
            "status": item.status,
            "error": item.error,
            "output_dir": item.out_dir,
            "outputs": [str(path) for path in outputs],
        },
    )


def main() -> int:
    bin_dir = RESOURCE_ROOT / "bin"
    os.environ["PATH"] = str(bin_dir) + os.pathsep + os.environ.get("PATH", "")

    if len(sys.argv) >= 3 and sys.argv[1] == "--separation-worker":
        from app.separation_worker import run_request

        return run_request(sys.argv[2])
    if len(sys.argv) >= 3 and sys.argv[1] == "--smoke-test":
        return smoke_test(sys.argv[2])
    if len(sys.argv) >= 5 and sys.argv[1] == "--smoke-audio":
        return smoke_audio(sys.argv[2], sys.argv[3], sys.argv[4])

    import webview
    from app.api import Api

    api = Api()
    window = webview.create_window(
        "Tube Vocal Removal",
        url=UI_PATH.as_uri(),
        js_api=api,
        width=580,
        height=728,
        min_size=(540, 650),
        frameless=True,
        easy_drag=False,
        background_color="#171310",
    )
    api._window = window

    def bind_native_drop():
        from webview.dom import DOMEventHandler

        def on_drop(event):
            paths = dropped_paths(event)
            if paths:
                api.add_dropped_files(paths)

        window.dom.body.on("drop", DOMEventHandler(on_drop, prevent_default=True))

    webview.start(bind_native_drop, debug=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
