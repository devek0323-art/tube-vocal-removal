# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_all, collect_submodules

audio_datas, audio_binaries, audio_hidden = collect_all("audio_separator")
webview_datas, webview_binaries, webview_hidden = collect_all("webview")
stretch_datas, stretch_binaries, stretch_hidden = collect_all("python_stretch")
sf_datas, sf_binaries, sf_hidden = collect_all("soundfile")
librosa_datas, librosa_binaries, librosa_hidden = collect_all("librosa")
scipy_dynamic = (
    collect_submodules("scipy._external.array_api_compat")
    + collect_submodules("scipy._lib.array_api_compat")
    + ["scipy.special._cdflib"]
)

a = Analysis(
    ["app/main.py"],
    pathex=["."],
    binaries=(audio_binaries + webview_binaries + stretch_binaries + sf_binaries
              + librosa_binaries),
    datas=[
        ("app/ui/index.html", "app/ui"),
        ("app/ui/fonts", "app/ui/fonts"),
        ("bin/yt-dlp", "bin"),
        ("bin/ffmpeg", "bin"),
        ("bin/deno", "bin"),
    ] + audio_datas + webview_datas + stretch_datas + sf_datas + librosa_datas,
    hiddenimports=(audio_hidden + webview_hidden + scipy_dynamic
                   + stretch_hidden + sf_hidden + librosa_hidden
                   + ["python_stretch", "soundfile", "librosa", "onnxruntime"]),
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
    upx=False,
    console=False,
    target_arch="arm64",
    codesign_identity=None,
    entitlements_file=None,
    contents_directory="runtime",
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="Tube Vocal Removal",
)

app = BUNDLE(
    coll,
    name="Tube Vocal Removal.app",
    icon="build-assets/TubeVocalRemoval.icns",
    bundle_identifier="art.devek0323.tube-vocal-removal",
    info_plist={
        "CFBundleDisplayName": "Tube Vocal Removal",
        "CFBundleShortVersionString": "2.06",
        "CFBundleVersion": "2.0.2",
        "LSMinimumSystemVersion": "14.0",
        "NSHighResolutionCapable": True,
    },
)
