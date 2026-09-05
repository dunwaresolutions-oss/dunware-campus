<#
  create-campus-admin.ps1 - create the first Campus SUPERADMIN.

  RUN AS ADMINISTRATOR (it needs to read the ACL-locked app\.env):
    powershell -ExecutionPolicy Bypass -File "$env:USERPROFILE\Desktop\create-campus-admin.ps1"

  Only works once - bootstrap_superadmin refuses if a superadmin already
  exists. After this, sign in at https://localhost/ and enrol an
  authenticator app (TOTP) immediately; staff accounts can't reach the
  sensitive screens until MFA is confirmed.
#>
param([string]$InstallRoot = "$env:ProgramData\Campus")

$ErrorActionPreference = "Stop"
$app = Join-Path $InstallRoot "app\campus-app.exe"
if (-not (Test-Path $app)) { throw "campus-app.exe not found at $app" }

$id = [Security.Principal.WindowsIdentity]::GetCurrent()
if (-not (New-Object Security.Principal.WindowsPrincipal($id)).IsInRole(
        [Security.Principal.WindowsBuiltInRole]::Administrator)) {
  throw "Not elevated. Re-run this from an Administrator PowerShell."
}

$username = Read-Host "Admin username"
$email    = Read-Host "Admin email"
$sec      = Read-Host "Admin password (min 12 chars, not all digits)" -AsSecureString
$password = [Runtime.InteropServices.Marshal]::PtrToStringAuto(
              [Runtime.InteropServices.Marshal]::SecureStringToBSTR($sec))

if ($password.Length -lt 12) { throw "password must be at least 12 characters" }

# hand the values to Django via env vars so nothing sensitive sits on the
# command line / in shell history
$env:CAMPUS_BOOTSTRAP_USER  = $username
$env:CAMPUS_BOOTSTRAP_EMAIL = $email
$env:CAMPUS_BOOTSTRAP_PASS  = $password
$py = @'
import os
from apps.accounts.services import bootstrap_superadmin
u = bootstrap_superadmin(
    username=os.environ["CAMPUS_BOOTSTRAP_USER"],
    email=os.environ["CAMPUS_BOOTSTRAP_EMAIL"],
    password=os.environ["CAMPUS_BOOTSTRAP_PASS"],
)
print("created superadmin:", u.username, u.email)
'@

try {
  $py | & $app manage shell 2>&1 | ForEach-Object { Write-Host $_ }
  $code = $LASTEXITCODE
} finally {
  Remove-Item Env:\CAMPUS_BOOTSTRAP_USER, Env:\CAMPUS_BOOTSTRAP_EMAIL, Env:\CAMPUS_BOOTSTRAP_PASS -ErrorAction SilentlyContinue
}

if ($code -ne 0) { throw "bootstrap failed (exit $code) - if it says a superadmin already exists, one was created earlier." }
Write-Host ""
Write-Host "  Done. Sign in at https://localhost/ and enrol an authenticator app right away." -ForegroundColor Green
