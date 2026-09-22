@echo off
setlocal EnableExtensions

cd /d "%~dp0"
chcp 65001 >nul

if not exist .venv\Scripts\python.exe (
  echo [ERROR] Please run install_windows.bat first.
  echo.
  pause
  exit /b 1
)

echo [INFO] Starting server at: http://127.0.0.1:8000
echo [INFO] Stop server with Ctrl+C
echo.

call .venv\Scripts\python.exe desktop_launcher.py --browser

echo.
echo [INFO] Server stopped.
pause
endlocal
