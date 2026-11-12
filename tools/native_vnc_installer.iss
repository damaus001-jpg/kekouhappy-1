#ifndef StageDir
  #error StageDir is required
#endif
#ifndef ReleaseDir
  #error ReleaseDir is required
#endif
#ifndef AppVersion
  #define AppVersion "0.1.6"
#endif

[Setup]
AppId={{AC8C7AE1-0C73-4989-B9F4-4A3F72B40760}
AppName=手机群控 VNC
AppVersion={#AppVersion}
AppPublisher=Phone Workbench
DefaultDirName={localappdata}\Programs\PhoneWorkbench
DefaultGroupName=手机群控 VNC
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
OutputDir={#ReleaseDir}
OutputBaseFilename=PhoneWorkbench-{#AppVersion}-Setup
Compression=lzma2/fast
SolidCompression=yes
LZMANumBlockThreads=2
LZMAUseSeparateProcess=yes
WizardStyle=modern
UninstallDisplayIcon={app}\PhoneWorkbench.exe
DisableProgramGroupPage=yes
CloseApplications=no
RestartApplications=no
SetupLogging=yes

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "创建桌面快捷方式"; Flags: checkedonce

[Files]
Source: "{#StageDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\手机群控 VNC"; Filename: "{app}\PhoneWorkbench.exe"; WorkingDir: "{app}"
Name: "{autodesktop}\手机群控 VNC"; Filename: "{app}\PhoneWorkbench.exe"; WorkingDir: "{app}"; Tasks: desktopicon
Name: "{group}\使用说明"; Filename: "{app}\使用说明.txt"

; Do not automatically launch: the development client may already own phones.
