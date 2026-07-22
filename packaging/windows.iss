; Inno Setup script — build after PyInstaller:
;   iscc packaging\windows.iss
; Produces packaging\Output\JobEngine-Setup-<version>.exe

#define MyAppName "Job Engine"
#define MyAppVersion "0.6.1"
#define MyAppExeName "JobEngine.exe"

[Setup]
AppId={{8E1B6F0A-6A0C-4C86-9B58-0F3A7C21D4E9}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher=Abhinav B
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
OutputBaseFilename=JobEngine-Setup-{#MyAppVersion}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
Source: "..\dist\JobEngine\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#MyAppName}}"; Flags: nowait postinstall skipifsilent
