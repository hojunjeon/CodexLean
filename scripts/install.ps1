$ErrorActionPreference = "Stop"
$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
$Wheel = Get-ChildItem (Join-Path $Root "dist") -Filter "codexlean-*.whl" -ErrorAction SilentlyContinue | Sort-Object Name | Select-Object -Last 1
if ($Wheel) {
  py -m pip install $Wheel.FullName
} else {
  py -m pip install $Root
}
$Scope = if ($env:CODEXLEAN_SCOPE) { $env:CODEXLEAN_SCOPE } else { "user" }
codexlean install --scope $Scope
codexlean doctor --scope $Scope
