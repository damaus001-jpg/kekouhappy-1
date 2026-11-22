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
AppName={cm:AppTitle}
AppVersion={#AppVersion}
AppPublisher=Pikachu
DefaultDirName={localappdata}\Programs\PikachuPhoneWorkbench
DefaultGroupName={cm:AppTitle}
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
OutputDir={#ReleaseDir}
OutputBaseFilename=皮卡丘手机工作台-{#AppVersion}-安装
Compression=lzma2/fast
SolidCompression=yes
LZMANumBlockThreads=2
LZMAUseSeparateProcess=yes
WizardStyle=modern dark hidebevels includetitlebar
WizardSizePercent=110,100
WizardImageFile=assets\wizard.bmp
WizardSmallImageFile=assets\pikachu-brand.png
WizardSmallImageBackColor=#171219
SetupIconFile=assets\pikachu.ico
UninstallDisplayName={cm:AppTitle}
DisableWelcomePage=no
DisableDirPage=no
DisableReadyPage=yes
ShowLanguageDialog=yes
LanguageDetectionMethod=uilanguage
#ifdef HostOnly
UninstallDisplayIcon={app}\workbench.ico
#else
UninstallDisplayIcon={app}\PhoneWorkbench8070.exe
#endif
DisableProgramGroupPage=yes
CloseApplications=no
RestartApplications=no
SetupLogging=yes
[Languages]
Name: "chinesesimp"; MessagesFile: "compiler:Default.isl,Chinese.isl"
Name: "english"; MessagesFile: "compiler:Default.isl,English.isl"
[Tasks]
#ifndef HostOnly
Name: "desktopicon"; Description: "创建桌面快捷方式"; Flags: checkedonce
#endif
[Files]
Source: "assets\pikachu.ico"; DestDir: "{app}"; DestName: "workbench.ico"; Flags: ignoreversion
Source: "{#StageDir}\*"; DestDir: "{app}"; Excludes: "*.pyc,*.pyo,*.log"; Flags: ignoreversion recursesubdirs createallsubdirs
[Icons]
#ifndef HostOnly
Name: "{group}\皮卡丘手机工作台"; Filename: "{app}\PhoneWorkbench8070.exe"; WorkingDir: "{app}"; AppUserModelID: "PhoneWorkbench8070.Desktop"
Name: "{autodesktop}\皮卡丘手机工作台"; Filename: "{app}\PhoneWorkbench8070.exe"; WorkingDir: "{app}"; Tasks: desktopicon; AppUserModelID: "PhoneWorkbench8070.Desktop"
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

[Code]
var
  ProgressText: TNewStaticText;
  ProgressTrack, ProgressFill: TPanel;
  NextFace, BackFace, CancelFace, BrowseFace: TPanel;

procedure ThemeText(Control: TControl);
var
  I: Integer;
begin
  Control.StyleElements := Control.StyleElements - [seFont];
  if Control is TNewStaticText then begin
    TNewStaticText(Control).Font.Color := $00B670FF;
    TNewStaticText(Control).Font.Name := CustomMessage('UIFont');
  end;
  if Control is TNewButton then
    TNewButton(Control).Font.Color := $00B670FF;
  if Control is TWinControl then
    for I := 0 to TWinControl(Control).ControlCount - 1 do
      ThemeText(TWinControl(Control).Controls[I]);
end;

procedure ThemeButtonClick(Sender: TObject);
begin
  if Sender = NextFace then
    PostMessage(WizardForm.NextButton.Handle, $00F5, 0, 0)
  else if Sender = BackFace then
    PostMessage(WizardForm.BackButton.Handle, $00F5, 0, 0)
  else if Sender = CancelFace then
    PostMessage(WizardForm.CancelButton.Handle, $00F5, 0, 0)
  else if Sender = BrowseFace then
    PostMessage(WizardForm.DirBrowseButton.Handle, $00F5, 0, 0);
end;

function ButtonCaption(Value: String): String;
begin
  StringChangeEx(Value, '&', '', True);
  Result := Value;
end;

function ButtonFace(Button: TNewButton; Primary: Boolean): TPanel;
begin
  Result := TPanel.Create(WizardForm);
  Result.Parent := Button.Parent;
  Result.SetBounds(Button.Left, Button.Top, Button.Width, Button.Height);
  Result.StyleElements := [];
  Result.BevelOuter := bvNone;
  Result.Color := $00191217;
  Result.Font.Name := CustomMessage('UIFont');
  Result.Font.Color := $00B670FF;
  Result.Font.Size := 10;
  Result.Caption := ButtonCaption(Button.Caption);
  Result.Cursor := crHand;
  Result.TabStop := False;
  Result.OnClick := @ThemeButtonClick;
  if Primary then begin
    Result.Color := $00B670FF;
    Result.Font.Color := $00191217;
    Result.Font.Style := [fsBold];
  end;
end;

procedure RefreshButtons;
begin
  NextFace.Visible := WizardForm.NextButton.Visible;
  NextFace.Enabled := WizardForm.NextButton.Enabled;
  NextFace.Caption := ButtonCaption(WizardForm.NextButton.Caption);
  BackFace.Visible := WizardForm.BackButton.Visible;
  BackFace.Enabled := WizardForm.BackButton.Enabled;
  BackFace.Caption := ButtonCaption(WizardForm.BackButton.Caption);
  CancelFace.Visible := WizardForm.CancelButton.Visible;
  CancelFace.Enabled := WizardForm.CancelButton.Enabled;
  CancelFace.Caption := ButtonCaption(WizardForm.CancelButton.Caption);
  BrowseFace.Caption := ButtonCaption(WizardForm.DirBrowseButton.Caption);
end;

#ifdef UIPreview
function PrepareToInstall(var NeedsRestart: Boolean): String;
begin
  Result := CustomMessage('PreviewOnly');
end;
#endif

procedure InitializeWizard;
begin
  WizardForm.Color := $00191217;
  WizardForm.StyleElements := [seBorder];
  WizardForm.MainPanel.Color := $00191217;
  WizardForm.MainPanel.StyleElements := [];
  WizardForm.Font.Name := CustomMessage('UIFont');
  WizardForm.WelcomePage.Color := $00191217;
  WizardForm.FinishedPage.Color := $00191217;
  WizardForm.WelcomePage.StyleElements := [];
  WizardForm.FinishedPage.StyleElements := [];
  WizardForm.InnerPage.Color := $00191217;
  WizardForm.Font.Color := $00B670FF;
  WizardForm.WelcomeLabel1.Font.Color := $00B670FF;
  WizardForm.WelcomeLabel1.Font.Name := CustomMessage('UIFont');
  WizardForm.WelcomeLabel1.Font.Size := 23;
  WizardForm.WelcomeLabel1.Font.Style := [fsBold];
  WizardForm.WelcomeLabel2.Font.Size := 11;
  WizardForm.WelcomeLabel2.Font.Name := CustomMessage('UIFont');
  WizardForm.WelcomeLabel2.Font.Color := $00B670FF;
  WizardForm.FinishedHeadingLabel.Font.Size := 21;
  WizardForm.FinishedHeadingLabel.Font.Name := CustomMessage('UIFont');
  WizardForm.FinishedHeadingLabel.Font.Color := $00B670FF;
  WizardForm.FinishedLabel.Font.Size := 11;
  WizardForm.FinishedLabel.Font.Name := CustomMessage('UIFont');
  WizardForm.FinishedLabel.Font.Color := $00B670FF;
  WizardForm.PageNameLabel.Font.Color := $00B670FF;
  WizardForm.PageNameLabel.Font.Size := 13;
  WizardForm.PageDescriptionLabel.Font.Color := $00B670FF;
  WizardForm.ReadyMemo.Color := $00191217;
  WizardForm.DirEdit.Color := $00191217;
  WizardForm.DirEdit.Font.Color := $00B670FF;
  WizardForm.SelectDirBitmapImage.Visible := False;
  WizardForm.FilenameLabel.Visible := False;
  ProgressText := TNewStaticText.Create(WizardForm);
  ProgressText.Parent := WizardForm.InstallingPage;
  ProgressText.Left := WizardForm.ProgressGauge.Left;
  ProgressText.Top := WizardForm.ProgressGauge.Top + WizardForm.ProgressGauge.Height + ScaleY(16);
  ProgressText.Width := WizardForm.ProgressGauge.Width;
  ProgressText.Height := ScaleY(28);
  ProgressText.Font.Size := 12;
  ProgressText.Font.Color := $00B670FF;
  ProgressTrack := TPanel.Create(WizardForm);
  ProgressTrack.Parent := WizardForm.InstallingPage;
  ProgressTrack.SetBounds(WizardForm.ProgressGauge.Left, WizardForm.ProgressGauge.Top,
    WizardForm.ProgressGauge.Width, WizardForm.ProgressGauge.Height);
  ProgressTrack.BevelOuter := bvNone;
  ProgressTrack.StyleElements := [];
  ProgressTrack.Color := $00322330;
  ProgressFill := TPanel.Create(WizardForm);
  ProgressFill.Parent := ProgressTrack;
  ProgressFill.SetBounds(0, 0, 0, ProgressTrack.Height);
  ProgressFill.BevelOuter := bvNone;
  ProgressFill.StyleElements := [];
  ProgressFill.Color := $00B670FF;
  WizardForm.ProgressGauge.Visible := False;
  ThemeText(WizardForm);
  NextFace := ButtonFace(WizardForm.NextButton, True);
  BackFace := ButtonFace(WizardForm.BackButton, False);
  CancelFace := ButtonFace(WizardForm.CancelButton, False);
  BrowseFace := ButtonFace(WizardForm.DirBrowseButton, False);
end;

procedure CurPageChanged(CurPageID: Integer);
begin
  if CurPageID = wpSelectDir then
    WizardForm.NextButton.Caption := SetupMessage(msgButtonInstall)
  else if CurPageID = wpWelcome then
    WizardForm.NextButton.Caption := SetupMessage(msgButtonNext);
  RefreshButtons;
end;

procedure CurInstallProgressChanged(CurProgress, MaxProgress: Integer);
begin
  if MaxProgress > 0 then begin
    ProgressText.Caption := Format(CustomMessage('ProgressFormat'), [Round(100.0 * CurProgress / MaxProgress)]);
    ProgressFill.Width := Round(1.0 * ProgressTrack.Width * CurProgress / MaxProgress);
  end;
  RefreshButtons;
end;
