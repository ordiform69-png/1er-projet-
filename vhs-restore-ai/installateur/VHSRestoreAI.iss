; Programme d'installation de VHS Restore AI (Inno Setup 6). Fabriqué par scripts\installateur.ps1.
; Pour le père (76 ans) : un double-clic, « Installer », et une icône « VHS Restore AI » sur le
; bureau. Sans droits d'administrateur, dans le profil (%LOCALAPPDATA%\Programs). Une nouvelle
; version s'installe par-dessus l'ancienne ; les outils installés depuis le logiciel et les
; réglages (profil de l'utilisateur) sont gardés.

#ifndef Version
  #define Version "1.0"
#endif
#ifndef Source
  #define Source "..\dist\VHSRestoreAI"
#endif
#ifndef Sortie
  #define Sortie "..\livraison"
#endif
#ifndef NomSortie
  #define NomSortie "Installer-VHS-Restore-AI"
#endif
#ifndef Icone
  #define Icone "..\vhs_restore\assets\VHSRestoreAI.ico"
#endif

[Setup]
AppId={{8E1C3A52-6F0B-4C1D-9B7E-2D5A4F3C9E11}
AppName=VHS Restore AI
AppVersion={#Version}
AppVerName=VHS Restore AI
AppPublisher=VHS Restore AI
DefaultDirName={localappdata}\Programs\VHS Restore AI
DefaultGroupName=VHS Restore AI
DisableDirPage=yes
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir={#Sortie}
OutputBaseFilename={#NomSortie}
SetupIconFile={#Icone}
UninstallDisplayIcon={app}\VHSRestoreAI.exe
UninstallDisplayName=VHS Restore AI
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
CloseApplications=yes
RestartApplications=no
ShowLanguageDialog=no

[Languages]
Name: "fr"; MessagesFile: "compiler:Languages\French.isl"

[InstallDelete]
; Les fichiers d'une version précédente ne se mélangent pas à ceux de la nouvelle.
Type: filesandordirs; Name: "{app}\_internal"

[Files]
Source: "{#Source}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autodesktop}\VHS Restore AI"; Filename: "{app}\VHSRestoreAI.exe"; WorkingDir: "{app}"
Name: "{autoprograms}\VHS Restore AI"; Filename: "{app}\VHSRestoreAI.exe"; WorkingDir: "{app}"

[Run]
Filename: "{app}\VHSRestoreAI.exe"; Description: "Ouvrir VHS Restore AI maintenant"; Flags: nowait postinstall skipifsilent
