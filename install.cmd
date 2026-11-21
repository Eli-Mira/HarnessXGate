@echo off
setlocal enabledelayedexpansion
echo === HarnessXGate One-Command Installer (Windows CMD) ===

where python >nul 2>&1
if errorlevel 1 (
  echo [ERROR] Python 3.10+ is required. Install it from https://www.python.org/downloads/ and re-run.
  exit /b 1
)

set "INSTALL_DIR=%USERPROFILE%\.harnessxgate\app"
set "BIN_DIR=%USERPROFILE%\.harnessxgate\bin"
if not exist "%BIN_DIR%" mkdir "%BIN_DIR%"

where git >nul 2>&1
if not errorlevel 1 (
  if exist "%INSTALL_DIR%\.git" (
    echo Updating HarnessXGate...
    git -C "%INSTALL_DIR%" pull --ff-only
  ) else (
    echo Downloading HarnessXGate...
    git clone --depth 1 https://github.com/Eli-Mira/HarnessXGate.git "%INSTALL_DIR%"
  )
) else (
  echo Downloading HarnessXGate archive...
  curl -fsSL https://github.com/Eli-Mira/HarnessXGate/archive/refs/heads/main.zip -o "%TEMP%\hxg.zip"
  powershell -NoProfile -Command "Expand-Archive -Force '%TEMP%\hxg.zip' '%TEMP%\hxg_extract'"
  if exist "%INSTALL_DIR%" rmdir /s /q "%INSTALL_DIR%"
  move "%TEMP%\hxg_extract\HarnessXGate-main" "%INSTALL_DIR%" >nul
)

(
  echo @echo off
  echo set "PYTHONPATH=%INSTALL_DIR%;%%PYTHONPATH%%"
  echo python -m harnessxgate %%*
) > "%BIN_DIR%\hxg.cmd"
copy /y "%BIN_DIR%\hxg.cmd" "%BIN_DIR%\harnessxgate.cmd" >nul

powershell -NoProfile -Command "$b='%BIN_DIR%'; $p=[Environment]::GetEnvironmentVariable('Path','User'); if ($p -notlike ('*'+$b+'*')) { [Environment]::SetEnvironmentVariable('Path', ($p.TrimEnd(';')+';'+$b), 'User') }"
set "PATH=%BIN_DIR%;%PATH%"

echo.
echo [OK] HarnessXGate installed!
echo Starting the Web Dashboard at http://127.0.0.1:7878 ...
echo (Next time, just type: hxg)
echo.
call "%BIN_DIR%\hxg.cmd" ui
