; Inno Setup script — build after PyInstaller:
;   iscc packaging\windows.iss
; Produces packaging\Output\JobEngine-Setup-<version>.exe

#define MyAppName "Job Engine"
#define MyAppVersion "0.8.0"
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
; --- 008 (FR-031): unattended-upgrade hardening ---
; desktop.py holds this named mutex for its whole lifetime, so Setup (incl.
; /VERYSILENT self-updates) reliably detects and closes a running instance
; instead of hitting in-use files mid-copy.
AppMutex=JobEngineRunning
CloseApplications=yes
; RestartApplications needs RegisterApplicationRestart (PyInstaller apps
; don't call it) — relaunch happens via the [Run] entry below instead.
RestartApplications=no
; Stamp the version into the installer's file properties so on-disk
; artifacts are identifiable (audit: no version resource anywhere).
VersionInfoVersion={#MyAppVersion}

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[InstallDelete]
; PyInstaller onedir payloads change file sets between releases; stale DLLs
; from a previous version in {app}\_internal cause mixed-version breakage.
Type: filesandordirs; Name: "{app}\_internal"

[Files]
Source: "..\dist\JobEngine\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#MyAppName}}"; Flags: nowait postinstall skipifsilent
; 008 self-update relaunch: the app launches the installer with /STARTAPP=1
; and exits; this entry restarts it after a silent upgrade.
Filename: "{app}\{#MyAppExeName}"; Flags: nowait; Check: StartAppRequested

[Code]
function StartAppRequested: Boolean;
begin
  Result := ExpandConstant('{param:STARTAPP|0}') = '1';
end;
