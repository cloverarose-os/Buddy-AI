; BuddyAI.iss - Inno Setup script for the Buddy AI graphical Windows installer.
; Compile with Inno Setup 6+ (ISCC.exe BuddyAI.iss). Produces:
;   Output\BuddyAI-Setup-v0.1.0-alpha.exe
;
; The heavy lifting (downloads, prereqs, models, config, shortcuts) is done by
; the PowerShell scripts in installer\scripts, which are bundled and invoked
; from [Code]. This keeps the logic testable and reusable for a future OS.

#define AppName "Buddy AI"
#define AppVersion "0.1.0-alpha"
#define AppPublisher "Clover Rose"
#define AppURL "https://github.com/cloverarose-os/Buddy-AI"

[Setup]
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
AppPublisherURL={#AppURL}
DefaultDirName=C:\BuddyAI
DisableProgramGroupPage=yes
DisableDirPage=no
OutputDir=Output
OutputBaseFilename=BuddyAI-Setup-v{#AppVersion}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
; Prereqs/models need admin for silent installs + writing to arbitrary drives.
PrivilegesRequired=admin
UninstallDisplayName={#AppName} {#AppVersion}

[Files]
; Bundle the app code (payload) and the installer scripts/tools. These land in
; {app}\_installer temporarily; the code is copied into the final layout by the
; [Code] section, and _installer is removed at the end.
Source: "payload\*"; DestDir: "{app}\_installer\payload"; Flags: recursesubdirs ignoreversion
Source: "scripts\*"; DestDir: "{app}\_installer\scripts"; Flags: ignoreversion
Source: "tools\*";   DestDir: "{app}\_installer\tools";   Flags: ignoreversion
Source: "models.manifest.json"; DestDir: "{app}\_installer"; Flags: ignoreversion

[Code]
var
  InstallTypePage: TInputOptionWizardPage;
  BrainUrlPage: TInputQueryWizardPage;
  OptionsPage: TInputOptionWizardPage;

procedure InitializeWizard;
begin
  { --- Install type page --- }
  InstallTypePage := CreateInputOptionPage(wpWelcome,
    'Install Type', 'How should Buddy be installed on this machine?',
    'Choose whether this machine runs the full Buddy stack, or only the companion talking to a Buddy brain on another machine.',
    True, False);
  InstallTypePage.Add('Full install (this machine runs everything: companion, brain, watchdog, models)');
  InstallTypePage.Add('Companion only (this machine shows the pet; the brain runs on another machine)');
  InstallTypePage.SelectedValueIndex := 0;

  { --- Brain endpoint page (companion-only) --- }
  BrainUrlPage := CreateInputQueryPage(InstallTypePage.ID,
    'Brain Endpoint', 'Where is the Buddy brain?',
    'Enter the address of the machine running the Buddy brain. Use the LAN address or a tunnel DNS name. Include the port (default 8766).');
  BrainUrlPage.Add('Brain URL:', False);
  BrainUrlPage.Values[0] := 'http://localhost:8766';

  { --- Options page (full install) --- }
  OptionsPage := CreateInputOptionPage(wpSelectDir,
    'Options', 'Choose components and behavior',
    'These can be changed later by editing buddy_config.json or re-running the installer.',
    False, False);
  OptionsPage.Add('Enable Home Assistant endpoint');
  OptionsPage.Add('Install the GPU Watchdog (frees the GPU for games)');
  OptionsPage.Add('Start Buddy automatically with Windows');
  OptionsPage.Add('Create desktop shortcuts');
  OptionsPage.Values[0] := True;
  OptionsPage.Values[1] := True;
  OptionsPage.Values[2] := True;
  OptionsPage.Values[3] := True;
end;

function IsCompanion: Boolean;
begin
  Result := (InstallTypePage.SelectedValueIndex = 1);
end;

function ShouldSkipPage(PageID: Integer): Boolean;
begin
  Result := False;
  { brain URL only for companion-only installs }
  if PageID = BrainUrlPage.ID then
    Result := not IsCompanion;
  { options only for full installs }
  if PageID = OptionsPage.ID then
    Result := IsCompanion;
end;

function RunHidden(Cmd: String): Integer;
var
  ResultCode: Integer;
begin
  Exec(ExpandConstant('{cmd}'), '/C ' + Cmd, '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
  Result := ResultCode;
end;

function PsScript(Name: String): String;
begin
  Result := ExpandConstant('{app}\_installer\scripts\') + Name;
end;

{ Run a bundled PowerShell script with args, visibly (so the user sees progress). }
function RunPs(ScriptName, Args: String; Wait: Boolean): Integer;
var
  ResultCode: Integer;
  Cmd: String;
begin
  Cmd := '-ExecutionPolicy Bypass -NoProfile -File "' + PsScript(ScriptName) + '" ' + Args;
  if Wait then
    Exec('powershell.exe', Cmd, '', SW_SHOW, ewWaitUntilTerminated, ResultCode)
  else
    Exec('powershell.exe', Cmd, '', SW_SHOW, ewNoWait, ResultCode);
  Result := ResultCode;
end;

{ Preflight runs when leaving the options/brain page, before the Ready page.
  It blocks progress if disk space is insufficient. }
function NextButtonClick(CurPageID: Integer): Boolean;
var
  InstallerDir, Root, ITypeStr, OutFile: String;
  PfJson: AnsiString;
  RC: Integer;
begin
  Result := True;
  { run preflight right before the Ready-to-install page }
  if CurPageID = wpReady then
  begin
    InstallerDir := ExpandConstant('{app}\_installer');
    Root := ExpandConstant('{app}');
    if IsCompanion then ITypeStr := 'companion' else ITypeStr := 'full';
    OutFile := ExpandConstant('{tmp}\buddy_preflight.json');
    RC := RunPs('Preflight.ps1',
      '-InstallerDir "' + InstallerDir + '" -Root "' + Root + '" -InstallType ' + ITypeStr +
      ' -OutFile "' + OutFile + '"', True);
    if LoadStringFromFile(OutFile, PfJson) then
    begin
      { crude check: if the JSON says ok:false, warn and block }
      if Pos('"ok":  false', PfJson) > 0 then
      begin
        MsgBox('Preflight found a blocking problem (likely not enough disk space):' + #13#10#13#10 +
          PfJson, mbError, MB_OK);
        Result := False;
      end
      else if (Pos('"warnings":', PfJson) > 0) and (Pos('GPU', PfJson) > 0) then
      begin
        if MsgBox('Preflight warnings were found (e.g. GPU/VRAM). Buddy may still work but image/LLM generation could be slow or fail.' + #13#10#13#10 +
          'Continue anyway?', mbConfirmation, MB_YESNO) = IDNO then
          Result := False;
      end;
    end;
  end;
end;

{ Copy the app code from the bundled payload into the final component layout. }
procedure LayOutCode(Root: String);
var
  Pay: String;
begin
  Pay := Root + '\_installer\payload\';
  { companion always }
  ForceDirectories(Root + '\companion');
  CopyFile(Pay + 'companion\buddy.py',          Root + '\companion\buddy.py', False);
  CopyFile(Pay + 'companion\skin_highres.py',   Root + '\companion\skin_highres.py', False);
  CopyFile(Pay + 'companion\buddy_config.py',   Root + '\companion\buddy_config.py', False);
  { launchers always (companion-only still needs the pet launcher) }
  ForceDirectories(Root + '\launchers');
  { note: the payload\launchers folder is copied wholesale via a helper below }
  if not IsCompanion then
  begin
    ForceDirectories(Root + '\brain');
    CopyFile(Pay + 'brain\buddy_ai.py',        Root + '\brain\buddy_ai.py', False);
    CopyFile(Pay + 'brain\buddy_config.py',    Root + '\brain\buddy_config.py', False);
    ForceDirectories(Root + '\watchdog');
    CopyFile(Pay + 'watchdog\watchdog.py',         Root + '\watchdog\watchdog.py', False);
    CopyFile(Pay + 'watchdog\watchdog_config.json',Root + '\watchdog\watchdog_config.json', False);
    CopyFile(Pay + 'watchdog\buddy_config.py',     Root + '\watchdog\buddy_config.py', False);
  end;
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  Root, InstallerDir, ITypeStr, BrainUrl, Args: String;
  HAOn, WDOn, StartWin, Icons: Integer;
begin
  if CurStep <> ssPostInstall then Exit;

  Root := ExpandConstant('{app}');
  InstallerDir := Root + '\_installer';
  if IsCompanion then ITypeStr := 'companion' else ITypeStr := 'full';

  { 1. lay out the app code + copy the launchers folder wholesale }
  LayOutCode(Root);
  RunPs('CopyTree.ps1', '-Src "' + InstallerDir + '\payload\launchers" -Dst "' + Root + '\launchers"', True);

  { 2. prerequisites (full only): Python, Ollama, ComfyUI }
  if not IsCompanion then
    RunPs('InstallPrereqs.ps1', '-InstallerDir "' + InstallerDir + '" -Root "' + Root + '"', True);

  { 3. write buddy_config.json from the wizard choices }
  if IsCompanion then
    BrainUrl := BrainUrlPage.Values[0]
  else
    BrainUrl := 'http://localhost:8766';
  if OptionsPage.Values[0] then HAOn := 1 else HAOn := 0;
  if OptionsPage.Values[1] then WDOn := 1 else WDOn := 0;
  if OptionsPage.Values[2] then StartWin := 1 else StartWin := 0;
  if OptionsPage.Values[3] then Icons := 1 else Icons := 0;
  if IsCompanion then begin StartWin := 1; Icons := 1; end;

  Args := '-Root "' + Root + '" -InstallType ' + ITypeStr +
          ' -BrainUrl "' + BrainUrl + '" -HAEnabled ' + IntToStr(HAOn) +
          ' -WatchdogEnabled ' + IntToStr(WDOn);
  RunPs('WriteConfig.ps1', Args, True);

  { 4. models (full only): ComfyUI weights + Ollama pulls }
  if not IsCompanion then
    RunPs('DownloadModels.ps1',
      '-InstallerDir "' + InstallerDir + '" -Root "' + Root + '" -OllamaModels "' + Root + '\models\ollama"', True);

  { 5. shortcuts + startup }
  RunPs('InstallShortcuts.ps1',
    '-Root "' + Root + '" -InstallType ' + ITypeStr +
    ' -DesktopIcons ' + IntToStr(Icons) + ' -StartWithWindows ' + IntToStr(StartWin), True);

  { 6. clean up the staging folder }
  DelTree(InstallerDir, True, True, True);
end;

procedure CurPageChanged(CurPageID: Integer);
var
  Msg: String;
begin
  if CurPageID = wpFinished then
  begin
    if (not IsCompanion) and OptionsPage.Values[0] then
    begin
      Msg := 'Home Assistant is enabled.' + #13#10 +
             'In Home Assistant, add the Ollama integration and point it at:' + #13#10 +
             '    URL:   http://<this-machine>:8766' + #13#10 +
             '    Model: buddy' + #13#10#13#10 +
             'See docs/ARCHITECTURE.md for the full steps.';
      WizardForm.FinishedLabel.Caption := WizardForm.FinishedLabel.Caption + #13#10#13#10 + Msg;
    end;
  end;
end;
