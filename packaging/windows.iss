#ifndef AppVersion
  #error Pass /DAppVersion=<version> when compiling this installer.
#endif
#define RepoRoot AddBackslash(SourcePath) + ".."

[Setup]
AppId={{6B2793DE-9136-42A5-BF2E-C05AD776517B}
AppName=Cyber Atlas
AppVersion={#AppVersion}
VersionInfoVersion={#AppVersion}
DefaultDirName={localappdata}\Programs\Cyber Atlas
DefaultGroupName=Cyber Atlas
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
DisableProgramGroupPage=yes
OutputDir={#RepoRoot}\dist
OutputBaseFilename=CyberAtlas-{#AppVersion}-Setup
SetupIconFile={#RepoRoot}\assets\CyberAtlas.ico
UninstallDisplayIcon={app}\CyberAtlas.exe
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes
CloseApplicationsFilter=CyberAtlas.exe
RestartApplications=no

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; Flags: unchecked

[Files]
Source: "{#RepoRoot}\dist\CyberAtlas\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\Cyber Atlas"; Filename: "{app}\CyberAtlas.exe"; AppUserModelID: "CyberAtlas.Desktop"
Name: "{autodesktop}\Cyber Atlas"; Filename: "{app}\CyberAtlas.exe"; Tasks: desktopicon; AppUserModelID: "CyberAtlas.Desktop"

[Run]
Filename: "{app}\CyberAtlas.exe"; Description: "Open Cyber Atlas"; Flags: nowait postinstall skipifsilent

; User atlases and logs live outside {app}. Uninstall deliberately leaves them in place.
