; 런타임(파이썬·CUDA)을 뺀 패치 설치 파일. app/version.py의 RUNTIME_REVISION이 같은
; 기존 설치본 위에만 덮어쓴다. 런타임이 바뀐 릴리스는 정식 설치 파일을 써야 한다.
#define MyAppName "Tube Vocal Removal"
#define MyAppVersion "2.04"
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
DisableDirPage=yes
OutputDir=..\release
OutputBaseFilename=Tube-Vocal-Removal-Patch-{#MyRuntimeRevision}-v{#MyAppVersion}
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
; 기존 설치본이 없으면 패치를 적용할 수 없다.
UsePreviousAppDir=yes
VersionInfoVersion=2.0.4.0
VersionInfoCompany=Tube Vocal Removal
VersionInfoDescription=Tube Vocal Removal 업데이트 패치
VersionInfoProductName=Tube Vocal Removal
VersionInfoProductVersion=2.04
VersionInfoCopyright=Copyright © 2026 Tube Vocal Removal

[Languages]
Name: "korean"; MessagesFile: "compiler:Languages\Korean.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Files]
; 릴리스마다 바뀌는 것만 담는다. runtime의 파이썬·CUDA 라이브러리는 제외한다.
Source: "..\dist\Tube Vocal Removal\{#MyAppExeName}"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\dist\Tube Vocal Removal\runtime\app\*"; DestDir: "{app}\runtime\app"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\dist\Tube Vocal Removal\runtime\bin\*"; DestDir: "{app}\runtime\bin"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{#MyAppName} 실행"; Flags: nowait postinstall runasoriginaluser

[Code]
function InitializeSetup(): Boolean;
var
  Existing: String;
begin
  // 정식 설치본이 있어야 패치를 얹을 수 있다. 없으면 안내하고 중단한다.
  Result := RegQueryStringValue(HKA, 'Software\Microsoft\Windows\CurrentVersion\Uninstall\{7E44419E-9B65-49F7-8B2A-CE04B50993A9}_is1', 'InstallLocation', Existing);
  if not Result then
    MsgBox('이 파일은 업데이트 패치입니다. 설치된 Tube Vocal Removal을 찾지 못했습니다.' + #13#10 +
           '정식 설치 파일(Setup)을 받아 실행해 주세요.', mbError, MB_OK);
end;
