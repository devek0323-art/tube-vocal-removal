"""Prepare redistributable command-line tools for the current CI platform."""

import argparse
import shutil
import stat
import tempfile
import urllib.request
import zipfile
from pathlib import Path

import imageio_ffmpeg


def download(url: str, destination: Path) -> None:
    request = urllib.request.Request(url, headers={"User-Agent": "Tube-Vocal-Removal-build"})
    with urllib.request.urlopen(request, timeout=300) as response, destination.open("wb") as output:
        shutil.copyfileobj(response, output)


def make_executable(path: Path) -> None:
    path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("platform", choices=("windows", "macos"))
    args = parser.parse_args()

    root = Path(__file__).resolve().parent.parent
    bin_dir = root / "bin"
    bin_dir.mkdir(parents=True, exist_ok=True)
    suffix = ".exe" if args.platform == "windows" else ""

    ffmpeg = bin_dir / f"ffmpeg{suffix}"
    shutil.copy2(imageio_ffmpeg.get_ffmpeg_exe(), ffmpeg)

    yt_dlp = bin_dir / f"yt-dlp{suffix}"
    yt_asset = "yt-dlp.exe" if args.platform == "windows" else "yt-dlp_macos"
    download(f"https://github.com/yt-dlp/yt-dlp/releases/latest/download/{yt_asset}", yt_dlp)

    deno = bin_dir / f"deno{suffix}"
    deno_asset = "deno-x86_64-pc-windows-msvc.zip" if args.platform == "windows" else "deno-aarch64-apple-darwin.zip"
    with tempfile.TemporaryDirectory() as tmp:
        archive = Path(tmp) / "deno.zip"
        download(f"https://github.com/denoland/deno/releases/latest/download/{deno_asset}", archive)
        with zipfile.ZipFile(archive) as package:
            member = next(name for name in package.namelist() if Path(name).name == f"deno{suffix}")
            with package.open(member) as source, deno.open("wb") as output:
                shutil.copyfileobj(source, output)

    for tool in (ffmpeg, yt_dlp, deno):
        make_executable(tool)
        print(f"prepared {tool.relative_to(root)} ({tool.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
