<#
  Campus - stop and deregister the Windows services on uninstall.
  Called from campus.iss [UninstallRun]. Data directories are handled
  separately in campus.iss [Code] (the "keep data?" prompt).
#>
foreach ($name in @("Campus App", "Campus Proxy", "Campus PostgreSQL")) {
  $svc = Get-Service -Name $name -ErrorAction SilentlyContinue
  if ($svc) {
    Stop-Service -Name $name -Force -ErrorAction SilentlyContinue
    sc.exe delete $name | Out-Null
  }
}
