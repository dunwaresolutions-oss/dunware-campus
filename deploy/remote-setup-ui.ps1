<#
  remote-setup-ui.ps1  --  the window a technician uses to turn Campus
  off-premises access on or off. Same actions as remote-setup.ps1, with a form
  instead of parameters. Self-elevates. Nothing here moves STORED data off the
  box in any mode -- see docs/REMOTE_ACCESS_AND_YOUR_DATA.md.

  Start Menu: "Campus - Remote Access Setup".
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

. (Join-Path $PSScriptRoot 'remote-setup.lib.ps1')

$initError = $null
if (-not $SelfTest) {
  try { Initialize-RemoteSetup -InstallRoot $InstallRoot }
  catch { $initError = $_.Exception.Message }
}

# ── form scaffold ────────────────────────────────────────────────────────
$font = New-Object System.Drawing.Font('Segoe UI', 9)
$form = New-Object System.Windows.Forms.Form
$form.Text = 'Campus - Remote Access Setup'
$form.Size = New-Object System.Drawing.Size(680, 720)
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
function New-Text($x, $y, $default = '', $w = 300) {
  $t = New-Object System.Windows.Forms.TextBox
  $t.Location = New-Object System.Drawing.Point($x, $y)
  $t.Size = New-Object System.Drawing.Size($w, 22)
  $t.Text = $default
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
$grpStatus.Text = 'Current status'
$grpStatus.Location = New-Object System.Drawing.Point(12, 10)
$grpStatus.Size = New-Object System.Drawing.Size(640, 96)
$lblStatus = New-Label '' 12 20 610 68
$lblStatus.Font = New-Object System.Drawing.Font('Consolas', 9)
$grpStatus.Controls.Add($lblStatus)
$form.Controls.Add($grpStatus)

# mode picker
$grpMode = New-Object System.Windows.Forms.GroupBox
$grpMode.Text = 'What do you want to do'
$grpMode.Location = New-Object System.Drawing.Point(12, 112)
$grpMode.Size = New-Object System.Drawing.Size(640, 60)
$modes = @(
  @{ Key = 'Tunnel';    Text = 'Cloudflare Tunnel' }
  @{ Key = 'WireGuard'; Text = 'WireGuard VPN' }
  @{ Key = 'Gateway';   Text = 'Plain gateway' }
  @{ Key = 'Off';       Text = 'Turn OFF' }
)
$radios = @{}
$rx = 14
foreach ($m in $modes) {
  $r = New-Object System.Windows.Forms.RadioButton
  $r.Text = $m.Text
  $r.Location = New-Object System.Drawing.Point($rx, 24)
  $r.Size = New-Object System.Drawing.Size(155, 22)
  $r.Tag = $m.Key
  $radios[$m.Key] = $r
  $grpMode.Controls.Add($r)
  $rx += 158
}
$form.Controls.Add($grpMode)

# ── detail panels (stacked, one visible at a time) ───────────────────────
$panelArea = New-Object System.Drawing.Point(12, 180)
$panelSize = New-Object System.Drawing.Size(640, 250)

$pnlTunnel = New-Object System.Windows.Forms.Panel
$pnlTunnel.Location = $panelArea; $pnlTunnel.Size = $panelSize
$pnlTunnel.Controls.Add((New-Label 'Public hostname' 8 12))
$txtTunHost = New-Text 170 10 '' 400
$pnlTunnel.Controls.Add($txtTunHost)
$pnlTunnel.Controls.Add((New-Label 'e.g. portal.yourschool.edu.bs' 170 34 400))
$pnlTunnel.Controls.Add((New-Label 'Tunnel name' 8 64))
$txtTunName = New-Text 170 62 'campus' 200
$pnlTunnel.Controls.Add($txtTunName)
$pnlTunnel.Controls.Add((New-Label 'Allowed emails (optional)' 8 96))
$txtTunEmails = New-Text 170 94 '' 400
$pnlTunnel.Controls.Add($txtTunEmails)
$pnlTunnel.Controls.Add((New-Label 'comma-separated; used for the Cloudflare Access policy note' 170 118 460))
$btnCfLogin = New-Button 'Sign in to Cloudflare...' 170 148 200
$pnlTunnel.Controls.Add($btnCfLogin)
$lblTunNote = New-Label 'Needs a Cloudflare account + a domain in Cloudflare. After Apply, finish the Cloudflare Access policy in the dashboard (the log prints the steps).' 8 188 620 50
$pnlTunnel.Controls.Add($lblTunNote)

$pnlWg = New-Object System.Windows.Forms.Panel
$pnlWg.Location = $panelArea; $pnlWg.Size = $panelSize
$pnlWg.Controls.Add((New-Label 'Listen port (UDP)' 8 12))
$txtWgPort = New-Text 170 10 '51820' 100
$pnlWg.Controls.Add($txtWgPort)
$pnlWg.Controls.Add((New-Label 'Forward this one port on the school router to this box.' 280 12 350))
$grpPeer = New-Object System.Windows.Forms.GroupBox
$grpPeer.Text = 'Add a device (run once the server is set up)'
$grpPeer.Location = New-Object System.Drawing.Point(8, 44)
$grpPeer.Size = New-Object System.Drawing.Size(620, 150)
$grpPeer.Controls.Add((New-Label 'Device name' 10 26 110))
$txtPeerName = New-Text 130 24 '' 260
$grpPeer.Controls.Add($txtPeerName)
$grpPeer.Controls.Add((New-Label "School public IP / DDNS" 10 58 110))
$txtPeerEndpoint = New-Text 130 56 '' 260
$grpPeer.Controls.Add($txtPeerEndpoint)
$btnAddPeer = New-Button 'Create device config' 130 92 180
$grpPeer.Controls.Add($btnAddPeer)
$pnlWg.Controls.Add($grpPeer)
$lblWgNote = New-Label 'Apply first sets up the server. Then fill a device name + the school''s public address and Create device config -- it writes a .conf to import into the WireGuard app.' 8 200 620 44
$pnlWg.Controls.Add($lblWgNote)

$pnlGw = New-Object System.Windows.Forms.Panel
$pnlGw.Location = $panelArea; $pnlGw.Size = $panelSize
$pnlGw.Controls.Add((New-Label 'Public hostname' 8 12))
$txtGwHost = New-Text 170 10 '' 400
$pnlGw.Controls.Add($txtGwHost)
$pnlGw.Controls.Add((New-Label "Let's Encrypt email" 8 44))
$txtGwEmail = New-Text 170 42 '' 300
$pnlGw.Controls.Add($txtGwEmail)
$lblGwNote = New-Label 'Forward ports 80 AND 443 to this box and point a public DNS A record at the school''s IP. Caddy fetches the certificate on the first external hit. No third party is in the path.' 8 84 620 60
$pnlGw.Controls.Add($lblGwNote)

$pnlOff = New-Object System.Windows.Forms.Panel
$pnlOff.Location = $panelArea; $pnlOff.Size = $panelSize
$pnlOff.Controls.Add((New-Label 'This stops the tunnel / VPN, clears the setting, and restarts Campus LAN-only. Nothing is removed from the database.' 8 12 620 50))

$allPanels = @($pnlTunnel, $pnlWg, $pnlGw, $pnlOff)
$allPanels | ForEach-Object { $_.Visible = $false; $form.Controls.Add($_) }

# ── action + log ────────────────────────────────────────────────────────
$btnApply = New-Button 'Apply' 12 440 120
$btnRefresh = New-Button 'Refresh status' 140 440 120
$btnClose = New-Button 'Close' 532 440 120
$form.Controls.AddRange(@($btnApply, $btnRefresh, $btnClose))

$grpLog = New-Object System.Windows.Forms.GroupBox
$grpLog.Text = 'Log'
$grpLog.Location = New-Object System.Drawing.Point(12, 478)
$grpLog.Size = New-Object System.Drawing.Size(640, 190)
$txtLog = New-Object System.Windows.Forms.TextBox
$txtLog.Multiline = $true
$txtLog.ReadOnly = $true
$txtLog.ScrollBars = 'Vertical'
$txtLog.BackColor = [System.Drawing.Color]::White
$txtLog.Location = New-Object System.Drawing.Point(10, 20)
$txtLog.Size = New-Object System.Drawing.Size(620, 160)
$txtLog.Font = New-Object System.Drawing.Font('Consolas', 8.5)
$grpLog.Controls.Add($txtLog)
$form.Controls.Add($grpLog)

Set-RSLogSink {
  param($msg, $level)
  $prefix = switch ($level) { 'step' { '==> ' } 'warn' { ' !  ' } 'err' { ' x  ' } default { '    ' } }
  $txtLog.AppendText("$prefix$msg`r`n")
  [System.Windows.Forms.Application]::DoEvents()
}

function Update-StatusLabel {
  if ($initError) { $lblStatus.Text = "NOT READY: $initError"; return }
  try {
    $s = Get-RemoteStatus
    $lblStatus.Text = @(
      ("Mode      : {0}" -f $s.Mode)
      ("Address   : {0}" -f $(if ($s.Hosts) { $s.Hosts } else { '-' }))
      ("Tunnel svc: {0}   Client-IP header: {1}" -f $s.Service, $(if ($s.Header) { $s.Header } else { '-' }))
      $(if ($s.Hotfixes) { "Hotfixes  : " + ($s.Hotfixes -join ', ') } else { "" })
    ) -join "`r`n"
  } catch { $lblStatus.Text = "status unavailable: $($_.Exception.Message)" }
}

function Show-Panel($key) {
  $allPanels | ForEach-Object { $_.Visible = $false }
  switch ($key) {
    'Tunnel'    { $pnlTunnel.Visible = $true }
    'WireGuard' { $pnlWg.Visible = $true }
    'Gateway'   { $pnlGw.Visible = $true }
    'Off'       { $pnlOff.Visible = $true }
  }
}

function Invoke-Guarded([scriptblock]$Action) {
  if ($initError) {
    [System.Windows.Forms.MessageBox]::Show($initError, 'Not ready',
      'OK', 'Error') | Out-Null
    return
  }
  $btnApply.Enabled = $false; $btnRefresh.Enabled = $false; $grpMode.Enabled = $false
  try {
    & $Action
    [System.Windows.Forms.Application]::DoEvents()
  } catch [RemoteSetupError] {
    [System.Windows.Forms.MessageBox]::Show($_.Exception.Message, 'Could not finish',
      'OK', 'Error') | Out-Null
  } catch {
    [System.Windows.Forms.MessageBox]::Show($_.Exception.Message, 'Unexpected error',
      'OK', 'Error') | Out-Null
  } finally {
    $btnApply.Enabled = $true; $btnRefresh.Enabled = $true; $grpMode.Enabled = $true
    Update-StatusLabel
  }
}

# ── wiring ──────────────────────────────────────────────────────────────
foreach ($r in $radios.Values) {
  $r.Add_CheckedChanged({ if ($this.Checked) { Show-Panel $this.Tag } })
}

$btnCfLogin.Add_Click({ Invoke-Guarded { Invoke-CloudflaredLogin $null } })

$btnAddPeer.Add_Click({
    Invoke-Guarded {
      $conf = Add-WireGuardPeer @{
        Name = $txtPeerName.Text.Trim(); Endpoint = $txtPeerEndpoint.Text.Trim()
        WgListenPort = $txtWgPort.Text.Trim()
      }
      if ($conf -and (Test-Path $conf)) {
        Start-Process explorer.exe "/select,`"$conf`""
      }
    }
  })

$btnApply.Add_Click({
    $key = ($radios.Values | Where-Object { $_.Checked } | Select-Object -First 1).Tag
    if (-not $key) {
      [System.Windows.Forms.MessageBox]::Show('Pick an option first.', 'Campus', 'OK', 'Information') | Out-Null
      return
    }
    Invoke-Guarded {
      switch ($key) {
        'Tunnel' {
          Enable-Tunnel @{
            Hostname = $txtTunHost.Text.Trim(); TunnelName = $txtTunName.Text.Trim()
            AccessEmails = $txtTunEmails.Text.Trim()
          }
        }
        'WireGuard' { Enable-WireGuard @{ WgListenPort = $txtWgPort.Text.Trim() } }
        'Gateway'   { Enable-Gateway @{ Hostname = $txtGwHost.Text.Trim(); AcmeEmail = $txtGwEmail.Text.Trim() } }
        'Off'       { Disable-RemoteAccess }
      }
      Write-RSLog "done ($key)." 'step'
    }
  })

$btnRefresh.Add_Click({ Update-StatusLabel })
$btnClose.Add_Click({ $form.Close() })

Update-StatusLabel
$radios['Tunnel'].Checked = $true

if ($SelfTest) {
  Write-Host 'remote-setup-ui: form built OK'
  $form.Dispose()
  exit 0
}

[void]$form.ShowDialog()
$form.Dispose()
