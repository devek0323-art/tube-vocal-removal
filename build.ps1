param(
    [switch]$SkipTests
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$Python = Join-Path $Root ".venv\Scripts\python.exe"
$PyInstaller = Join-Path $Root ".venv\Scripts\pyinstaller.exe"

if (-not (Test-Path $Python)) { throw ".venv가 없습니다." }
if (-not (Test-Path (Join-Path $Root "bin\ffmpeg.exe"))) { throw "bin\ffmpeg.exe가 없습니다." }
if (-not (Test-Path (Join-Path $Root "bin\yt-dlp.exe"))) { throw "bin\yt-dlp.exe가 없습니다." }

if (-not $SkipTests) {
    & $Python -m unittest discover -v
    if ($LASTEXITCODE -ne 0) { throw "자동 테스트 실패" }
}

& $PyInstaller --noconfirm --clean (Join-Path $Root "TubeVocalRemoval.spec")
if ($LASTEXITCODE -ne 0) { throw "PyInstaller 빌드 실패" }

Write-Host "빌드 완료: dist\Tube Vocal Removal\Tube Vocal Removal.exe"
