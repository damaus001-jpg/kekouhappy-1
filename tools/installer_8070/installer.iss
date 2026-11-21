#ifndef StageDir
 #error StageDir is required
#endif
#ifndef ReleaseDir
 #error ReleaseDir is required
#endif
#ifndef AppVersion
 #error AppVersion is required
#endif
[Setup]
AppId={{7C9E926A-5F26-4BF4-A17E-D74080701800}
AppName=手机工作台 8070
AppVersion={#AppVersion}
AppPublisher=Phone Workbench
DefaultDirName={localappdata}\Programs\PhoneWorkbench8070
DefaultGroupName=手机工作台 8070
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
OutputDir={#ReleaseDir}
OutputBaseFilename=PhoneWorkbench8070-{#AppVersion}-Setup
Compression=lzma2/fast
SolidCompression=yes
LZMANumBlockThreads=2
LZMAUseSeparateProcess=yes
WizardStyle=modern
UninstallDisplayIcon={app}\PhoneWorkbench8070.exe
DisableProgramGroupPage=yes
CloseApplications=no
RestartApplications=no
SetupLogging=yes
[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"
[Tasks]
Name: "desktopicon"; Description: "创建桌面快捷方式"; Flags: checkedonce
[Files]
Source: "{#StageDir}\*"; DestDir: "{app}"; Excludes: "*.pyc,*.pyo,*.log"; Flags: ignoreversion recursesubdirs createallsubdirs
[Icons]
Name: "{group}\手机工作台 8070"; Filename: "{app}\PhoneWorkbench8070.exe"; WorkingDir: "{app}"; AppUserModelID: "PhoneWorkbench8070.Desktop"
Name: "{autodesktop}\手机工作台 8070"; Filename: "{app}\PhoneWorkbench8070.exe"; WorkingDir: "{app}"; Tasks: desktopicon; AppUserModelID: "PhoneWorkbench8070.Desktop"
Name: "{group}\后台管理"; Filename: "{app}\PhoneWorkbench8070.exe"; Parameters: "--backend-control"; WorkingDir: "{app}"
Name: "{group}\使用说明"; Filename: "{app}\使用说明.txt"
; No automatic launch or recursive user-data removal during uninstall.
