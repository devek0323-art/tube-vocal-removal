"""Small OS-specific helpers shared by the desktop app and worker processes."""

import os
import signal
import subprocess
import sys
import tempfile
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


_MACOS_UPDATE_SCRIPT = r"""#!/bin/sh
# 앱이 종료되기를 기다린 뒤 DMG 안의 새 앱으로 교체하고 다시 실행한다.
# 어느 단계에서든 실패하면 원래 앱을 되돌리고 DMG를 열어 수동 설치로 넘긴다.
DMG="$1"; APP="$2"; PID="$3"
NAME=$(basename "$APP")
MNT="/tmp/tvr-mnt-$$"
STAGE="/tmp/tvr-stage-$$"

i=0
while kill -0 "$PID" 2>/dev/null && [ $i -lt 60 ]; do sleep 0.5; i=$((i + 1)); done

fail() {
    hdiutil detach "$MNT" -quiet 2>/dev/null
    rm -rf "$MNT" "$STAGE"
    open "$DMG"
    exit 1
}

mkdir -p "$MNT" "$STAGE" || fail
hdiutil attach "$DMG" -nobrowse -quiet -mountpoint "$MNT" || fail
[ -d "$MNT/$NAME" ] || fail
# 새 앱을 먼저 확보한다. 이 단계까지는 기존 앱을 건드리지 않는다.
ditto "$MNT/$NAME" "$STAGE/$NAME" || fail
hdiutil detach "$MNT" -quiet
rmdir "$MNT" 2>/dev/null

BACKUP="$APP.old-$$"
mv "$APP" "$BACKUP" 2>/dev/null
if ! mv "$STAGE/$NAME" "$APP"; then
    [ -d "$BACKUP" ] && mv "$BACKUP" "$APP"
    rm -rf "$STAGE"
    open "$DMG"
    exit 1
fi
rm -rf "$BACKUP" "$STAGE"
open "$APP"
"""


def macos_app_path():
    """실행 중인 .app 번들 경로. 번들로 실행된 것이 아니면 None."""
    for parent in Path(sys.executable).resolve().parents:
        if parent.suffix == ".app":
            return parent
    return None


def macos_replace_app(dmg, app) -> bool:
    """DMG의 앱으로 교체하고 재실행하는 스크립트를 앱과 분리해 띄운다."""
    script = Path(tempfile.gettempdir()) / "tube-vocal-removal-update.sh"
    try:
        script.write_text(_MACOS_UPDATE_SCRIPT, encoding="utf-8")
        script.chmod(0o755)
        subprocess.Popen(
            ["/bin/sh", str(script), str(dmg), str(app), str(os.getpid())],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            close_fds=True,
            start_new_session=True,
        )
    except OSError:
        return False
    return True


def cuda_arch_supported(torch) -> bool:
    """이 배포본에 설치된 GPU용 커널이 들어 있는지 확인한다.

    CUDA 13 빌드는 Turing(sm_75) 이상만 담고 있어 GTX 10xx 이하에서는 커널이 없다.
    반대로 CUDA 12 빌드에는 RTX 50(sm_120) 커널이 없다. 어느 쪽이든
    `torch.cuda.is_available()`은 True를 돌려주므로 arch 목록을 직접 대조해야 한다.
    """
    # 드라이버가 장치를 열지 못하는 상태에서 get_device_capability를 부르면
    # 예외가 아니라 프로세스가 그대로 죽는다. is_available 확인을 건너뛰면 안 된다.
    try:
        if not torch.cuda.is_available():
            return False
        major, minor = torch.cuda.get_device_capability(0)
        arch_list = torch.cuda.get_arch_list()
    except (RuntimeError, AssertionError, IndexError):
        return False
    for name in arch_list:
        # cubin은 같은 major 세대 안에서 상위 minor로 올라가는 방향만 호환된다.
        if name.startswith("sm_") and name[3:].rstrip("a").isdigit():
            value = int(name[3:].rstrip("a"))
            if value // 10 == major and value % 10 <= minor:
                return True
        # PTX가 있으면 같거나 낮은 세대용 코드를 드라이버가 JIT 컴파일한다.
        if name.startswith("compute_") and name[8:].isdigit() and int(name[8:]) <= major * 10 + minor:
            return True
    return False


def accelerator_info() -> dict:
    """Describe the accelerator usable by audio-separator on this machine."""
    try:
        import torch

        if torch.cuda.is_available() and cuda_arch_supported(torch):
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
