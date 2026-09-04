<#
  Campus — first-run setup (invoked by the Inno Setup installer, or run by hand
  on a dev box). STUB for Phase 0: the structure and order are fixed here;
  Phase 9 fills in the real bundled-binary paths and the sc.exe service
  registration.

  What the finished version does, in order:
    1.  Check prerequisites: Windows 10/11 x64, ~4 GB free, disk encryption on
        (BitLocker) — warn loudly if not, since this box will hold children's PII.
    2.  Lay out %ProgramData%\Campus\{app,pgsql,pgdata,caddy,logs,media}.
    3.  Generate secrets -> %ProgramData%\Campus\app\.env :
          SECRET_KEY            (50+ random chars)
          FIELD_ENCRYPTION_KEY  (32 random bytes, base64)
          POSTGRES_PASSWORD     (random)
        .env is ACL'd to SYSTEM + Administrators only.
    4.  initdb pgdata; register "Campus PostgreSQL" service; start it; create the
        campus role + database.
    5.  Run the frozen Django: migrate, collectstatic (picks up frontend\out),
        create the first admin (interactive: username / email / password), then
        walk the admin through MFA enrolment.
    6.  Template deploy\proxy\Caddyfile with the chosen LAN host + API bind;
        register "Campus Proxy" (Caddy) service; `caddy trust` note for clients.
    7.  Register "Campus App" service (waitress serving config.wsgi on API_BIND).
    8.  Set all three services to Automatic (start on boot). Start them.
    9.  Drop Start Menu + Desktop shortcuts and a small launcher.exe that opens
        https://<host>/ in the default browser.
   10.  Print the LAN URL and a one-line health check.

  Uninstall prompts: "Keep Campus data (database, media, audit log)?" — default YES.
#>

param(
  [string]$InstallRoot = "$env:ProgramData\Campus",
  [string]$LanHost = "localhost",
  [string]$ApiBind = "127.0.0.1:8001"
)

Write-Host "Campus installer — Phase 0 stub. No-op." -ForegroundColor Yellow
Write-Host "InstallRoot = $InstallRoot"
Write-Host "LanHost     = $LanHost"
Write-Host "ApiBind     = $ApiBind"
Write-Host "See the comment block in this file for the full first-run sequence (built in Phase 9)."
exit 0
