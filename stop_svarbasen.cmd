@echo off
setlocal

set "SVARBASE_PORT=8765"
set "SVARBASE_PID="

for /f "tokens=5" %%P in ('netstat -ano -p tcp ^| findstr /R /C:":%SVARBASE_PORT% .*LISTENING"') do (
  set "SVARBASE_PID=%%P"
)

if not defined SVARBASE_PID (
  echo Svarbasen koerer ikke paa port %SVARBASE_PORT%.
  echo.
  pause
  exit /b 0
)

powershell -NoProfile -ExecutionPolicy Bypass -Command "Stop-Process -Id %SVARBASE_PID% -Force"
if errorlevel 1 (
  echo Svarbasen kunne ikke stoppes. Proces-id: %SVARBASE_PID%
) else (
  echo Svarbasen blev stoppet. Proces-id: %SVARBASE_PID%
)

echo.
pause
