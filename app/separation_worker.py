import json
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

_PROGRESS_PATH = None
_PROGRESS_LOCK = threading.Lock()
_INFERENCE_MODEL_INDEX = 0
_INFERENCE_MODEL_TOTAL = 1
_INFERENCE_LAST_PCT = -1.0


def _hide_all_child_consoles():
    """Ensure third-party FFmpeg/Deno helpers never flash a console window."""
    if os.name != "nt" or getattr(subprocess.Popen, "_tvr_hidden", False):
        return
    original_popen = subprocess.Popen

    class HiddenPopen(original_popen):
        _tvr_hidden = True

        def __init__(self, *args, **kwargs):
            kwargs["creationflags"] = kwargs.get("creationflags", 0) | subprocess.CREATE_NO_WINDOW
            startupinfo = kwargs.get("startupinfo") or subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = subprocess.SW_HIDE
            kwargs["startupinfo"] = startupinfo
            super().__init__(*args, **kwargs)

    subprocess.Popen = HiddenPopen


def _set_inference_model(index: int, total: int):
    global _INFERENCE_MODEL_INDEX, _INFERENCE_MODEL_TOTAL
    _INFERENCE_MODEL_INDEX = max(0, int(index))
    _INFERENCE_MODEL_TOTAL = max(1, int(total))


def _install_inference_progress():
    """Replace engine tqdm iterators with progress-reporting iterators."""
    global _INFERENCE_LAST_PCT
    _INFERENCE_LAST_PCT = -1.0

    class ProgressIterable:
        def __init__(self, iterable, total=None):
            self.iterable = iterable
            try:
                self.total = int(total if total is not None else len(iterable))
            except (TypeError, ValueError):
                self.total = 0

        def __len__(self):
            return self.total

        def __iter__(self):
            global _INFERENCE_LAST_PCT
            for count, value in enumerate(self.iterable, 1):
                yield value
                if self.total <= 0:
                    continue
                local = min(1.0, count / self.total)
                overall = ((_INFERENCE_MODEL_INDEX + local) / _INFERENCE_MODEL_TOTAL) * 100.0
                # Nested/preparation loops can restart at zero. Never move the UI backwards.
                if overall > _INFERENCE_LAST_PCT + 0.05:
                    _INFERENCE_LAST_PCT = overall
                    _progress({"type": "inference_progress", "pct": round(overall, 1)})

    def progress_tqdm(iterable=None, *args, **kwargs):
        if iterable is None:
            iterable = range(int(kwargs.get("total") or 0))
        return ProgressIterable(iterable, kwargs.get("total"))

    import tqdm as tqdm_module
    from audio_separator.separator.architectures import mdx_separator, mdxc_separator, vr_separator

    tqdm_module.tqdm = progress_tqdm
    mdx_separator.tqdm = progress_tqdm
    mdxc_separator.tqdm = progress_tqdm
    vr_separator.tqdm = progress_tqdm


def _write_response(path: Path, payload: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _progress(payload: dict):
    if _PROGRESS_PATH:
        with _PROGRESS_LOCK:
            with _PROGRESS_PATH.open("a", encoding="utf-8") as file:
                file.write(json.dumps(payload, ensure_ascii=False) + "\n")
                file.flush()


def run_request(request_file: str) -> int:
    global _PROGRESS_PATH
    request_path = Path(request_file).resolve()
    request = json.loads(request_path.read_text(encoding="utf-8"))
    response_path = Path(request["response_path"])
    _PROGRESS_PATH = Path(request["progress_path"]) if request.get("progress_path") else None
    use_gpu = bool(request.get("use_gpu", False))
    _hide_all_child_consoles()

    if not use_gpu:
        # 배포 환경에서 CPU가 무제한으로 점유되는 것을 막되 UVR의 Batch 1 모델 설정은 유지한다.
        thread_count = min(8, max(1, (os.cpu_count() or 2) // 2))
        os.environ["OMP_NUM_THREADS"] = str(thread_count)
        os.environ["MKL_NUM_THREADS"] = str(thread_count)
        os.environ["OPENBLAS_NUM_THREADS"] = str(thread_count)

    try:
        import requests
        import torch
        from audio_separator.separator import Separator
        from app.pipeline import MODE_MODELS

        class ProgressSeparator(Separator):
            def load_model(self, model_filename="model_bs_roformer_ep_317_sdr_12.9755.ckpt"):
                ensemble_models = list(self._ensemble_preset_models or [])
                if ensemble_models and model_filename in ensemble_models:
                    _set_inference_model(ensemble_models.index(model_filename), len(ensemble_models))
                elif not isinstance(model_filename, list):
                    _set_inference_model(0, 1)
                return super().load_model(model_filename=model_filename)

            def download_file_if_not_exists(self, url, output_path):
                output = Path(output_path)
                if output.is_file():
                    return
                output.parent.mkdir(parents=True, exist_ok=True)
                partial = output.with_name(output.name + ".part")
                response = None
                try:
                    response = requests.get(url, stream=True, timeout=300)
                    if response.status_code != 200:
                        raise RuntimeError(f"모델 다운로드 실패 (HTTP {response.status_code})")
                    total = int(response.headers.get("content-length", 0))
                    received = 0
                    last_emit = 0.0
                    started = time.monotonic()
                    with partial.open("wb") as file:
                        for chunk in response.iter_content(chunk_size=256 * 1024):
                            if not chunk:
                                continue
                            file.write(chunk)
                            received += len(chunk)
                            now = time.monotonic()
                            if now - last_emit >= 0.15 or (total and received >= total):
                                last_emit = now
                                pct = round(min(100.0, received / total * 100), 1) if total else None
                                speed = received / max(0.001, now - started)
                                eta = (total - received) / speed if total and speed else None
                                _progress({
                                    "type": "model_download",
                                    "filename": output.name,
                                    "received": received,
                                    "total": total,
                                    "pct": pct,
                                    "speed": speed,
                                    "eta": eta,
                                })
                except requests.exceptions.RequestException as exc:
                    partial.unlink(missing_ok=True)
                    raise RuntimeError(f"모델 다운로드 네트워크 오류: {exc}") from exc
                finally:
                    if response is not None:
                        response.close()
                # Content-Length is only a progress hint. CDNs/proxies can report
                # the encoded transfer size while requests yields decoded bytes,
                # so strict equality rejects otherwise complete model files.
                if received <= 0:
                    partial.unlink(missing_ok=True)
                    raise RuntimeError("모델 다운로드 결과가 비어 있습니다.")
                os.replace(partial, output)

        mps_backend = getattr(torch.backends, "mps", None)
        mps_available = sys.platform == "darwin" and mps_backend is not None and mps_backend.is_available()
        cuda_available = torch.cuda.is_available()
        if use_gpu and not (cuda_available or mps_available):
            raise RuntimeError("GPU 사용을 선택했지만 CUDA 또는 Apple Silicon MPS 가속을 사용할 수 없습니다.")
        accelerator = "cuda" if use_gpu and cuda_available else "mps" if use_gpu and mps_available else "cpu"
        if not use_gpu:
            torch.set_num_threads(thread_count)
            try:
                torch.set_num_interop_threads(1)
            except RuntimeError:
                pass

        mode = request.get("mode", "karaoke")
        selection = MODE_MODELS.get(mode, MODE_MODELS["karaoke"])
        preset = selection.get("preset") if isinstance(selection, dict) else None
        output_format = request.get("output_format", "WAV").upper()
        separator = ProgressSeparator(
            output_dir=request["output_dir"],
            model_file_dir=request["models_dir"],
            output_format=output_format,
            output_bitrate=request.get("mp3_bitrate") if output_format == "MP3" else None,
            ensemble_preset=preset,
        )
        if request.get("action") == "download_only":
            # Cache model files without instantiating the neural network. Loading a
            # model here can allocate gigabytes even though no separation is running.
            model_files = separator._ensemble_preset_models if preset else [selection]
            for model_filename in model_files:
                separator.download_model_files(model_filename)
            _write_response(response_path, {"ok": True, "outputs": [], "device": "cpu"})
            return 0

        if accelerator == "cpu":
            separator.torch_device = torch.device("cpu")
            separator.onnx_execution_provider = ["CPUExecutionProvider"]
        elif accelerator == "mps":
            # audio-separator도 자동 감지하지만 명시해 PyInstaller 환경의 플랫폼 감지 편차를 없앤다.
            separator.torch_device_mps = torch.device("mps")
            separator.torch_device = separator.torch_device_mps
            try:
                import onnxruntime as ort
                providers = ort.get_available_providers()
            except (ImportError, RuntimeError):
                providers = []
            separator.onnx_execution_provider = (
                ["CoreMLExecutionProvider"] if "CoreMLExecutionProvider" in providers
                else ["CPUExecutionProvider"]
            )
        if preset:
            separator.load_model()
        else:
            separator.load_model(model_filename=selection)
        inference_done = threading.Event()
        inference_started = time.monotonic()

        def heartbeat():
            while not inference_done.wait(1.0):
                _progress({"type": "inference_elapsed", "seconds": int(time.monotonic() - inference_started)})

        threading.Thread(target=heartbeat, daemon=True).start()
        try:
            _install_inference_progress()
            outputs = separator.separate(request["source"])
        finally:
            inference_done.set()
        resolved = []
        for raw in outputs or []:
            path = Path(raw)
            if not path.is_absolute():
                path = Path(request["output_dir"]) / path
            resolved.append(str(path.resolve()))
        _write_response(response_path, {"ok": True, "outputs": resolved, "device": accelerator})
        return 0
    except (Exception, SystemExit) as exc:
        _write_response(response_path, {"ok": False, "error": str(exc) or type(exc).__name__})
        return 1


if __name__ == "__main__":
    raise SystemExit(run_request(sys.argv[1]))
