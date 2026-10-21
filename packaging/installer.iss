; Script Inno Setup : crée apkg2cards-setup.exe à partir du dossier dist\apkg2cards
; La version est passée par la ligne de commande : ISCC /DMyAppVersion=0.4.0 installer.iss
#define MyAppName "apkg2cards"
#ifndef MyAppVersion
  #define MyAppVersion "0.0.0"
#endif
#define MyAppExe "apkg2cards.exe"

[Setup]
; Ne jamais changer l'AppId : c'est lui qui permet les mises à jour par-dessus l'installation.
AppId={{B7C2F6A4-3D1E-4B58-9A0C-5E2D7F9A1C64}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=..\installer
OutputBaseFilename=apkg2cards-setup
SetupIconFile=..\assets\icon.ico
UninstallDisplayIcon={app}\{#MyAppExe}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesInstallIn64BitMode=x64compatible
; Mise à jour automatique : l'application est fermée avant le remplacement des fichiers,
; puis relancée par l'entrée [Run] ci-dessous (paramètre /RELAUNCH=1).
CloseApplications=yes
RestartApplications=no

[Languages]
Name: "french"; MessagesFile: "compiler:Languages\French.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[CustomMessages]
french.DesktopIcon=Créer un raccourci sur le Bureau
english.DesktopIcon=Create a desktop shortcut
french.Shortcuts=Raccourcis :
english.Shortcuts=Shortcuts:
french.LaunchApp=Lancer apkg2cards
english.LaunchApp=Launch apkg2cards

[Tasks]
Name: "desktopicon"; Description: "{cm:DesktopIcon}"; GroupDescription: "{cm:Shortcuts}"

[Files]
Source: "..\dist\apkg2cards\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\{#MyAppExe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExe}"; Tasks: desktopicon

[Run]
; Installation classique : case « Lancer apkg2cards » à la fin de l'assistant.
Filename: "{app}\{#MyAppExe}"; Description: "{cm:LaunchApp}"; Flags: nowait postinstall skipifsilent
; Mise à jour automatique (installation silencieuse) : on relance directement l'application.
Filename: "{app}\{#MyAppExe}"; Flags: nowait; Check: RelaunchAfterUpdate

[Code]
function RelaunchAfterUpdate(): Boolean;
begin
  Result := ExpandConstant('{param:RELAUNCH|0}') = '1';
end;
