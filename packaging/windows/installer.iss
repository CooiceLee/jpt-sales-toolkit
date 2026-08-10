#ifndef AppVersion
  #define AppVersion "0.11.8-internal"
#endif
#ifndef SourceDir
  #define SourceDir "..\..\dist\JPT Sales Toolkit"
#endif
#ifndef OutputDir
  #define OutputDir "..\..\release"
#endif
#ifndef OutputBaseFilename
  #define OutputBaseFilename "JPT-Sales-Toolkit-0.11.8-internal-Windows-x64-UNSIGNED-INTERNAL-Setup"
#endif
#ifndef VersionInfoVersion
  #define VersionInfoVersion "0.11.8.0"
#endif

[Setup]
AppId={{9A616D60-2231-47A5-88CF-4D0735376638}
AppName=JPT Sales Toolkit
AppVersion={#AppVersion}
AppVerName=JPT Sales Toolkit {#AppVersion}
AppPublisher=JPT
DefaultDirName={localappdata}\Programs\JPT Sales Toolkit
DefaultGroupName=JPT Sales Toolkit
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir={#OutputDir}
OutputBaseFilename={#OutputBaseFilename}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes
RestartApplications=no
UninstallDisplayIcon={app}\JPT Sales Toolkit.exe
VersionInfoVersion={#VersionInfoVersion}

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Additional shortcuts:"; Flags: unchecked

[Files]
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\JPT Sales Toolkit"; Filename: "{app}\JPT Sales Toolkit.exe"
Name: "{autodesktop}\JPT Sales Toolkit"; Filename: "{app}\JPT Sales Toolkit.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\JPT Sales Toolkit.exe"; Description: "Launch JPT Sales Toolkit"; Flags: nowait postinstall skipifsilent
