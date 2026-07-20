$ErrorActionPreference = "Stop"

$DataHome = if ($env:LOCALAPPDATA) { $env:LOCALAPPDATA } else { Join-Path $HOME "AppData\Local" }
$InstallHome = if ($env:CODEXLEAN_HOME) { $env:CODEXLEAN_HOME } else { Join-Path $DataHome "CodexLean" }
$BinDir = if ($env:CODEXLEAN_BIN_DIR) { $env:CODEXLEAN_BIN_DIR } else { Join-Path $HOME ".local\bin" }
$Marker = Join-Path $InstallHome ".codexlean-install"
$CodexLean = Join-Path $InstallHome "venv\Scripts\codexlean.exe"
$Scope = if ($env:CODEXLEAN_SCOPE) { $env:CODEXLEAN_SCOPE } else { "user" }
if ($Scope -notin @("user", "project")) { throw "CODEXLEAN_SCOPE must be user or project." }

$InstallFullPath = [IO.Path]::GetFullPath($InstallHome).TrimEnd('\')
$InstallRoot = [IO.Path]::GetPathRoot($InstallFullPath).TrimEnd('\')
if ($InstallFullPath -eq $InstallRoot) { throw "Refusing to remove a drive root." }
if ((Test-Path $InstallHome) -and -not (Test-Path $Marker -PathType Leaf)) {
    throw "Refusing to remove unrecognized directory: $InstallHome"
}

if (Test-Path $CodexLean) {
    $Args = @("uninstall", "--scope", $Scope)
    if ($Scope -eq "project") {
        $Project = if ($env:CODEXLEAN_PROJECT) { $env:CODEXLEAN_PROJECT } else { (Get-Location).Path }
        $Args += @("--project", $Project)
    }
    & $CodexLean @Args
    if ($LASTEXITCODE -ne 0) { throw "Codex integration removal failed." }
}

$CmdPath = Join-Path $BinDir "codexlean.cmd"
if (Test-Path $CmdPath) {
    $Expected = "`"$CodexLean`" %*"
    if ((Get-Content $CmdPath -Raw).Contains($Expected)) { Remove-Item -Force $CmdPath }
}
if (Test-Path $InstallHome) { Remove-Item -Recurse -Force $InstallHome }
Write-Host "Removed CodexLean from $InstallHome"
