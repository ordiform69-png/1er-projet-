; Installateur Windows sans droits administrateur.
; Fabriqué seulement dans GitHub Actions (Inno Setup). Pas une dépendance du logiciel.

#define AppName "VHS Restore AI"
#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif

[Setup]
AppId={{A7C3E1B2-4D58-4F0A-9B11-6E5D4C3B2A19}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher=VHS Restore AI
DefaultDirName={localappdata}\Programs\VHS Restore AI
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputBaseFilename=VHSRestoreAI-Setup-{#AppVersion}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
SetupIconFile=vhs_restore\assets\icon.ico
UninstallDisplayIcon={app}\VHSRestoreAI.exe
CloseApplications=yes

[Languages]
Name: "french"; MessagesFile: "compiler:Languages\French.isl"

[Tasks]
Name: "desktopicon"; Description: "Icône sur le Bureau"; GroupDescription: "Raccourcis :"; Flags: checkedonce

[Files]
Source: "dist\VHSRestoreAI\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{userprograms}\{#AppName}"; Filename: "{app}\VHSRestoreAI.exe"
Name: "{userdesktop}\{#AppName}"; Filename: "{app}\VHSRestoreAI.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\VHSRestoreAI.exe"; Description: "Ouvrir VHS Restore AI"; Flags: nowait postinstall skipifsilent
