$ErrorActionPreference = "Stop"
Write-Host "=== HarnessXGate One-Command Installer (PowerShell) ===" -ForegroundColor Cyan

if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
  Write-Error "Python 3.10+ is required. Install from https://www.python.org/downloads/ and re-run."
  exit 1
}

$installDir = Join-Path $env:USERPROFILE ".harnessxgate\app"
$binDir = Join-Path $env:USERPROFILE ".harnessxgate\bin"
New-Item -ItemType Directory -Force -Path $binDir | Out-Null

if (Get-Command git -ErrorAction SilentlyContinue) {
  if (Test-Path (Join-Path $installDir ".git")) {
    Write-Host "Updating HarnessXGate..."
    git -C $installDir pull --ff-only
  } else {
    Write-Host "Downloading HarnessXGate..."
    git clone --depth 1 https://github.com/Eli-Mira/HarnessXGate.git $installDir
  }
} else {
  Write-Host "Downloading HarnessXGate archive..."
  $zip = Join-Path $env:TEMP "harnessxgate.zip"
  $ext = Join-Path $env:TEMP "harnessxgate_extract"
  Invoke-WebRequest -UseBasicParsing -Uri "https://github.com/Eli-Mira/HarnessXGate/archive/refs/heads/main.zip" -OutFile $zip
  if (Test-Path $ext) { Remove-Item -Recurse -Force $ext }
  Expand-Archive -Force -Path $zip -DestinationPath $ext
  if (Test-Path $installDir) { Remove-Item -Recurse -Force $installDir }
  Move-Item (Join-Path $ext "HarnessXGate-main") $installDir
}

$shim = "@echo off`r`nset `"PYTHONPATH=$installDir;%PYTHONPATH%`"`r`npython -m harnessxgate %*`r`n"
Set-Content -Path (Join-Path $binDir "hxg.cmd") -Value $shim -Encoding ascii
Set-Content -Path (Join-Path $binDir "harnessxgate.cmd") -Value $shim -Encoding ascii

$userPath = [Environment]::GetEnvironmentVariable("Path", "User")
if ($userPath -notlike "*$binDir*") {
  [Environment]::SetEnvironmentVariable("Path", ($userPath.TrimEnd(";") + ";" + $binDir), "User")
}
$env:Path = "$binDir;$env:Path"

Write-Host "`n[OK] HarnessXGate installed! Opening http://127.0.0.1:7878 ..." -ForegroundColor Green
Write-Host "Next time, just type: hxg"
& (Join-Path $binDir "hxg.cmd") ui
