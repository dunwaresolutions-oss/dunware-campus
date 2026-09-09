; Campus - Inno Setup script (Phase 9 packaging).
;
; Compiles the single bundled installer, Campus-Setup.exe: the frozen Django
; app (dist/campus-app, built by deploy/campus.spec), the exported Next.js
; SPA, the Caddyfile, and the deploy scripts, laid out under
; %ProgramData%\Campus and wired up by install.ps1 in the [Run] step.
;
; Build order:
;   1. cd frontend && npm run build              (produces frontend/out)
;   2. cd backend  && pyinstaller ..\deploy\campus.spec --distpath ..\dist
;                                                 (produces dist/campus-app)
;   3. stage deploy/_thirdparty/{pgsql,caddy}     (see docs/DEPLOYMENT.md
;      #third-party-binaries - never committed, deploy/_thirdparty/ is
;      gitignored)
;   4. iscc deploy\campus.iss                     (produces dist/installer/
;      Campus-Setup.exe)
;
; Postgres/Caddy/NSSM are OPTIONAL at compile time (Flags: skipifsourcedoesntexist)
; so this compiles today even before those binaries are staged - install.ps1
; detects their absence at install time and degrades gracefully rather than
; failing setup. See docs/PACKAGING.md for the compile run this was proven
; against.

#define AppName "Campus"
#define AppVersion "0.9.0"
#define AppPublisher "Dunware Solutions"

[Setup]
AppId={{9E7B7C7A-3B0A-4E7A-9E7A-2D6D6C8F0A01}}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
DefaultDirName={commonappdata}\Campus
DefaultGroupName=Campus
DisableProgramGroupPage=yes
DisableDirPage=yes
OutputDir=..\dist\installer
OutputBaseFilename=Campus-Setup
Compression=lzma2
SolidCompression=yes
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequired=admin
LicenseFile=..\LICENSE
SetupIconFile=campus.ico
UninstallDisplayIcon={app}\campus.ico
WizardStyle=modern
SetupLogging=yes

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: desktopicon; Description: "Create a &desktop shortcut"; GroupDescription: "Additional shortcuts:"

[Files]
; the frozen Django backend (PyInstaller onedir - see campus.spec)
Source: "..\dist\campus-app\*"; DestDir: "{app}\app"; Flags: recursesubdirs ignoreversion

; the exported Next.js SPA - built separately, may not exist on a bare checkout
Source: "..\frontend\out\*"; DestDir: "{app}\app\frontend_out"; Flags: recursesubdirs ignoreversion skipifsourcedoesntexist

; the reverse proxy front door (templated by install.ps1 at first run)
Source: "proxy\Caddyfile"; DestDir: "{app}\caddy"; Flags: ignoreversion

; third-party binaries, staged manually per docs/DEPLOYMENT.md - optional
; here so this .iss compiles before they're staged; install.ps1 checks for
; their presence at install time either way.
Source: "_thirdparty\pgsql\*"; DestDir: "{app}\pgsql"; Flags: recursesubdirs ignoreversion skipifsourcedoesntexist
Source: "_thirdparty\caddy\*"; DestDir: "{app}\caddy\bin"; Flags: recursesubdirs ignoreversion skipifsourcedoesntexist
; remote-access helpers (cloudflared / WireGuard) - staged only for sites that
; buy off-premises access; optional here exactly like caddy/pgsql above.
Source: "_thirdparty\remote\*"; DestDir: "{app}\remote\bin"; Flags: recursesubdirs ignoreversion skipifsourcedoesntexist

; the first-run wizard + day-2 ops scripts
Source: "install.ps1"; DestDir: "{app}\scripts"; Flags: ignoreversion
Source: "repair-campus.ps1"; DestDir: "{app}\scripts"; Flags: ignoreversion
Source: "remote-setup.ps1"; DestDir: "{app}\scripts"; Flags: ignoreversion
Source: "remote-setup.lib.ps1"; DestDir: "{app}\scripts"; Flags: ignoreversion
Source: "remote-setup-ui.ps1"; DestDir: "{app}\scripts"; Flags: ignoreversion
Source: "create-campus-admin.ps1"; DestDir: "{app}\scripts"; Flags: ignoreversion
Source: "campus.ico"; DestDir: "{app}\scripts"; Flags: ignoreversion
Source: "backup.ps1"; DestDir: "{app}\scripts"; Flags: ignoreversion
Source: "restore.ps1"; DestDir: "{app}\scripts"; Flags: ignoreversion
Source: "uninstall-services.ps1"; DestDir: "{app}\scripts"; Flags: ignoreversion

Source: "..\.env.example"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\LICENSE"; DestDir: "{app}"; Flags: ignoreversion
Source: "campus.ico"; DestDir: "{app}"; Flags: ignoreversion

[Dirs]
; created empty; install.ps1 also ensures these exist (belt + braces since
; Inno may skip an empty [Dirs] entry's ACL on some Windows builds)
Name: "{app}\pgdata"; Permissions: admins-full system-full
Name: "{app}\media"; Permissions: admins-full system-full
Name: "{app}\logs"
; a technician drops a corrected .py here (at its real package path) to shadow
; the frozen build on site - see docs/DEPLOYMENT.md and apps/core/hotfix.py
Name: "{app}\app\hotfix"
; remote-setup.ps1 writes tunnel/VPN config here when a site opts in
Name: "{app}\remote"

[Icons]
Name: "{group}\Campus"; Filename: "{app}\launch-campus.url"; IconFilename: "{app}\campus.ico"
Name: "{commondesktop}\Campus"; Filename: "{app}\launch-campus.url"; IconFilename: "{app}\campus.ico"; Tasks: desktopicon
; the off-premises access setup window (self-elevates); the .ps1 stays for scripted runs
Name: "{group}\Campus - Remote Access Setup"; Filename: "{sys}\WindowsPowerShell\v1.0\powershell.exe"; Parameters: "-NoProfile -ExecutionPolicy Bypass -File ""{app}\scripts\remote-setup-ui.ps1"""; IconFilename: "{app}\campus.ico"; Comment: "Turn off-site access to Campus on or off"

[Run]
; NO runascurrentuser here - install.ps1 registers Windows services (nssm,
; pg_ctl) and writes ACL'd files under {commonappdata}, so it must inherit
; Setup's elevated token. With runascurrentuser (0.9.0) the nssm CreateService
; calls silently failed and Setup still reported success.
Filename: "powershell.exe"; \
  Parameters: "-NoProfile -ExecutionPolicy Bypass -File ""{app}\scripts\install.ps1"" -InstallRoot ""{app}"""; \
  StatusMsg: "Setting up Campus (this can take a few minutes)..."; \
  Flags: waituntilterminated

[UninstallRun]
Filename: "powershell.exe"; \
  Parameters: "-NoProfile -ExecutionPolicy Bypass -File ""{app}\scripts\uninstall-services.ps1"""; \
  Flags: runhidden waituntilterminated; RunOnceId: "StopCampusServices"

[Code]
var
  KeepData: Boolean;

function InitializeUninstall(): Boolean;
begin
  KeepData := (MsgBox('Keep Campus data (database, uploaded documents, audit log)?' + #13#10 +
    'Choose Yes to keep everything for a future reinstall; No permanently deletes it.',
    mbConfirmation, MB_YESNO) = IDYES);
  Result := True;
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  AppDir: String;
begin
  if (CurUninstallStep = usPostUninstall) and (not KeepData) then begin
    AppDir := ExpandConstant('{app}');
    DelTree(AppDir + '\pgdata', True, True, True);
    DelTree(AppDir + '\media', True, True, True);
    DelTree(AppDir + '\logs', True, True, True);
  end;
end;
