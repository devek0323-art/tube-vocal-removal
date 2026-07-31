import json
import hashlib
import os
import queue
import subprocess
import tempfile
import threading
import urllib.request
from pathlib import Path

import webview

from app import config
from app.pipeline import Pipeline
from app.platform_support import IS_MACOS, IS_WINDOWS, accelerator_info, hidden_process_kwargs, open_path
from app.version import APP_VERSION, GITHUB_API_VERSION, GITHUB_REPOSITORY


class Api:
    def __init__(self):
        # pywebview recursively exposes every public attribute. Keep all state
        # private so Window -> Api -> Pipeline -> emit cycles are never walked.
        self._cfg = config.load()
        self._window = None
        self._maximized = False
        self._events = queue.SimpleQueue()
        self._pipeline = Pipeline(self._events.put)
        self._update_busy = False
        self._update_release = None
        self._update_installer = None

    def get_app_version(self):
        return APP_VERSION

    @staticmethod
    def _version_tuple(value):
        parts = []
        for token in str(value).lower().lstrip("v").split("."):
            digits = "".join(ch for ch in token if ch.isdigit())
            parts.append(int(digits or 0))
        return tuple((parts + [0, 0, 0])[:3])

    def check_for_updates(self):
        if self._update_busy:
            return False
        self._update_busy = True
        threading.Thread(target=self._check_update_worker, daemon=True).start()
        return True

    def _check_update_worker(self):
        self._events.put({"type": "update_state", "state": "checking", "current": APP_VERSION})
        try:
            request = urllib.request.Request(
                f"https://api.github.com/repos/{GITHUB_REPOSITORY}/releases/latest",
                headers={
                    "Accept": "application/vnd.github+json",
                    "X-GitHub-Api-Version": GITHUB_API_VERSION,
                    "User-Agent": f"Tube-Vocal-Removal/{APP_VERSION}",
                },
            )
            with urllib.request.urlopen(request, timeout=30) as response:
                release = json.loads(response.read().decode("utf-8"))
            latest = str(release.get("tag_name", "")).lstrip("v")
            assets = release.get("assets") or []
            extension = ".exe" if IS_WINDOWS else ".dmg" if IS_MACOS else ""
            asset = next(
                (item for item in assets if item.get("name", "").lower().endswith(extension)
                 and ("setup" in item.get("name", "").lower() if IS_WINDOWS else True)),
                None,
            )
            if not latest or not asset:
                raise RuntimeError("최신 릴리즈에 설치파일이 없습니다.")
            if self._version_tuple(latest) <= self._version_tuple(APP_VERSION):
                self._update_release = None
                self._events.put({"type": "update_state", "state": "current", "current": APP_VERSION, "latest": latest})
                return
            self._update_release = {
                "version": latest,
                "url": asset["browser_download_url"],
                "size": int(asset.get("size") or 0),
                "digest": str(asset.get("digest") or ""),
                "name": asset["name"],
            }
            self._events.put({
                "type": "update_state", "state": "available", "current": APP_VERSION,
                "latest": latest, "size": self._update_release["size"],
            })
        except Exception as exc:
            self._update_release = None
            self._events.put({"type": "update_state", "state": "error", "current": APP_VERSION, "error": str(exc)})
        finally:
            self._update_busy = False

    def download_update(self):
        if self._update_busy or not self._update_release:
            return False
        self._update_busy = True
        threading.Thread(target=self._download_update_worker, daemon=True).start()
        return True

    def _download_update_worker(self):
        release = dict(self._update_release)
        final_path = Path(tempfile.gettempdir()) / release["name"]
        partial_path = final_path.with_name(final_path.name + ".part")
        self._events.put({"type": "update_state", "state": "downloading", "current": APP_VERSION, "latest": release["version"]})
        try:
            partial_path.unlink(missing_ok=True)
            request = urllib.request.Request(release["url"], headers={"User-Agent": f"Tube-Vocal-Removal/{APP_VERSION}"})
            digest = hashlib.sha256()
            received = 0
            with urllib.request.urlopen(request, timeout=60) as response, partial_path.open("wb") as output:
                total = int(response.headers.get("Content-Length") or release["size"] or 0)
                while True:
                    chunk = response.read(1024 * 1024)
                    if not chunk:
                        break
                    output.write(chunk)
                    digest.update(chunk)
                    received += len(chunk)
                    pct = round(min(100.0, received / total * 100), 1) if total else None
                    self._events.put({"type": "update_progress", "received": received, "total": total, "pct": pct})
            if received <= 0:
                raise RuntimeError("업데이트 설치파일이 비어 있습니다.")
            expected = release["digest"].lower()
            if not expected.startswith("sha256:"):
                raise RuntimeError("업데이트 파일의 SHA-256 정보가 없습니다.")
            if digest.hexdigest().lower() != expected.split(":", 1)[1]:
                raise RuntimeError("업데이트 파일 무결성 검사에 실패했습니다.")
            os.replace(partial_path, final_path)
            self._update_installer = final_path
            self._events.put({"type": "update_state", "state": "ready", "current": APP_VERSION, "latest": release["version"]})
        except Exception as exc:
            partial_path.unlink(missing_ok=True)
            self._update_installer = None
            self._events.put({"type": "update_state", "state": "error", "current": APP_VERSION, "error": str(exc)})
        finally:
            self._update_busy = False

    def apply_update(self):
        installer = self._update_installer
        if (self._update_busy or not installer or not Path(installer).is_file()
                or self._pipeline.running or self._pipeline.model_downloading):
            return False
        self._events.put({"type": "update_state", "state": "installing", "current": APP_VERSION})
        try:
            if IS_MACOS:
                open_path(installer)
                self._events.put({"type": "update_state", "state": "manual_install", "current": APP_VERSION})
                return True
            install_log = Path(tempfile.gettempdir()) / "TubeVocalRemoval-update-install.log"
            subprocess.Popen(
                [str(installer), "/SILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/SP-",
                 "/CLOSEAPPLICATIONS", f"/LOG={install_log}"],
                cwd=str(Path(installer).parent),
                close_fds=True,
                **hidden_process_kwargs(new_group=True, detached=True),
            )
        except OSError as exc:
            self._events.put({
                "type": "update_state", "state": "error", "current": APP_VERSION,
                "error": f"설치 프로그램을 열지 못했습니다: {exc}",
            })
            return False
        self._window.destroy()
        return True

    def get_settings(self):
        return self._cfg

    def save_settings(self, new_cfg):
        self._cfg.update(config.validated(new_cfg))
        config.save(self._cfg)
        return self._cfg

    def choose_output_dir(self):
        result = self._window.create_file_dialog(webview.FOLDER_DIALOG)
        if result:
            self._cfg["output_dir"] = result[0]
            config.save(self._cfg)
        return self._cfg["output_dir"]

    def add_urls(self, text):
        return self._pipeline.add_urls(text)

    def pick_files(self):
        result = self._window.create_file_dialog(
            webview.OPEN_DIALOG,
            allow_multiple=True,
            file_types=("오디오 파일 (*.mp3;*.wav;*.flac;*.m4a;*.opus;*.ogg;*.webm)",),
        )
        return self._pipeline.add_files(list(result or []))

    def add_dropped_files(self, paths):
        return self._pipeline.add_files(paths or [])

    def remove_item(self, item_id):
        self._pipeline.remove(int(item_id))

    def reset_queue(self):
        return self._pipeline.reset()

    def set_item_key(self, item_id, semitones):
        return self._pipeline.set_item_key(int(item_id), int(semitones))

    def set_item_lyrics(self, item_id, enabled):
        return self._pipeline.set_item_lyrics(int(item_id), bool(enabled))

    def start(self, mode):
        return self._pipeline.start(mode, self._cfg)

    def cancel(self):
        self._pipeline.cancel()

    def download_model(self, mode):
        return self._pipeline.download_model(mode, self._cfg)

    def download_all_models(self):
        return self._pipeline.download_all_models(self._cfg)

    def open_folder(self, path):
        target = path or self._cfg["output_dir"]
        if os.path.isdir(target):
            open_path(target)
            return True
        return False

    def get_gpu_info(self):
        """Return CUDA or Apple Silicon MPS/CoreML availability."""
        info = accelerator_info()
        return {"type": "gpu", **info}

    def poll_events(self):
        """Drain pending worker events. JavaScript calls this from one loop."""
        events = []
        while len(events) < 100:
            try:
                events.append(self._events.get_nowait())
            except queue.Empty:
                break
        return events

    def win_minimize(self):
        self._window.minimize()

    def win_toggle_max(self):
        try:
            if self._maximized:
                self._window.restore()
            else:
                self._window.maximize()
            self._maximized = not self._maximized
        except Exception:
            return False
        return True

    def win_close(self):
        if self._pipeline.running:
            return False
        self._window.destroy()
        return True

    def win_force_close(self):
        self._pipeline.cancel()
        self._window.destroy()
        return True
