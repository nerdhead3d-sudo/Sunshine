; Sunshine installer (Inno Setup). Build the PyInstaller app first
; (pyinstaller installer/sunshine.spec --noconfirm from the repo root),
; then compile this with the Inno Setup Compiler (ISCC.exe) or IDE.
;
; No code-signing (deliberately skipped for now, see CLAUDE.md/conversation
; history — EV/OV certs need a registered business entity and an annual
; cost not justified yet). Windows SmartScreen will warn on first run of
; the unsigned exe; that's expected, not a bug in this script.

#define MyAppName "Sunshine"
#define MyAppVersion "1.0.0"
#define MyAppPublisher "Sunshine"
#define MyAppExeName "Sunshine.exe"
#define MyAppDataDir "{localappdata}\Sunshine"

[Setup]
AppId={{8C2C9C2E-7B7A-4B7E-9B5D-9B7B6F6C9A11}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\{#MyAppName}
; Default install location is per-user (no admin / UAC prompt needed),
; like VS Code/Discord — most desktop-mascot users won't want a UAC
; prompt for something this lightweight. Switch to {autopf}-only and
; PrivilegesRequired=admin if a machine-wide install is ever wanted instead.
DefaultGroupName={#MyAppName}
PrivilegesRequired=lowest
OutputDir=dist_installer
OutputBaseFilename=SunshineSetup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
UninstallDisplayIcon={app}\{#MyAppExeName}

[Languages]
Name: "italian"; MessagesFile: "compiler:Languages\Italian.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "autostart"; Description: "{cm:AutostartTask}"; GroupDescription: "{cm:AutostartGroup}"
Name: "downloadmodels"; Description: "{cm:DownloadModelsTask}"; GroupDescription: "{cm:DownloadModelsGroup}"; Flags: checkedonce

[CustomMessages]
italian.AutostartTask=Avvia Sunshine automaticamente all'accesso a Windows
italian.AutostartGroup=Avvio automatico:
italian.DownloadModelsTask=Scarica ora i modelli vocali/IA (alcune centinaia di MB, qualche minuto)
italian.DownloadModelsGroup=Modelli:
italian.MonitorPageCaption=Schermo del pet
italian.MonitorPageDescription=Su quale monitor deve vivere Sunshine?
italian.OllamaMissingTitle=Ollama non trovato
italian.OllamaMissingText=Sunshine usa Ollama come motore di chat predefinito (oppure il modello offline integrato, selezionabile dopo l'installazione dal menu Impostazioni del pet). Ollama non risulta installato su questo PC.%n%nPuoi continuare l'installazione comunque e installare Ollama in seguito da ollama.com, oppure aprirlo ora.
italian.OllamaOpenSite=Apri ollama.com
italian.DownloadingModels=Scaricamento modelli in corso, potrebbe richiedere qualche minuto...

english.AutostartTask=Start Sunshine automatically when you log into Windows
english.AutostartGroup=Startup:
english.DownloadModelsTask=Download voice/AI models now (a few hundred MB, a few minutes)
english.DownloadModelsGroup=Models:
english.MonitorPageCaption=Pet's screen
english.MonitorPageDescription=Which monitor should Sunshine live on?
english.OllamaMissingTitle=Ollama not found
english.OllamaMissingText=Sunshine uses Ollama as its default chat engine (or the built-in offline model, selectable after installation from the pet's Settings menu). Ollama doesn't appear to be installed on this PC.%n%nYou can continue installing anyway and install Ollama later from ollama.com, or open it now.
english.OllamaOpenSite=Open ollama.com
english.DownloadingModels=Downloading models, this may take a few minutes...

[Files]
Source: "..\dist\Sunshine\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\{cm:UninstallProgram,{#MyAppName}}"; Filename: "{uninstallexe}"
Name: "{userstartup}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: autostart

[Run]
Filename: "{app}\{#MyAppExeName}"; Parameters: "--download-models --lang={code:GetSelectedLanguage}"; \
    StatusMsg: "{cm:DownloadingModels}"; Tasks: downloadmodels; Flags: runhidden waituntilterminated

[Code]
var
  MonitorPage: TInputOptionWizardPage;
  OllamaChecked: Boolean;

function GetSelectedLanguage(Param: string): string;
begin
  { Maps the installer's own UI language to one of Sunshine's supported
    spoken languages (config.SUPPORTED_LANGUAGES); defaults to Italian for
    any installer language not explicitly handled, matching config.
    DEFAULT_LANGUAGE. }
  case ActiveLanguage of
    'english': Result := 'en';
  else
    Result := 'it';
  end;
end;

procedure InitializeWizardMonitorPage;
var
  I, MonitorCount: Integer;
begin
  MonitorPage := CreateInputOptionPage(wpSelectTasks,
    CustomMessage('MonitorPageCaption'), CustomMessage('MonitorPageCaption'),
    CustomMessage('MonitorPageDescription'), True, False);

  { GetSystemMetrics(SM_CMONITORS) = 80: real Win32 call, not a guess —
    gives the actual number of display monitors attached right now.
    Listed as plain "Monitor 1/2/3" rather than trying to show each
    monitor's real geometry/name (that would need EnumDisplayMonitors with
    a callback, awkward from Pascal Script) — good enough to pick the same
    index config.SECONDARY_SCREEN_INDEX already expects. }
  MonitorCount := GetSystemMetrics(80);
  if MonitorCount < 1 then
    MonitorCount := 1;

  for I := 0 to MonitorCount - 1 do
    MonitorPage.Add(Format('Monitor %d', [I + 1]));

  { Default to the second monitor if there is one (matches config.py's
    own SECONDARY_SCREEN_INDEX = 1 default), else the only one available. }
  if MonitorCount > 1 then
    MonitorPage.SelectedValueIndex := 1
  else
    MonitorPage.SelectedValueIndex := 0;
end;

procedure CheckOllamaInstalled;
var
  ResultCode: Integer;
  Response: Integer;
begin
  OllamaChecked := True;
  if not Exec(ExpandConstant('{app}\{#MyAppExeName}'), '--check-ollama', '',
     SW_HIDE, ewWaitUntilTerminated, ResultCode) then
    ResultCode := 1; { couldn't even run it yet at this point in setup; treat as "not found" }

  if ResultCode <> 0 then
  begin
    Response := MsgBox(CustomMessage('OllamaMissingText'), mbInformation, MB_YESNO);
    if Response = IDYES then
      ShellExec('open', 'https://ollama.com/download', '', '', SW_SHOW, ewNoWait, ResultCode);
  end;
end;

procedure InitializeWizard;
begin
  InitializeWizardMonitorPage;
  OllamaChecked := False;
end;

function NextButtonClick(CurPageID: Integer): Boolean;
begin
  Result := True;
  { Runs the Ollama check right after files are installed (wpInstalling is
    the page right after copying), so {app}\Sunshine.exe actually exists
    by the time we try to run --check-ollama against it. }
  if (CurPageID = wpInstalling) and not OllamaChecked then
    CheckOllamaInstalled;
end;

procedure WriteInstallSettings;
var
  SettingsDir, SettingsFile: string;
  MonitorIndex: Integer;
begin
  MonitorIndex := MonitorPage.SelectedValueIndex;
  SettingsDir := ExpandConstant('{localappdata}\Sunshine\data');
  ForceDirectories(SettingsDir);
  SettingsFile := SettingsDir + '\install_settings.json';
  SaveStringToFile(SettingsFile,
    '{"secondary_screen_index": ' + IntToStr(MonitorIndex) +
    ', "language": "' + GetSelectedLanguage('') + '"}', False);
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssPostInstall then
    WriteInstallSettings;
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  DataDir: string;
  Response: Integer;
begin
  if CurUninstallStep = usPostUninstall then
  begin
    DataDir := ExpandConstant('{localappdata}\Sunshine');
    if DirExists(DataDir) then
    begin
      Response := MsgBox(
        'Vuoi eliminare anche i dati personali di Sunshine (conversazioni, volti riconosciuti, modelli scaricati)?' + #13#10 +
        'Do you also want to delete Sunshine''s personal data (conversations, recognized faces, downloaded models)?',
        mbConfirmation, MB_YESNO);
      if Response = IDYES then
        DelTree(DataDir, True, True, True);
    end;
  end;
end;
