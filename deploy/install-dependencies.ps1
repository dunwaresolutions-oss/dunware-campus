<#
  Campus - technical-staff dependency installer.

  NOT part of the application's own setup installer (deploy/campus.iss
  deliberately never runs this) - companion to
  Campus_Technical_and_Troubleshooting_Guide.pdf, for whoever is building
  Campus-Setup.exe or repairing a site that's missing one bundled
  third-party component.

  Fetches and stages every optional third-party binary the main installer
  can bundle - PostgreSQL, Caddy, NSSM, GnuPG, the GTK3 runtime (WeasyPrint's
  native half - see docs/DEPLOYMENT.md and Technical Guide 5.11) - into
  deploy/_thirdparty/, in exactly the layout campus.iss and
  _ensure_native_pdf_libs() already expect. Detects what's already staged and
  skips it; only fetches what's actually missing. Everything it downloads is
  a plain zip or a portable/self-contained installer run silently to a
  scratch folder and copied out - nothing here needs, or requests,
  Administrator elevation, because it never touches %ProgramData% or the
  Windows service registry; it only ever writes under deploy\_thirdparty\.

  Usage (from anywhere; run.ps1 resolves paths off its own location):
    powershell -ExecutionPolicy Bypass -File install-dependencies.ps1
    powershell -ExecutionPolicy Bypass -File install-dependencies.ps1 -Only caddy,nssm
    powershell -ExecutionPolicy Bypass -File install-dependencies.ps1 -Force
    powershell -ExecutionPolicy Bypass -File install-dependencies.ps1 -CheckOnly

  After this finishes, deploy/_thirdparty/ is ready for `iscc campus.iss` to
  bundle everything it finds (each row is still individually optional -
  campus.iss compiles fine with any subset staged; install.ps1 degrades
  gracefully at install time for whatever's absent).
#>
param(
  # Only fetch these (by key below) instead of everything.
  [string[]]$Only = @(),
  # Re-fetch and overwrite even if already staged.
  [switch]$Force,
  # Report what's present/missing without downloading anything.
  [switch]$CheckOnly
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$Stage = Join-Path $Root "_thirdparty"
$Tmp = Join-Path $env:TEMP ("campus-deps-" + [guid]::NewGuid().ToString("N").Substring(0, 8))
New-Item -ItemType Directory -Force -Path $Stage, $Tmp | Out-Null

function Write-Step($m) { Write-Host "==> $m" -ForegroundColor Cyan }
function Write-Info($m) { Write-Host "    $m" }
function Write-Skip($m) { Write-Host "    - already staged, skipping: $m" -ForegroundColor DarkYellow }
function Write-Done($m) { Write-Host "    + $m" -ForegroundColor Green }
function Write-Fail($m) { Write-Host "    ! $m" -ForegroundColor Red }

function Get-DepFile([string]$Url, [string]$OutFile) {
  Invoke-WebRequest -Uri $Url -OutFile $OutFile -UseBasicParsing -TimeoutSec 600
}

# Each entry: a human label, the file (relative to _thirdparty\) whose
# presence means "already staged", the source URL, and an install script
# block that turns the download into that exact layout. Every install block
# takes ($Url, $Stage, $Tmp) and must leave the `detect` path behind on
# success - that's also how the summary confirms it actually worked, not
# just that the installer/unzip step didn't throw.
$Deps = [ordered]@{

  caddy = @{
    # campus.iss maps "_thirdparty\caddy\*" -> "{app}\caddy\bin" -- the "bin"
    # is added by that destination mapping, so the STAGED copy here is flat
    # (caddy.exe and nssm.exe sit directly under _thirdparty\caddy\, sharing
    # the folder), not nested under its own bin\.
    label  = "Caddy v2.11.4 (reverse proxy + local HTTPS)"
    detect = "caddy\caddy.exe"
    url    = "https://github.com/caddyserver/caddy/releases/download/v2.11.4/caddy_2.11.4_windows_amd64.zip"
    install = {
      param($Url, $Stage, $Tmp)
      $zip = Join-Path $Tmp "caddy.zip"
      Get-DepFile $Url $zip
      $x = Join-Path $Tmp "caddy-x"
      Expand-Archive -Path $zip -DestinationPath $x -Force
      $dst = Join-Path $Stage "caddy"
      New-Item -ItemType Directory -Force -Path $dst | Out-Null
      Copy-Item (Join-Path $x "caddy.exe") $dst -Force
    }
  }

  nssm = @{
    label  = "NSSM 2.24 (wraps caddy.exe / campus-app.exe as Windows services)"
    detect = "caddy\nssm.exe"
    url    = "https://nssm.cc/release/nssm-2.24.zip"
    install = {
      param($Url, $Stage, $Tmp)
      $zip = Join-Path $Tmp "nssm.zip"
      Get-DepFile $Url $zip
      $x = Join-Path $Tmp "nssm-x"
      Expand-Archive -Path $zip -DestinationPath $x -Force
      $dst = Join-Path $Stage "caddy"
      New-Item -ItemType Directory -Force -Path $dst | Out-Null
      Copy-Item (Join-Path $x "nssm-2.24\win64\nssm.exe") $dst -Force
    }
  }

  gtk3 = @{
    label  = "GTK3 runtime 3.24.31 (WeasyPrint's native libs - Cairo/Pango/GObject)"
    detect = "gtk3\bin\libgobject-2.0-0.dll"
    url    = "https://github.com/tschoonj/GTK-for-Windows-Runtime-Environment-Installer/releases/download/2022-01-04/gtk3-runtime-3.24.31-2022-01-04-ts-win64.exe"
    install = {
      param($Url, $Stage, $Tmp)
      $installer = Join-Path $Tmp "gtk3-installer.exe"
      Get-DepFile $Url $installer
      $x = Join-Path $Tmp "gtk3-x"
      # This ships as an NSIS installer whose manifest requests elevation -
      # Start-Process refuses it outright. Direct invocation with NSIS's own
      # silent flags (/S /D=<path>, D last, unquoted, absolute) sidesteps
      # that entirely - confirmed working, not assumed. This is NOT Inno
      # Setup syntax (/DIR=) despite the source project's name.
      & $installer /S "/D=$x"
      Start-Sleep -Seconds 3
      $dst = Join-Path $Stage "gtk3"
      if (Test-Path $dst) { Remove-Item $dst -Recurse -Force }
      Move-Item $x $dst
    }
  }

  gpg = @{
    label  = "GnuPG 2.5, standalone w32 build (encrypts/decrypts backup.ps1 / restore.ps1 archives)"
    detect = "gpg\bin\gpg.exe"
    url    = "https://www.gnupg.org/ftp/gcrypt/binary/gnupg-w32-2.5.22_20260831.exe"
    install = {
      param($Url, $Stage, $Tmp)
      $installer = Join-Path $Tmp "gnupg-installer.exe"
      Get-DepFile $Url $installer
      $x = Join-Path $Tmp "gnupg-x"
      & $installer /S "/D=$x"
      Start-Sleep -Seconds 3
      $dst = Join-Path $Stage "gpg"
      if (Test-Path $dst) { Remove-Item $dst -Recurse -Force }
      New-Item -ItemType Directory -Force -Path $dst | Out-Null
      Copy-Item (Join-Path $x "bin") (Join-Path $dst "bin") -Recurse -Force
      $gnupgLib = Join-Path $x "lib\gnupg"
      if (Test-Path $gnupgLib) {
        New-Item -ItemType Directory -Force -Path (Join-Path $dst "lib") | Out-Null
        Copy-Item $gnupgLib (Join-Path $dst "lib\gnupg") -Recurse -Force
      }
    }
  }

  postgres = @{
    label  = "PostgreSQL 16.15, portable binaries (~330 MB - the slow one)"
    detect = "pgsql\bin\initdb.exe"
    url    = "https://sbp.enterprisedb.com/getfile.jsp?fileid=1260494"
    install = {
      param($Url, $Stage, $Tmp)
      $zip = Join-Path $Tmp "postgres.zip"
      Get-DepFile $Url $zip
      $x = Join-Path $Tmp "postgres-x"
      Expand-Archive -Path $zip -DestinationPath $x -Force
      # EDB's zip normally wraps everything in its own "pgsql" folder;
      # fall back to the extraction root if a future build ever doesn't.
      $inner = Join-Path $x "pgsql"
      $src = if (Test-Path $inner) { $inner } else { $x }
      $dst = Join-Path $Stage "pgsql"
      if (Test-Path $dst) { Remove-Item $dst -Recurse -Force }
      Move-Item $src $dst
    }
  }
}

$names = if ($Only.Count) { $Only } else { $Deps.Keys }
$unknown = $names | Where-Object { -not $Deps.Contains($_) }
if ($unknown) {
  Write-Fail "unknown dependency name(s): $($unknown -join ', ') - valid: $($Deps.Keys -join ', ')"
  exit 1
}

Write-Step "Campus dependency check - staging into $Stage"
$results = [System.Collections.Generic.List[object]]::new()

foreach ($name in $names) {
  $d = $Deps[$name]
  $detectPath = Join-Path $Stage $d.detect
  $present = Test-Path $detectPath

  if ($CheckOnly) {
    Write-Info ("{0,-10} {1}  ({2})" -f $name, $(if ($present) { "present" } else { "MISSING" }), $d.label)
    $results.Add([pscustomobject]@{ Dependency = $name; Status = $(if ($present) { "Present" } else { "Missing" }) })
    continue
  }

  Write-Step $d.label
  if ($present -and -not $Force) {
    Write-Skip $d.detect
    $results.Add([pscustomobject]@{ Dependency = $name; Result = "Skipped (already staged)" })
    continue
  }
  try {
    & $d.install $d.url $Stage $Tmp
    if (Test-Path $detectPath) {
      Write-Done "staged at deploy\_thirdparty\$($d.detect)"
      $results.Add([pscustomobject]@{ Dependency = $name; Result = "Installed" })
    } else {
      Write-Fail "ran with no error, but $($d.detect) still doesn't exist - check by hand"
      $results.Add([pscustomobject]@{ Dependency = $name; Result = "FAILED (verify manually)" })
    }
  } catch {
    Write-Fail $_.Exception.Message
    $results.Add([pscustomobject]@{ Dependency = $name; Result = "FAILED: $($_.Exception.Message)" })
  }
}

Remove-Item $Tmp -Recurse -Force -ErrorAction SilentlyContinue

Write-Host ""
Write-Step "Summary"
$results | Format-Table -AutoSize

if (-not $CheckOnly) {
  Write-Host ""
  Write-Info "Next: 'iscc campus.iss' bundles whatever's now staged into Campus-Setup.exe."
  Write-Info "Anything still missing is simply left out - the installer and install.ps1 both"
  Write-Info "degrade gracefully per-component (see docs/DEPLOYMENT.md's third-party table)."
}
