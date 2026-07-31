"""Small OS-specific helpers shared by the desktop app and worker processes."""

import os
import signal
import subprocess
import sys
from pathlib import Path


IS_WINDOWS = sys.platform == "win32"
IS_MACOS = sys.platform == "darwin"
EXECUTABLE_SUFFIX = ".exe" if IS_WINDOWS else ""


def tool_name(name: str) -> str:
    return name + EXECUTABLE_SUFFIX


def hidden_process_kwargs(*, new_group: bool = False, detached: bool = False) -> dict:
    """Return subprocess options without passing Windows-only flags on POSIX."""
    if IS_WINDOWS:
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        if new_group:
            flags |= getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        if detached:
            flags |= getattr(subprocess, "DETACHED_PROCESS", 0)
        return {"creationflags": flags}
    return {"start_new_session": True} if new_group or detached else {}


def open_path(path: str | Path) -> None:
    target = str(path)
    if IS_WINDOWS:
        subprocess.Popen(["explorer", target], **hidden_process_kwargs())
    elif IS_MACOS:
        subprocess.Popen(["open", target], start_new_session=True)
    else:
        subprocess.Popen(["xdg-open", target], start_new_session=True)


def accelerator_info() -> dict:
    """Describe the accelerator usable by audio-separator on this machine."""
    try:
        import torch

        if torch.cuda.is_available():
            return {"available": True, "backend": "cuda", "name": torch.cuda.get_device_name(0)}
        mps = getattr(getattr(torch, "backends", None), "mps", None)
        if IS_MACOS and mps is not None and mps.is_available():
            return {"available": True, "backend": "mps", "name": "Apple Silicon · MPS/CoreML"}
    except (ImportError, RuntimeError):
        pass
    return {"available": False, "backend": "cpu", "name": ""}


def terminate_process_tree(proc) -> None:
    if proc.poll() is not None:
        return
    if IS_WINDOWS:
        subprocess.run(
            ["taskkill", "/PID", str(proc.pid), "/T", "/F"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
            **hidden_process_kwargs(),
        )
    else:
        try:
            os.killpg(proc.pid, signal.SIGTERM)
        except (ProcessLookupError, PermissionError):
            proc.terminate()
    if proc.poll() is None:
        proc.kill()
