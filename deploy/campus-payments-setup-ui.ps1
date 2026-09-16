<#
  campus-payments-setup-ui.ps1 -- pick and configure this install's online
  payment gateway. Self-elevates, same pattern as remote-setup-ui.ps1.

  Per Campus_Payments_Action_Plan.html decision 9 ("the browser wizard is
  not the place for it") and §companion ("Tab: Payments"): the window shells
  out to `campus-app.exe manage set_gateway_config` / `payments_test` - the
  exact same commands available from a plain elevated PowerShell (see
  docs/PAYMENTS setup notes) - this is a nicer front end for them, not a
  different mechanism. A standalone window for now rather than merged into
  one tabbed "Setup & Configuration" window with Region & Fees + Remote
  Access, which the plan describes as the eventual shape - scoped this way
  so Damien can actually pick a gateway today; folding the three into one
  tabbed window is a real, separate follow-up, not done here.

  Kanoo is deliberately not in the gateway list - Damien, 2026-09-16: "leave
  Kanoo out until we get word from CaribPay." Add it once P5 builds a real
  KanooGateway.

  Start it directly (no Start-Menu entry yet - see the file header above):
    powershell -ExecutionPolicy Bypass -File deploy\campus-payments-setup-ui.ps1
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

# ── form scaffold (same helpers/conventions as remote-setup-ui.ps1) ───────
$font = New-Object System.Drawing.Font('Segoe UI', 9)
$form = New-Object System.Windows.Forms.Form
$form.Text = 'Campus - Payments Setup'
$form.Size = New-Object System.Drawing.Size(640, 560)
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
$grpStatus.Size = New-Object System.Drawing.Size(600, 70)
$lblStatus = New-Label '' 12 20 570 44
$lblStatus.Font = New-Object System.Drawing.Font('Consolas', 9)
$grpStatus.Controls.Add($lblStatus)
$form.Controls.Add($grpStatus)

# gateway picker - Kanoo deliberately excluded, see file header
$grpGateway = New-Object System.Windows.Forms.GroupBox
$grpGateway.Text = 'Gateway'
$grpGateway.Location = New-Object System.Drawing.Point(12, 88)
$grpGateway.Size = New-Object System.Drawing.Size(600, 60)
$gateways = @(
  @{ Key = 'manual';     Text = 'Manual only (no online gateway)' }
  @{ Key = 'paystack';   Text = 'Paystack' }
  @{ Key = 'flutterwave';Text = 'Flutterwave' }
  @{ Key = 'stripe';     Text = 'Stripe' }
)
$gwRadios = @{}
$gx = 14
foreach ($g in $gateways) {
  $r = New-Object System.Windows.Forms.RadioButton
  $r.Text = $g.Text
  $r.Location = New-Object System.Drawing.Point($gx, 24)
  $r.Size = New-Object System.Drawing.Size(145, 22)
  $r.Tag = $g.Key
  $gwRadios[$g.Key] = $r
  $grpGateway.Controls.Add($r)
  $gx += 148
}
$form.Controls.Add($grpGateway)

# mode
$grpMode = New-Object System.Windows.Forms.GroupBox
$grpMode.Text = 'Mode'
$grpMode.Location = New-Object System.Drawing.Point(12, 152)
$grpMode.Size = New-Object System.Drawing.Size(600, 50)
$rTest = New-Object System.Windows.Forms.RadioButton
$rTest.Text = 'Test'; $rTest.Location = New-Object System.Drawing.Point(14, 20)
$rTest.Size = New-Object System.Drawing.Size(100, 22); $rTest.Checked = $true
$rLive = New-Object System.Windows.Forms.RadioButton
$rLive.Text = 'Live'; $rLive.Location = New-Object System.Drawing.Point(120, 20)
$rLive.Size = New-Object System.Drawing.Size(100, 22)
$grpMode.Controls.AddRange(@($rTest, $rLive))
$form.Controls.Add($grpMode)

# keys
$grpKeys = New-Object System.Windows.Forms.GroupBox
$grpKeys.Text = 'Keys (from the gateway''s own dashboard)'
$grpKeys.Location = New-Object System.Drawing.Point(12, 210)
$grpKeys.Size = New-Object System.Drawing.Size(600, 110)
$grpKeys.Controls.Add((New-Label 'Public key' 12 26 100))
$txtPublic = New-Text 120 24 '' 460
$grpKeys.Controls.Add($txtPublic)
$grpKeys.Controls.Add((New-Label 'Secret key' 12 60 100))
$txtSecret = New-Text 120 58 '' 460 -Password
$grpKeys.Controls.Add($txtSecret)
$lblKeysNote = New-Label 'Ignored when Gateway = Manual only.' 12 90 560 20
$lblKeysNote.ForeColor = [System.Drawing.Color]::Gray
$grpKeys.Controls.Add($lblKeysNote)
$form.Controls.Add($grpKeys)

# ── action + log ────────────────────────────────────────────────────────
$btnTest = New-Button 'Test connection' 12 332 140
$btnApply = New-Button 'Apply' 160 332 120
$btnRefresh = New-Button 'Refresh status' 288 332 120
$btnClose = New-Button 'Close' 492 332 120
$form.Controls.AddRange(@($btnTest, $btnApply, $btnRefresh, $btnClose))

$grpLog = New-Object System.Windows.Forms.GroupBox
$grpLog.Text = 'Log'
$grpLog.Location = New-Object System.Drawing.Point(12, 372)
$grpLog.Size = New-Object System.Drawing.Size(600, 140)
$txtLog = New-Object System.Windows.Forms.TextBox
$txtLog.Multiline = $true
$txtLog.ReadOnly = $true
$txtLog.ScrollBars = 'Vertical'
$txtLog.BackColor = [System.Drawing.Color]::White
$txtLog.Location = New-Object System.Drawing.Point(10, 20)
$txtLog.Size = New-Object System.Drawing.Size(580, 110)
$txtLog.Font = New-Object System.Drawing.Font('Consolas', 8.5)
$grpLog.Controls.Add($txtLog)
$form.Controls.Add($grpLog)

function Write-Log($msg, $level = 'info') {
  $prefix = switch ($level) { 'step' { '==> ' } 'warn' { ' !  ' } 'err' { ' x  ' } default { '    ' } }
  $txtLog.AppendText("$prefix$msg`r`n")
  [System.Windows.Forms.Application]::DoEvents()
}

function Invoke-Manage([string[]]$ManageArgs) {
  # Every write here goes through the SAME `manage` command an elevated
  # PowerShell would run directly (decision 9) - this window is a front
  # end, not a different mechanism.
  $out = & $appExe manage @ManageArgs 2>&1
  return @{ Output = ($out -join "`r`n"); Code = $LASTEXITCODE }
}

function Update-StatusLabel {
  if ($initError) { $lblStatus.Text = "NOT READY: $initError"; return }
  $py = @'
from apps.billing.models import GatewayConfig
c = GatewayConfig.load()
masked = (c.secret_key[:7] + "...") if c.secret_key else "(none)"
print(f"gateway={c.gateway} mode={c.mode} public_key={c.public_key or '(none)'} secret_key={masked}")
'@
  try {
    $result = $py | & $appExe manage shell 2>&1
    $lblStatus.Text = ($result -join "`r`n").Trim()
  } catch {
    $lblStatus.Text = "status unavailable: $($_.Exception.Message)"
  }
}

function Invoke-Guarded([scriptblock]$Action) {
  if ($initError) {
    [System.Windows.Forms.MessageBox]::Show($initError, 'Not ready', 'OK', 'Error') | Out-Null
    return
  }
  $btnApply.Enabled = $false; $btnTest.Enabled = $false; $btnRefresh.Enabled = $false
  try {
    & $Action
  } catch {
    Write-Log $_.Exception.Message 'err'
  } finally {
    $btnApply.Enabled = $true; $btnTest.Enabled = $true; $btnRefresh.Enabled = $true
    Update-StatusLabel
  }
}

# ── wiring ──────────────────────────────────────────────────────────────
$btnApply.Add_Click({
    $key = ($gwRadios.Values | Where-Object { $_.Checked } | Select-Object -First 1).Tag
    if (-not $key) {
      [System.Windows.Forms.MessageBox]::Show('Pick a gateway first.', 'Campus', 'OK', 'Information') | Out-Null
      return
    }
    if ($key -ne 'manual' -and (-not $txtPublic.Text.Trim() -or -not $txtSecret.Text.Trim())) {
      [System.Windows.Forms.MessageBox]::Show(
        'Public key and secret key are required for a real gateway.', 'Campus', 'OK', 'Warning'
      ) | Out-Null
      return
    }
    Invoke-Guarded {
      $mode = if ($rLive.Checked) { 'live' } else { 'test' }
      $manageArgs = @('set_gateway_config', '--gateway', $key, '--mode', $mode)
      if ($key -ne 'manual') {
        $manageArgs += @('--public-key', $txtPublic.Text.Trim(), '--secret-key', $txtSecret.Text.Trim())
      }
      Write-Log "applying: gateway=$key mode=$mode ..." 'step'
      $r = Invoke-Manage $manageArgs
      Write-Log $r.Output
      if ($r.Code -ne 0) { Write-Log "Apply failed (exit $($r.Code))." 'err' }
      else { Write-Log 'Applied.' 'step' }
    }
  })

$btnTest.Add_Click({
    Invoke-Guarded {
      Write-Log 'testing connection...' 'step'
      $r = Invoke-Manage @('payments_test')
      Write-Log $r.Output
      if ($r.Code -ne 0) { Write-Log 'Connection test failed.' 'err' }
      else { Write-Log 'OK.' 'step' }
    }
  })

$btnRefresh.Add_Click({ Update-StatusLabel })
$btnClose.Add_Click({ $form.Close() })

Update-StatusLabel

if ($SelfTest) {
  Write-Host 'campus-payments-setup-ui: form built OK'
  $form.Dispose()
  exit 0
}

[void]$form.ShowDialog()
$form.Dispose()
