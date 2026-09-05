; Inno Setup — установщик GZP (Gold Zone Pro)
;
; Что делает установщик:
;   1. ставит приложение в Program Files;
;   2. создаёт ярлыки;
;   3. запускает патч терминалов MT4/MT5 (индикатор появляется сам);
;   4. при удалении откатывает патч и возвращает шаблоны графиков.
;
; Версия и номер релиза приходят из CI через /DAppVersion и /DAppRelease.

#ifndef AppVersion
  #define AppVersion "1.0.1"
#endif
#ifndef AppRelease
  #define AppRelease "R2"
#endif

#define AppName "GZP"
#define AppFullName "GZP — Gold Zone Pro"
#define AppPublisher "Vadim Chudin"
#define AppExe "GZP.exe"

[Setup]
AppId={{8C1F5C2E-4B7A-4E2D-9F31-A17C4E90B215}
AppName={#AppFullName}
AppVersion={#AppVersion}
AppVerName={#AppFullName} {#AppVersion} {#AppRelease}
AppPublisher={#AppPublisher}
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
OutputDir=..\dist
OutputBaseFilename=GZP_Setup_{#AppVersion}_{#AppRelease}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=admin
ArchitecturesInstallIn64BitMode=x64compatible
SetupIconFile=..\assets\gzp.ico
UninstallDisplayName={#AppFullName} {#AppVersion}

[Languages]
Name: "russian"; MessagesFile: "compiler:Languages\Russian.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Создать ярлык на рабочем столе"; GroupDescription: "Ярлыки:"
Name: "patchterminals"; Description: "Установить индикатор в найденные терминалы MT4/MT5"; GroupDescription: "MetaTrader:"; Flags: checkedonce
Name: "autostart"; Description: "Запускать GZP при входе в Windows"; GroupDescription: "Автозапуск:"; Flags: unchecked

[Files]
Source: "..\dist\GZP\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\mql\MT4\Indicators\*"; DestDir: "{app}\mql\MT4\Indicators"; Flags: ignoreversion
Source: "..\mql\MT5\Indicators\*"; DestDir: "{app}\mql\MT5\Indicators"; Flags: ignoreversion
Source: "..\README.md"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\docs\*"; DestDir: "{app}\docs"; Flags: ignoreversion recursesubdirs

[Icons]
Name: "{group}\{#AppFullName}"; Filename: "{app}\{#AppExe}"
Name: "{group}\Удалить {#AppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon
Name: "{userstartup}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: autostart

[Run]
; Раскладываем индикатор по терминалам сразу после копирования файлов.
Filename: "{app}\{#AppExe}"; Parameters: "--patch-only"; \
  Description: "Установить индикатор в терминалы"; \
  StatusMsg: "Установка индикатора в MetaTrader..."; \
  Flags: runhidden waituntilterminated; Tasks: patchterminals
Filename: "{app}\{#AppExe}"; Description: "Запустить {#AppFullName}"; \
  Flags: nowait postinstall skipifsilent

[UninstallRun]
; Откат патча: индикатор удаляется, пользовательский шаблон возвращается.
Filename: "{app}\{#AppExe}"; Parameters: "--unpatch"; Flags: runhidden; RunOnceId: "GZPUnpatch"

[Registry]
Root: HKLM; Subkey: "Software\{#AppName}"; ValueType: string; ValueName: "Version"; ValueData: "{#AppVersion}"; Flags: uninsdeletekey
Root: HKLM; Subkey: "Software\{#AppName}"; ValueType: string; ValueName: "Release"; ValueData: "{#AppRelease}"; Flags: uninsdeletekey

[Messages]
russian.WelcomeLabel2=Будет установлен {#AppFullName} версии {#AppVersion} ({#AppRelease}).%n%nИндикатор автоматически появится в установленных терминалах MetaTrader 4 и 5.
