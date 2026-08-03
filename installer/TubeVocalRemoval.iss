; 정식 설치 파일과 업데이트 패치를 같은 스크립트로 만든다.
;   정식 : ISCC TubeVocalRemoval.iss
;   패치 : ISCC /DPATCH TubeVocalRemoval.iss
; 패치는 런타임(파이썬·CUDA)을 빼고 릴리스마다 바뀌는 것만 담는다.
; RuntimeRevision은 app/version.py의 RUNTIME_REVISION과 반드시 같아야 한다.
#define MyAppName "Tube Vocal Removal"
#define MyAppVersion "2.06"
#define MyRuntimeRevision "cu128-1"
#define MyAppPublisher "Tube Vocal Removal"
#define MyAppExeName "Tube Vocal Removal.exe"

[Setup]
AppId={{7E44419E-9B65-49F7-8B2A-CE04B50993A9}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppVerName={#MyAppName} v{#MyAppVersion}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
OutputDir=..\release
#ifdef PATCH
OutputBaseFilename=Tube-Vocal-Removal-Patch-{#MyRuntimeRevision}-v{#MyAppVersion}
VersionInfoDescription=Tube Vocal Removal 업데이트 패치
; 기존 설치 위치를 그대로 쓴다. 경로를 다시 묻지 않는다.
DisableDirPage=yes
UsePreviousAppDir=yes
#else
OutputBaseFilename=Tube-Vocal-Removal-Setup-v{#MyAppVersion}
VersionInfoDescription=Tube Vocal Removal 설치 프로그램
#endif
SetupIconFile=app-icon.ico
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequired=lowest
UninstallDisplayIcon={app}\{#MyAppExeName}
CloseApplications=yes
RestartApplications=no
VersionInfoVersion=2.0.5.0
VersionInfoCompany=Tube Vocal Removal
VersionInfoProductName=Tube Vocal Removal
VersionInfoProductVersion={#MyAppVersion}
VersionInfoCopyright=Copyright © 2026 Tube Vocal Removal

[Languages]
Name: "korean"; MessagesFile: "compiler:Languages\Korean.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Files]
#ifdef PATCH
; 릴리스마다 바뀌는 것만. runtime의 파이썬·CUDA 라이브러리는 그대로 둔다.
Source: "..\dist\Tube Vocal Removal\{#MyAppExeName}"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\dist\Tube Vocal Removal\runtime\app\*"; DestDir: "{app}\runtime\app"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\dist\Tube Vocal Removal\runtime\bin\*"; DestDir: "{app}\runtime\bin"; Flags: ignoreversion recursesubdirs createallsubdirs
#else
Source: "..\dist\Tube Vocal Removal\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
#endif

#ifndef PATCH
[Tasks]
Name: "desktopicon"; Description: "바탕 화면에 바로가기 만들기"; GroupDescription: "추가 바로가기:"

[InstallDelete]
; v2.01까지 사용한 PyInstaller 런타임 폴더. v2.02의 runtime 폴더와 중복되지 않게 제거한다.
Type: filesandordirs; Name: "{app}\_internal"
#endif

[Icons]
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
#ifndef PATCH
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon
#endif

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{#MyAppName} 실행"; Flags: nowait postinstall runasoriginaluser

#ifdef PATCH
[Code]
function InitializeSetup(): Boolean;
var
  Existing: String;
begin
  // 정식 설치본 위에만 얹을 수 있다. 없으면 안내하고 중단한다.
  Result := RegQueryStringValue(HKA, 'Software\Microsoft\Windows\CurrentVersion\Uninstall\{7E44419E-9B65-49F7-8B2A-CE04B50993A9}_is1', 'InstallLocation', Existing);
  if not Result then
    MsgBox('이 파일은 업데이트 패치입니다. 설치된 Tube Vocal Removal을 찾지 못했습니다.' + #13#10 +
           '정식 설치 파일(Setup)을 받아 실행해 주세요.', mbError, MB_OK);
end;
#endif
