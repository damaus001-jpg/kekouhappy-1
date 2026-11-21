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
#ifdef HostOnly
UninstallDisplayIcon={app}\runtime\python.exe
#else
UninstallDisplayIcon={app}\PhoneWorkbench8070.exe
#endif
DisableProgramGroupPage=yes
CloseApplications=no
RestartApplications=no
SetupLogging=yes
[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"
[Tasks]
#ifndef HostOnly
Name: "desktopicon"; Description: "创建桌面快捷方式"; Flags: checkedonce
#endif
[Files]
Source: "{#StageDir}\*"; DestDir: "{app}"; Excludes: "*.pyc,*.pyo,*.log"; Flags: ignoreversion recursesubdirs createallsubdirs
[Icons]
#ifndef HostOnly
Name: "{group}\手机工作台 8070"; Filename: "{app}\PhoneWorkbench8070.exe"; WorkingDir: "{app}"; AppUserModelID: "PhoneWorkbench8070.Desktop"
Name: "{autodesktop}\手机工作台 8070"; Filename: "{app}\PhoneWorkbench8070.exe"; WorkingDir: "{app}"; Tasks: desktopicon; AppUserModelID: "PhoneWorkbench8070.Desktop"
Name: "{group}\后台管理"; Filename: "{app}\PhoneWorkbench8070.exe"; Parameters: "--backend-control"; WorkingDir: "{app}"
Name: "{group}\使用说明"; Filename: "{app}\使用说明.txt"
#endif
#ifdef HostOnly
[Registry]
Root: HKCU64; Subkey: "Software\PhoneWorkbench8070"; ValueType: string; ValueName: "InstallDir"; ValueData: "{app}"; Flags: uninsdeletekey
Root: HKCU64; Subkey: "Software\PhoneWorkbench8070"; ValueType: string; ValueName: "Version"; ValueData: "{#AppVersion}"
Root: HKCU64; Subkey: "Software\PhoneWorkbench8070"; ValueType: dword; ValueName: "ControlProtocol"; ValueData: "1"
[InstallDelete]
; Fixed legacy program paths only; business data lives outside this client folder.
Type: filesandordirs; Name: "{app}\client"
Type: files; Name: "{app}\PhoneWorkbench8070.exe"
Type: files; Name: "{app}\BackendControl.pyw"
Type: files; Name: "{app}\BackendControl.cmd"
Type: files; Name: "{app}\Start.ps1"
Type: files; Name: "{userdesktop}\手机工作台 8070.lnk"
Type: files; Name: "{userprograms}\手机工作台 8070\手机工作台 8070.lnk"
Type: files; Name: "{userprograms}\手机工作台 8070\后台管理.lnk"
Type: files; Name: "{userprograms}\手机工作台 8070\使用说明.lnk"
#endif
; No automatic launch or recursive user-data removal during uninstall.
