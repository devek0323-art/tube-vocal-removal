param(
    [switch]$SkipTests,
    [switch]$Installer   # 정식 설치 파일과 업데이트 패치를 함께 만든다
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

if ($Installer) {
    $Candidates = @(
        (Join-Path $env:LOCALAPPDATA "Programs\Inno Setup 6\ISCC.exe"),
        "C:\Program Files (x86)\Inno Setup 6\ISCC.exe",
        "C:\Program Files\Inno Setup 6\ISCC.exe"
    )
    $Iscc = $Candidates | Where-Object { Test-Path $_ } | Select-Object -First 1
    if (-not $Iscc) { throw "ISCC.exe를 찾지 못했습니다. Inno Setup 6을 설치하세요." }

    $Script = Join-Path $Root "installer\TubeVocalRemoval.iss"

    # 정식 설치 파일과 패치는 같은 dist를 두 가지로 포장한 것이다. 항상 함께 만든다.
    & $Iscc $Script
    if ($LASTEXITCODE -ne 0) { throw "정식 설치 파일 생성 실패" }

    & $Iscc /DPATCH $Script
    if ($LASTEXITCODE -ne 0) { throw "업데이트 패치 생성 실패" }

    Write-Host ""
    Write-Host "release 폴더:"
    Get-ChildItem (Join-Path $Root "release\*.exe") | ForEach-Object {
        "{0,-46} {1,6:N0} MB" -f $_.Name, ($_.Length / 1MB)
    }
}
