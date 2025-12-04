@echo off
REM SOC Report Review Tool - Startup Script (Batch version)

setlocal enabledelayedexpansion

echo.
echo ==========================================
echo SOC Report Review Tool - MVP Launcher
echo ==========================================
echo.

REM Get the directory where this script is located
set SCRIPT_DIR=%~dp0
set BACKEND_DIR=%SCRIPT_DIR%backend
set FRONTEND_DIR=%SCRIPT_DIR%frontend

echo Checking for running processes...
tasklist /FI "IMAGENAME eq python.exe" 2>NUL | find /I /N "python.exe">NUL
if "%ERRORLEVEL%"=="0" (
    echo Stopping existing Python processes...
    taskkill /F /IM python.exe >NUL 2>&1
    timeout /t 2 /nobreak >NUL
)

echo.
echo ✓ Starting Backend API...
cd /d %BACKEND_DIR%
start "SOC Report Backend" python app.py
timeout /t 3 /nobreak >NUL

echo ✓ Backend API started on http://127.0.0.1:5000
echo.
echo ✓ Starting Frontend Server...
cd /d %FRONTEND_DIR%
start "SOC Report Frontend" python -m http.server 8000 --bind 127.0.0.1
timeout /t 2 /nobreak >NUL

echo ✓ Frontend Server started on http://127.0.0.1:8000
echo.
echo ==========================================
echo ✓ SOC Report Review Tool is ready!
echo ==========================================
echo.
echo Frontend: http://127.0.0.1:8000
echo Backend API: http://127.0.0.1:5000
echo.
echo Press any key to stop all services and exit...
pause >NUL

echo.
echo Stopping services...
taskkill /F /IM python.exe >NUL 2>&1
echo ✓ Services stopped
