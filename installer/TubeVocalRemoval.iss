#define MyAppName "Tube Vocal Removal"
#define MyAppVersion "2.04"
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
OutputBaseFilename=Tube-Vocal-Removal-Setup-v{#MyAppVersion}
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
VersionInfoVersion=2.0.4.0
VersionInfoCompany=Tube Vocal Removal
VersionInfoDescription=Tube Vocal Removal 설치 프로그램
VersionInfoProductName=Tube Vocal Removal
VersionInfoProductVersion=2.04
VersionInfoCopyright=Copyright © 2026 Tube Vocal Removal

[Languages]
Name: "korean"; MessagesFile: "compiler:Languages\Korean.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "바탕 화면에 바로가기 만들기"; GroupDescription: "추가 바로가기:"

[Files]
Source: "..\dist\Tube Vocal Removal\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[InstallDelete]
; v2.01까지 사용한 PyInstaller 런타임 폴더. v2.02의 runtime 폴더와 중복되지 않게 제거한다.
Type: filesandordirs; Name: "{app}\_internal"

[Icons]
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{#MyAppName} 실행"; Flags: nowait postinstall runasoriginaluser
