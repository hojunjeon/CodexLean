$ErrorActionPreference = "Stop"

$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
$DataHome = if ($env:LOCALAPPDATA) { $env:LOCALAPPDATA } else { Join-Path $HOME "AppData\Local" }
$InstallHome = if ($env:CODEXLEAN_HOME) { $env:CODEXLEAN_HOME } else { Join-Path $DataHome "CodexLean" }
$BinDir = if ($env:CODEXLEAN_BIN_DIR) { $env:CODEXLEAN_BIN_DIR } else { Join-Path $HOME ".local\bin" }
$Venv = Join-Path $InstallHome "venv"
$Marker = Join-Path $InstallHome ".codexlean-install"
$Python = Join-Path $Venv "Scripts\python.exe"
$CodexLean = Join-Path $Venv "Scripts\codexlean.exe"
$CmdPath = Join-Path $BinDir "codexlean.cmd"
$ExpectedLauncher = "`"$CodexLean`" %*"
$Scope = if ($env:CODEXLEAN_SCOPE) { $env:CODEXLEAN_SCOPE } else { "user" }
if ($Scope -notin @("user", "project")) { throw "CODEXLEAN_SCOPE must be user or project." }

$InstallFullPath = [IO.Path]::GetFullPath($InstallHome).TrimEnd('\')
$InstallRoot = [IO.Path]::GetPathRoot($InstallFullPath).TrimEnd('\')
if ($InstallFullPath -eq $InstallRoot) { throw "Refusing to use a drive root as CODEXLEAN_HOME." }
if ((Test-Path $InstallHome) -and -not (Test-Path $Marker -PathType Leaf)) {
    throw "Refusing to overwrite unrecognized directory: $InstallHome"
}
if (Test-Path $CmdPath) {
    $ExistingLauncher = Get-Content $CmdPath -Raw
    if (-not $ExistingLauncher.Contains($ExpectedLauncher)) {
        throw "Refusing to replace unrelated launcher: $CmdPath"
    }
}

$Launcher = Get-Command py -ErrorAction SilentlyContinue
if (-not $Launcher) { throw "CodexLean requires Python 3.10+ with the py launcher." }
$VersionOk = & py -3 -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)"
if ($LASTEXITCODE -ne 0) { throw "CodexLean requires Python 3.10+." }

New-Item -ItemType Directory -Force -Path $InstallHome, $BinDir | Out-Null
[IO.File]::WriteAllText($Marker, "CodexLean managed installation`r`n", [Text.UTF8Encoding]::new($false))
& py -3 -m venv $Venv
if ($LASTEXITCODE -ne 0) { throw "Failed to create the CodexLean virtual environment." }
& $Python -m pip install --disable-pip-version-check $Root
if ($LASTEXITCODE -ne 0) { throw "Failed to install CodexLean." }

$CmdText = "@echo off`r`n`"$CodexLean`" %*`r`n"
[IO.File]::WriteAllText($CmdPath, $CmdText, [Text.UTF8Encoding]::new($false))

$IntegrationArgs = @("install", "--scope", $Scope)
if ($Scope -eq "project") {
    $Project = if ($env:CODEXLEAN_PROJECT) { $env:CODEXLEAN_PROJECT } else { (Get-Location).Path }
    $IntegrationArgs += @("--project", $Project)
}
& $CodexLean @IntegrationArgs
if ($LASTEXITCODE -ne 0) { throw "Codex integration installation failed." }

$DoctorArgs = @("doctor", "--scope", $Scope)
if ($Scope -eq "project") { $DoctorArgs += @("--project", $Project) }
& $CodexLean @DoctorArgs
if ($LASTEXITCODE -ne 0) { throw "CodexLean doctor failed." }

Write-Host "Installed CodexLean in $Venv"
Write-Host "Launcher: $CmdPath"
