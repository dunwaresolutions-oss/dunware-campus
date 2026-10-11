<#
  campus-central-setup-ui.ps1 -- link this Campus install to a Campus Central
  head office, or turn that link off. Self-elevates, same pattern as
  remote-setup-ui.ps1 / campus-payments-setup-ui.ps1.

  Per Campus_MultiSchool_Action_Plan.html (C1/C5) and docs/CENTRAL_SYNC_SCOPE.md
  (the C0 decisions this builds on): the window shells out to
  `campus-app.exe manage set_site_config` / `link_central` / `unlink_central`
  / `central_link_test` / `central_sync` -- the exact same commands available
  from a plain elevated PowerShell -- this is a nicer front end for them, not
  a different mechanism (same reasoning campus-payments-setup-ui.ps1 states
  for itself).

  "Sync now" (C5) has no automatic schedule behind it yet -- see
  apps/core/central_sync.py's own docstring for why (django_q is configured
  but no worker process is registered in this product's installed services).
  Use the button, or `manage central_sync`, until that's resolved.

  There is no "Headquarters" option in this window on purpose: Campus itself
  can never run as the head office -- that is a separate product, Campus
  Central, with its own installer. If that's what's needed, this window says
  so instead of offering a choice that the backend will always refuse.

  "Test connection" will always fail today -- Campus Central's ingest/health
  endpoint isn't built until a later phase (see docs/CENTRAL_SYNC_SCOPE.md).
  The button is wired up now so it works for free once Central exists.

  On an installed machine, open Start Menu -> "Campus - Central Link Setup"
  (campus.iss adds the shortcut). From a source checkout, start it directly:
    powershell -ExecutionPolicy Bypass -File deploy\campus-central-setup-ui.ps1
#>
param(
  [string]$InstallRoot = "$env:ProgramData\Campus",
  [switch]$SelfTest   # build the form and exit (used by the packaging gate)
)

$ErrorActionPreference = 'Stop'

# ── self-elevate ─────────────────────────────────────────────────────────
$isAdmin = ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()
).IsInRole([Security.Principal.WindowsBuiltinRole]::Administrator)
if (-not $isAdmin -and -not $SelfTest) {
  Start-Process powershell -Verb RunAs -ArgumentList @(
    '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', "`"$PSCommandPath`"",
    '-InstallRoot', "`"$InstallRoot`""
  )
  exit
}

Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
[System.Windows.Forms.Application]::EnableVisualStyles()

$appExe = Join-Path $InstallRoot 'app\campus-app.exe'
$initError = $null
if (-not $SelfTest -and -not (Test-Path $appExe)) {
  $initError = "campus-app.exe not found at $appExe"
}

# ── form scaffold (same helpers/conventions as campus-payments-setup-ui.ps1) ─
$font = New-Object System.Drawing.Font('Segoe UI', 9)
$form = New-Object System.Windows.Forms.Form
$form.Text = 'Campus - Central Link Setup'
$form.Size = New-Object System.Drawing.Size(640, 640)
$form.StartPosition = 'CenterScreen'
$form.FormBorderStyle = 'FixedDialog'
$form.MaximizeBox = $false
$form.Font = $font

function New-Label($text, $x, $y, $w = 150, $h = 20) {
  $l = New-Object System.Windows.Forms.Label
  $l.Text = $text; $l.Location = New-Object System.Drawing.Point($x, $y)
  $l.Size = New-Object System.Drawing.Size($w, $h)
  $l
}
function New-Text($x, $y, $default = '', $w = 300, [switch]$Password) {
  $t = New-Object System.Windows.Forms.TextBox
  $t.Location = New-Object System.Drawing.Point($x, $y)
  $t.Size = New-Object System.Drawing.Size($w, 22)
  $t.Text = $default
  if ($Password) { $t.UseSystemPasswordChar = $true }
  $t
}
function New-Button($text, $x, $y, $w = 150) {
  $b = New-Object System.Windows.Forms.Button
  $b.Text = $text; $b.Location = New-Object System.Drawing.Point($x, $y)
  $b.Size = New-Object System.Drawing.Size($w, 28)
  $b
}

# status
$grpStatus = New-Object System.Windows.Forms.GroupBox
$grpStatus.Text = 'Current configuration'
$grpStatus.Location = New-Object System.Drawing.Point(12, 10)
$grpStatus.Size = New-Object System.Drawing.Size(600, 86)
$lblStatus = New-Label '' 12 20 570 60
$lblStatus.Font = New-Object System.Drawing.Font('Consolas', 8.5)
$grpStatus.Controls.Add($lblStatus)
$form.Controls.Add($grpStatus)

# mode
$grpMode = New-Object System.Windows.Forms.GroupBox
$grpMode.Text = 'Is this a single institution, or a school linked to a Head Office?'
$grpMode.Location = New-Object System.Drawing.Point(12, 104)
$grpMode.Size = New-Object System.Drawing.Size(600, 80)
$rSingle = New-Object System.Windows.Forms.RadioButton
$rSingle.Text = 'Single institution'; $rSingle.Location = New-Object System.Drawing.Point(14, 22)
$rSingle.Size = New-Object System.Drawing.Size(200, 22); $rSingle.Checked = $true
$rSchool = New-Object System.Windows.Forms.RadioButton
$rSchool.Text = 'School (linked to a Head Office)'; $rSchool.Location = New-Object System.Drawing.Point(220, 22)
$rSchool.Size = New-Object System.Drawing.Size(260, 22)
$lblHq = New-Label 'Running the Head Office itself? That is a separate product, Campus Central -- a separate installer, not this window.' 14 48 580 28
$lblHq.ForeColor = [System.Drawing.Color]::Gray
$grpMode.Controls.AddRange(@($rSingle, $rSchool, $lblHq))
$form.Controls.Add($grpMode)
$btnSaveMode = New-Button 'Save mode' 480 192 120
$form.Controls.Add($btnSaveMode)

# link
$grpLink = New-Object System.Windows.Forms.GroupBox
$grpLink.Text = 'Head Office link (used only in School mode)'
$grpLink.Location = New-Object System.Drawing.Point(12, 228)
$grpLink.Size = New-Object System.Drawing.Size(600, 150)
$grpLink.Controls.Add((New-Label 'Central URL' 12 26 100))
$txtUrl = New-Text 140 24 '' 440
$grpLink.Controls.Add($txtUrl)
$grpLink.Controls.Add((New-Label 'School ID' 12 58 100))
$txtSchoolId = New-Text 140 56 '' 440
$grpLink.Controls.Add($txtSchoolId)
$grpLink.Controls.Add((New-Label 'Sync token' 12 90 100))
$txtToken = New-Text 140 88 '' 440 -Password
$grpLink.Controls.Add($txtToken)
$lblLinkNote = New-Label 'School ID and token are issued by whoever runs the Head Office box, when this school is registered there.' 12 118 570 28
$lblLinkNote.ForeColor = [System.Drawing.Color]::Gray
$grpLink.Controls.Add($lblLinkNote)
$form.Controls.Add($grpLink)

# ── sync (C5) ─────────────────────────────────────────────────────────────
$btnSync = New-Button 'Sync now' 12 388 110
$chkForceFull = New-Object System.Windows.Forms.CheckBox
$chkForceFull.Text = 'Force full (not just changes)'
$chkForceFull.Location = New-Object System.Drawing.Point(132, 392)
$chkForceFull.Size = New-Object System.Drawing.Size(220, 22)
$lblSyncNote = New-Label 'No automatic schedule runs this yet -- see docs/CENTRAL_SYNC_SCOPE.md. Use this button, or `manage central_sync`, until one does.' 12 414 600 20
$lblSyncNote.ForeColor = [System.Drawing.Color]::Gray
$lblSyncNote.Font = New-Object System.Drawing.Font('Segoe UI', 7.5)
$form.Controls.AddRange(@($btnSync, $chkForceFull, $lblSyncNote))

# ── action + log ────────────────────────────────────────────────────────
$btnTest = New-Button 'Test connection' 12 436 130
$btnLink = New-Button 'Link' 148 436 90
$btnUnlink = New-Button 'Unlink' 244 436 90
$btnRefresh = New-Button 'Refresh status' 340 436 130
$btnClose = New-Button 'Close' 492 436 120
$form.Controls.AddRange(@($btnTest, $btnLink, $btnUnlink, $btnRefresh, $btnClose))

$grpLog = New-Object System.Windows.Forms.GroupBox
$grpLog.Text = 'Log'
$grpLog.Location = New-Object System.Drawing.Point(12, 476)
$grpLog.Size = New-Object System.Drawing.Size(600, 130)
$txtLog = New-Object System.Windows.Forms.TextBox
$txtLog.Multiline = $true
$txtLog.ReadOnly = $true
$txtLog.ScrollBars = 'Vertical'
$txtLog.BackColor = [System.Drawing.Color]::White
$txtLog.Location = New-Object System.Drawing.Point(10, 20)
$txtLog.Size = New-Object System.Drawing.Size(580, 100)
$txtLog.Font = New-Object System.Drawing.Font('Consolas', 8.5)
$grpLog.Controls.Add($txtLog)
$form.Controls.Add($grpLog)

function Write-Log($msg, $level = 'info') {
  $prefix = switch ($level) { 'step' { '==> ' } 'warn' { ' !  ' } 'err' { ' x  ' } default { '    ' } }
  $txtLog.AppendText("$prefix$msg`r`n")
  [System.Windows.Forms.Application]::DoEvents()
}

function Invoke-Manage([string[]]$ManageArgs) {
  # Same reasoning and the same stdout/stderr-to-file approach as
  # campus-payments-setup-ui.ps1's Invoke-Manage -- see that file's comment.
  $stdoutFile = [System.IO.Path]::GetTempFileName()
  $stderrFile = [System.IO.Path]::GetTempFileName()
  try {
    $p = Start-Process -FilePath $appExe -ArgumentList (@('manage') + $ManageArgs) `
      -RedirectStandardOutput $stdoutFile -RedirectStandardError $stderrFile `
      -NoNewWindow -PassThru -Wait
    $stdout = Get-Content $stdoutFile -Raw -ErrorAction SilentlyContinue
    $stderr = Get-Content $stderrFile -Raw -ErrorAction SilentlyContinue
    $combined = (@($stdout, $stderr) | Where-Object { $_ }) -join "`r`n"
    return @{ Output = $combined.Trim(); Code = $p.ExitCode }
  } finally {
    Remove-Item $stdoutFile, $stderrFile -ErrorAction SilentlyContinue
  }
}

function Update-StatusLabel {
  if ($initError) { $lblStatus.Text = "NOT READY: $initError"; return }
  $py = @'
from apps.core.models import SiteConfiguration
c = SiteConfiguration.load()
token = "(set)" if c.central_token else "(none)"
print(f"mode={c.deployment_mode} school_id={c.school_id or '(none)'}")
print(f"central_url={c.central_url or '(none)'} token={token} sync_enabled={c.sync_enabled}")
print(f"last_synced_at={c.last_synced_at or 'never'} last_sync_error={c.last_sync_error or '(none)'}")
'@
  $stdinFile = [System.IO.Path]::GetTempFileName()
  $stdoutFile = [System.IO.Path]::GetTempFileName()
  $stderrFile = [System.IO.Path]::GetTempFileName()
  try {
    Set-Content -Path $stdinFile -Value $py -Encoding utf8 -NoNewline
    $p = Start-Process -FilePath $appExe -ArgumentList @('manage', 'shell') `
      -RedirectStandardInput $stdinFile -RedirectStandardOutput $stdoutFile `
      -RedirectStandardError $stderrFile -NoNewWindow -PassThru -Wait
    $stdout = (Get-Content $stdoutFile -Raw -ErrorAction SilentlyContinue)
    if ($p.ExitCode -eq 0 -and $stdout) {
      $lblStatus.Text = $stdout.Trim()
      $rSchool.Checked = $stdout -match 'mode=SCHOOL'
      $rSingle.Checked = -not $rSchool.Checked
    } else {
      $stderr = (Get-Content $stderrFile -Raw -ErrorAction SilentlyContinue)
      $lblStatus.Text = "status unavailable (exit $($p.ExitCode)): $($stderr.Trim())"
    }
  } catch {
    $lblStatus.Text = "status unavailable: $($_.Exception.Message)"
  } finally {
    Remove-Item $stdinFile, $stdoutFile, $stderrFile -ErrorAction SilentlyContinue
  }
}

function Invoke-Guarded([scriptblock]$Action) {
  if ($initError) {
    [System.Windows.Forms.MessageBox]::Show($initError, 'Not ready', 'OK', 'Error') | Out-Null
    return
  }
  $btnSaveMode.Enabled = $false; $btnTest.Enabled = $false; $btnSync.Enabled = $false
  $btnLink.Enabled = $false; $btnUnlink.Enabled = $false; $btnRefresh.Enabled = $false
  try {
    & $Action
  } catch {
    Write-Log $_.Exception.Message 'err'
  } finally {
    $btnSaveMode.Enabled = $true; $btnTest.Enabled = $true; $btnSync.Enabled = $true
    $btnLink.Enabled = $true; $btnUnlink.Enabled = $true; $btnRefresh.Enabled = $true
    Update-StatusLabel
  }
}

# ── wiring ──────────────────────────────────────────────────────────────
$btnSaveMode.Add_Click({
    $mode = if ($rSchool.Checked) { 'SCHOOL' } else { 'SINGLE' }
    Invoke-Guarded {
      Write-Log "setting deployment mode to $mode ..." 'step'
      $r = Invoke-Manage @('set_site_config', '--deployment-mode', $mode)
      Write-Log $r.Output
      if ($r.Code -ne 0) { Write-Log 'Save failed.' 'err' } else { Write-Log 'Saved.' 'step' }
    }
  })

$btnSync.Add_Click({
    Invoke-Guarded {
      $syncArgs = @('central_sync')
      if ($chkForceFull.Checked) { $syncArgs += '--full' }
      Write-Log "syncing ($(if ($chkForceFull.Checked) { 'forced full' } else { 'incremental if due' })) ..." 'step'
      $r = Invoke-Manage $syncArgs
      Write-Log $r.Output
      if ($r.Code -ne 0) { Write-Log 'Sync failed.' 'err' } else { Write-Log 'Done.' 'step' }
    }
  })

$btnTest.Add_Click({
    if (-not $txtUrl.Text.Trim()) {
      [System.Windows.Forms.MessageBox]::Show('Enter a Central URL first.', 'Campus', 'OK', 'Information') | Out-Null
      return
    }
    Invoke-Guarded {
      Write-Log "testing connection to $($txtUrl.Text.Trim()) (nothing saved) ..." 'step'
      $r = Invoke-Manage @('central_link_test', '--central-url', $txtUrl.Text.Trim())
      Write-Log $r.Output
      if ($r.Code -ne 0) { Write-Log 'Connection test failed -- expected until Campus Central itself exists.' 'warn' }
      else { Write-Log 'OK.' 'step' }
    }
  })

$btnLink.Add_Click({
    if (-not $txtUrl.Text.Trim() -or -not $txtSchoolId.Text.Trim() -or -not $txtToken.Text.Trim()) {
      [System.Windows.Forms.MessageBox]::Show(
        'Central URL, School ID and token are all required to link.', 'Campus', 'OK', 'Warning'
      ) | Out-Null
      return
    }
    Invoke-Guarded {
      Write-Log 'linking to the Head Office ...' 'step'
      $r = Invoke-Manage @(
        'link_central', '--central-url', $txtUrl.Text.Trim(),
        '--school-id', $txtSchoolId.Text.Trim(), '--token', $txtToken.Text.Trim()
      )
      Write-Log $r.Output
      if ($r.Code -ne 0) { Write-Log 'Link failed.' 'err' } else { Write-Log 'Linked.' 'step'; $txtToken.Text = '' }
    }
  })

$btnUnlink.Add_Click({
    if ([System.Windows.Forms.MessageBox]::Show(
        'Unlink from the Head Office? Sync turns off; the mode (Single/School) is left as is.',
        'Campus', 'YesNo', 'Question') -ne 'Yes') { return }
    Invoke-Guarded {
      Write-Log 'unlinking ...' 'step'
      $r = Invoke-Manage @('unlink_central')
      Write-Log $r.Output
      if ($r.Code -ne 0) { Write-Log 'Unlink failed.' 'err' } else {
        Write-Log 'Unlinked.' 'step'
        $txtUrl.Text = ''; $txtSchoolId.Text = ''; $txtToken.Text = ''
      }
    }
  })

$btnRefresh.Add_Click({ Update-StatusLabel })
$btnClose.Add_Click({ $form.Close() })

Update-StatusLabel

if ($SelfTest) {
  Write-Host 'campus-central-setup-ui: form built OK'
  $form.Dispose()
  exit 0
}

[void]$form.ShowDialog()
$form.Dispose()
