@echo off
setlocal EnableExtensions

set LOG=install_log.txt
echo ===== install_windows.bat started at %date% %time% ===== > "%LOG%"

chcp 65001 >nul

echo [INFO] Current dir: %cd% >> "%LOG%"

echo [INFO] Checking Python... >> "%LOG%"
python --version 1>>"%LOG%" 2>>&1
if errorlevel 1 (
  echo [ERROR] Python not found. >> "%LOG%"
  echo [ERROR] Python not found. Open install_log.txt
  pause
  exit /b 1
)

echo [INFO] Creating venv... >> "%LOG%"
if not exist .venv (
  python -m venv .venv 1>>"%LOG%" 2>>&1
  if errorlevel 1 (
    echo [ERROR] venv creation failed. >> "%LOG%"
    echo [ERROR] venv creation failed. Open install_log.txt
    pause
    exit /b 1
  )
)

echo [INFO] Upgrading pip... >> "%LOG%"
call .venv\Scripts\python.exe -m pip install -U pip 1>>"%LOG%" 2>>&1
if errorlevel 1 (
  echo [ERROR] pip upgrade failed. >> "%LOG%"
  echo [ERROR] pip upgrade failed. Open install_log.txt
  pause
  exit /b 1
)

echo [INFO] Installing requirements... >> "%LOG%"
call .venv\Scripts\pip.exe install -r requirements.txt 1>>"%LOG%" 2>>&1
set RC=%errorlevel%

echo [INFO] pip install exit code: %RC% >> "%LOG%"

if not "%RC%"=="0" (
  echo [ERROR] requirements install failed. >> "%LOG%"
  echo [ERROR] requirements install failed. Open install_log.txt
  echo.
  type "%LOG%"
  pause
  exit /b %RC%
)

echo [INFO] Checking ffmpeg... >> "%LOG%"
ffmpeg -version 1>>"%LOG%" 2>>&1
if errorlevel 1 (
  echo [WARN] ffmpeg not found in PATH. >> "%LOG%"
)

echo [OK] Install complete. >> "%LOG%"
echo.
echo [OK] Install complete.
echo Log saved to: %LOG%
echo.
type "%LOG%"
pause
endlocal
