; Inno Setup script for the Windows installer. Run after PyInstaller:
;   iscc /DAppVersion=0.1.2 packaging\fetchly.iss
#ifndef AppVersion
  #define AppVersion "0.1.2"
#endif

[Setup]
AppId={{6C1E7A43-3B8E-4C5F-9A57-F37C0E5D2B11}
AppName=Fetchly
AppVersion={#AppVersion}
AppPublisher=Fetchly
DefaultDirName={autopf}\Fetchly
DefaultGroupName=Fetchly
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
OutputDir=..\dist
OutputBaseFilename=Fetchly-Windows-Setup
SetupIconFile=fetchly.ico
UninstallDisplayIcon={app}\Fetchly.exe
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Shortcuts:"

[Files]
Source: "..\dist\Fetchly\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\Fetchly"; Filename: "{app}\Fetchly.exe"
Name: "{autodesktop}\Fetchly"; Filename: "{app}\Fetchly.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\Fetchly.exe"; Description: "Launch Fetchly"; Flags: nowait postinstall skipifsilent
