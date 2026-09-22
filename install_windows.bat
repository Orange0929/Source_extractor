@echo off
setlocal EnableExtensions
cd /d "%~dp0"

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

echo [1/4] Preparing Python environment...
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

echo [2/4] Checking/installing pitch runtime. First install may take several minutes.
echo Progress log: %cd%\install_log.txt
echo [INFO] Installing CPU pitch runtime... >> "%LOG%"
call .venv\Scripts\python.exe -m pip install torch==2.8.0 torchaudio==2.8.0 --index-url https://download.pytorch.org/whl/cpu 1>>"%LOG%" 2>>&1
if errorlevel 1 (
  echo [ERROR] Pitch runtime installation failed. See install_log.txt
  pause
  exit /b 1
)

echo [3/4] Installing app components...
echo [INFO] Installing requirements... >> "%LOG%"
call .venv\Scripts\python.exe -m pip install -r requirements-desktop.txt 1>>"%LOG%" 2>>&1
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

echo [INFO] Checking Korean pronunciation engine... >> "%LOG%"
call .venv\Scripts\python.exe -c "from korean_pronunciation import pronounce; pronounce('test'); pronounce(chr(54617)+chr(44368))" 1>>"%LOG%" 2>>&1
if errorlevel 1 (
  echo [ERROR] Pronunciation engine check failed. See install_log.txt
  pause
  exit /b 1
)

echo [INFO] Checking ffmpeg... >> "%LOG%"
ffmpeg -version 1>>"%LOG%" 2>>&1
if errorlevel 1 (
  echo [WARN] ffmpeg not found in PATH. >> "%LOG%"
)

echo [4/4] Creating desktop shortcut...
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0create_shortcut.ps1" -InstallRoot "%cd%" 1>>"%LOG%" 2>>&1
if errorlevel 1 echo [WARN] Shortcut creation failed. Use run_windows.bat instead.
echo [OK] Install complete. >> "%LOG%"
echo.
echo [OK] Install complete. Open Source Extractor on your desktop or run_windows.bat.
echo Log saved to: %LOG%
echo.
type "%LOG%"
pause
endlocal
