<#
  Campus Central - stop and deregister the Windows services on uninstall.
  Called from campus-central.iss [UninstallRun]. Data directories are
  handled separately in campus-central.iss [Code] (the "keep data?" prompt).
  Mirrors deploy/uninstall-services.ps1 (Campus's own) exactly, scoped to
  Central's three services (no scheduler - Central has no django_q worker).
#>
foreach ($name in @("Campus Central App", "Campus Central Proxy", "Campus Central PostgreSQL")) {
  $svc = Get-Service -Name $name -ErrorAction SilentlyContinue
  if ($svc) {
    Stop-Service -Name $name -Force -ErrorAction SilentlyContinue
    sc.exe delete $name | Out-Null
  }
}
