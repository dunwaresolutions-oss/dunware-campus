; Campus Central - Inno Setup script.
;
; Compiles the single bundled installer, Campus-Central-Setup.exe: the
; frozen Django app (dist/central-app, built by deploy/central.spec), the
; exported Next.js SPA (frontend_central/out), the Caddyfile, and the
; deploy scripts, laid out under %ProgramData%\CampusCentral and wired up by
; install-central.ps1 in the [Run] step. Mirrors deploy/campus.iss exactly -
; same structure, same already-proven fixes (no runascurrentuser; Postgres/
; Caddy/NSSM optional at compile time) - for a second, independent product.
;
; Build order:
;   1. cd frontend_central && npm run build        (produces frontend_central/out)
;   2. cd backend  && $env:DJANGO_SETTINGS_MODULE = "central.settings.prod"
;                     $env:CENTRAL_SECRET_KEY = "<placeholder>"
;                     $env:CENTRAL_FIELD_ENCRYPTION_KEY = "<placeholder>"
;                     pyinstaller ..\deploy\central.spec --distpath ..\dist
;                                                 (produces dist/central-app)
;   3. deploy/_thirdparty/{pgsql,caddy}            SAME staged binaries as
;      Campus's own build - generic, not Campus-specific, never committed
;      (deploy/_thirdparty/ is gitignored). Nothing extra to stage if a
;      Campus build has already staged them in this checkout.
;   4. iscc deploy\central.iss                     (produces dist/installer/
;      Campus-Central-Setup.exe)
;
; Postgres/Caddy/NSSM are OPTIONAL at compile time (Flags: skipifsourcedoesntexist)
; so this compiles today even before those binaries are staged -
; install-central.ps1 detects their absence at install time and degrades
; gracefully rather than failing setup, exactly like Campus's own.

#define AppName "Campus Central"
#define AppVersion "0.1.0"
#define AppPublisher "Dunware Solutions"

[Setup]
AppId={{6F1E9C3A-2D5B-4A8E-9C1F-7B3A5E8D2C40}}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
DefaultDirName={commonappdata}\CampusCentral
DefaultGroupName=Campus Central
DisableProgramGroupPage=yes
DisableDirPage=yes
OutputDir=..\dist\installer
OutputBaseFilename=Campus-Central-Setup
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
; the frozen Django backend (PyInstaller onedir - see central.spec)
Source: "..\dist\central-app\*"; DestDir: "{app}\app"; Flags: recursesubdirs ignoreversion

; the exported Next.js SPA - built separately, may not exist on a bare checkout
Source: "..\frontend_central\out\*"; DestDir: "{app}\app\frontend_central_out"; Flags: recursesubdirs ignoreversion skipifsourcedoesntexist

; the reverse proxy front door. install-central.ps1 templates
; {app}\caddy\Caddyfile in place on first run; repair-campus-central.ps1
; rewrites it thereafter. A REINSTALL must NOT clobber the live (templated)
; file - same reasoning, same pattern as campus.iss.
Source: "proxy\central-caddyfile"; DestDir: "{app}\caddy"; DestName: "Caddyfile.template"; Flags: ignoreversion
Source: "proxy\central-caddyfile"; DestDir: "{app}\caddy"; DestName: "Caddyfile"; Flags: onlyifdoesntexist uninsneveruninstall

; third-party binaries - the SAME staged copies Campus's own installer uses
; (generic, not Campus-specific); optional here so this .iss compiles before
; they're staged - install-central.ps1 checks for their presence at install
; time either way.
Source: "_thirdparty\pgsql\*"; DestDir: "{app}\pgsql"; Flags: recursesubdirs ignoreversion skipifsourcedoesntexist
Source: "_thirdparty\caddy\*"; DestDir: "{app}\caddy\bin"; Flags: recursesubdirs ignoreversion skipifsourcedoesntexist
; GnuPG - encrypts/decrypts backups (backup-central.ps1/restore-central.ps1).
; Same staged copy Campus's own installer uses; optional here exactly like
; pgsql/caddy above. The scripts fall back to a gpg on PATH otherwise.
Source: "_thirdparty\gpg\*"; DestDir: "{app}\gpg"; Flags: recursesubdirs ignoreversion skipifsourcedoesntexist

; the first-run wizard + day-2 ops scripts
Source: "install-central.ps1"; DestDir: "{app}\scripts"; Flags: ignoreversion
Source: "repair-campus-central.ps1"; DestDir: "{app}\scripts"; Flags: ignoreversion
Source: "uninstall-central-services.ps1"; DestDir: "{app}\scripts"; Flags: ignoreversion
Source: "backup-central.ps1"; DestDir: "{app}\scripts"; Flags: ignoreversion
Source: "restore-central.ps1"; DestDir: "{app}\scripts"; Flags: ignoreversion
Source: "campus.ico"; DestDir: "{app}\scripts"; Flags: ignoreversion

Source: "..\LICENSE"; DestDir: "{app}"; Flags: ignoreversion
Source: "campus.ico"; DestDir: "{app}"; Flags: ignoreversion

[Dirs]
Name: "{app}\pgdata"; Permissions: admins-full system-full
Name: "{app}\media_central"; Permissions: admins-full system-full
Name: "{app}\logs"
; a technician drops a corrected .py here (at its real package path) to
; shadow the frozen build on site - see central_app.py's
; _apply_hotfix_overlay() (the same mechanism as Campus's own).
Name: "{app}\app\hotfix"
; default target for backup-central.ps1 -Out; GPG-encrypted archives.
Name: "{app}\backups"; Permissions: admins-full system-full
Name: "{app}\gpg\home"; Permissions: admins-full system-full

[Icons]
Name: "{group}\Campus Central"; Filename: "{app}\launch-campus-central.url"; IconFilename: "{app}\campus.ico"
Name: "{commondesktop}\Campus Central"; Filename: "{app}\launch-campus-central.url"; IconFilename: "{app}\campus.ico"; Tasks: desktopicon

[Run]
; NO runascurrentuser here - install-central.ps1 registers Windows services
; (nssm, pg_ctl) and writes ACL'd files under {commonappdata}, so it must
; inherit Setup's elevated token. Same bug class campus.iss documents for
; Campus's own 0.9.0 - fixed the same way here from the start.
Filename: "powershell.exe"; \
  Parameters: "-NoProfile -ExecutionPolicy Bypass -File ""{app}\scripts\install-central.ps1"" -InstallRoot ""{app}"""; \
  StatusMsg: "Setting up Campus Central (this can take a few minutes)..."; \
  Flags: waituntilterminated

[UninstallRun]
Filename: "powershell.exe"; \
  Parameters: "-NoProfile -ExecutionPolicy Bypass -File ""{app}\scripts\uninstall-central-services.ps1"""; \
  Flags: runhidden waituntilterminated; RunOnceId: "StopCampusCentralServices"

[Code]
var
  KeepData: Boolean;

function InitializeUninstall(): Boolean;
begin
  KeepData := (MsgBox('Keep Campus Central data (every linked school''s synced database, audit log)?' + #13#10 +
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
    DelTree(AppDir + '\media_central', True, True, True);
    DelTree(AppDir + '\logs', True, True, True);
  end;
end;
