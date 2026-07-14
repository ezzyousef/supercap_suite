; Inno Setup script for the Supercapacitor & DSC Analysis Suite.
;
; Wraps the standalone PyInstaller build (dist\SupercapSuite\, an
; onedir build -- SupercapSuite.exe plus every bundled dependency as
; loose files in that folder; no Python or anything else needs to be
; installed on the target PC) into a normal Windows installer: Start
; Menu shortcut, optional Desktop shortcut, Add/Remove Programs entry,
; and a proper uninstaller.
;
; Deliberately onedir, not onefile: onefile re-extracts its entire
; bundled runtime to a fresh %TEMP% folder on EVERY launch, which is a
; well-documented cause of flaky/slow startup (antivirus real-time
; scanning the newly-written payload each time) -- onedir extracts once,
; here, at install time.
;
; Build with (from this "installer" folder, or point ISCC at this file
; directly -- see build_installer.ps1 in this folder for the one-command
; version):
;     "C:\Users\<you>\AppData\Local\Programs\Inno Setup 6\ISCC.exe" SupercapSuite.iss
;
; Requires dist\SupercapSuite\ to already exist -- run
; `pyinstaller SupercapSuite.spec` from the project root first (or run
; build_installer.ps1, which does both steps).

#define MyAppName "Supercapacitor & DSC Analysis Suite"
#define MyAppVersion "1.0.0"
#define MyAppPublisher "Ezzeldien Yousef"
#define MyAppURL "mailto:ezzyousef2@aucegypt.edu"
#define MyAppExeName "SupercapSuite.exe"
#define MyAppCopyright "Copyright (C) 2026 Ezzeldien Yousef"

[Setup]
; Fixed AppId (a GUID) so future versions upgrade in place instead of
; installing side by side -- generated once for this app, keep it stable.
AppId={{6E4B6E6D-6E6B-4D6B-9D42-2D6C6D5E9A21}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppCopyright={#MyAppCopyright}
DefaultDirName={autopf}\SupercapSuite
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
OutputDir=output
OutputBaseFilename=SupercapSuiteSetup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesInstallIn64BitMode=x64compatible
UninstallDisplayIcon={app}\{#MyAppExeName}
SetupIconFile=..\assets\app_icon.ico

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
; The whole onedir build folder (SupercapSuite.exe + every bundled DLL/
; data file it needs at runtime), recursively -- NOT just the exe.
Source: "..\dist\SupercapSuite\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\assets\app_icon.ico"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\README.md"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\COPYRIGHT.txt"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\docs\EQUATIONS.md"; DestDir: "{app}\docs"; Flags: ignoreversion

[Icons]
; IconFilename is set explicitly (not just relying on the exe's own
; embedded icon) so the Start Menu and Desktop shortcuts show the EML
; badge icon reliably even if Windows' shortcut-icon cache is stale.
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\app_icon.ico"
Name: "{group}\{cm:UninstallProgram,{#MyAppName}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\app_icon.ico"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent
