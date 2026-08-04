# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_all, collect_submodules

audio_datas, audio_binaries, audio_hidden = collect_all("audio_separator")
webview_datas, webview_binaries, webview_hidden = collect_all("webview")
# 키 이동/감지·가사 기능에 필요한 런타임 (Signalsmith 시프트, 오디오 IO, 키 감지)
stretch_datas, stretch_binaries, stretch_hidden = collect_all("python_stretch")
sf_datas, sf_binaries, sf_hidden = collect_all("soundfile")
librosa_datas, librosa_binaries, librosa_hidden = collect_all("librosa")
# 노래방 영상(P6)의 가사 타이밍. mel 필터·토크나이저 데이터까지 담아야 한다.
whisper_datas, whisper_binaries, whisper_hidden = collect_all("whisper")
scipy_dynamic = (
    collect_submodules("scipy._external.array_api_compat")
    + collect_submodules("scipy._lib.array_api_compat")
    + ["scipy.special._cdflib"]
)

a = Analysis(
    ["app/main.py"],
    pathex=["."],
    binaries=(audio_binaries + webview_binaries + stretch_binaries + sf_binaries
              + librosa_binaries + whisper_binaries),
    datas=[
        ("app/ui/index.html", "app/ui"),
        ("app/ui/fonts", "app/ui/fonts"),
        ("app/assets/Pretendard.ttf", "app/assets"),
        ("bin/yt-dlp.exe", "bin"),
        ("bin/ffmpeg.exe", "bin"),
        ("bin/deno.exe", "bin"),
    ] + audio_datas + webview_datas + stretch_datas + sf_datas + librosa_datas + whisper_datas,
    hiddenimports=(audio_hidden + webview_hidden + scipy_dynamic
                   + stretch_hidden + sf_hidden + librosa_hidden
                   + whisper_hidden + ["python_stretch", "soundfile", "librosa", "whisper"]),
    hookspath=[],
    runtime_hooks=[],
    excludes=["tkinter", "tkinterdnd2", "PyQt5", "PyQt6", "PySide2", "PySide6"],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Tube Vocal Removal",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    icon=["app/assets/app-icon.png"],
    version="installer/version_info.txt",
    disable_windowed_traceback=False,
    contents_directory="runtime",  # 기본 '_internal' 대신 깔끔한 폴더명
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="Tube Vocal Removal",
)
