@echo off
setlocal

set "SVARBASE_APPDIR=%~dp0"
set "SVARBASE_PYTHON=C:\Users\b165105\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
set "SVARBASE_PORT=8765"
set "SVARBASE_SERVER=%SVARBASE_APPDIR%server.py"

netstat -ano -p tcp | findstr /R /C:":%SVARBASE_PORT% .*LISTENING" >nul
if not errorlevel 1 (
  echo Svarbasen koerer allerede paa http://127.0.0.1:%SVARBASE_PORT%/
  echo.
  pause
  exit /b 0
)

if not exist "%SVARBASE_PYTHON%" (
  echo Python-runtime blev ikke fundet:
  echo %SVARBASE_PYTHON%
  echo.
  pause
  exit /b 1
)

if not exist "%SVARBASE_SERVER%" (
  echo server.py blev ikke fundet:
  echo %SVARBASE_SERVER%
  echo.
  pause
  exit /b 1
)

start "Plandata Svarbasen" /min "%SVARBASE_PYTHON%" "%SVARBASE_SERVER%" --host 127.0.0.1 --port %SVARBASE_PORT%
timeout /t 2 /nobreak >nul

netstat -ano -p tcp | findstr /R /C:":%SVARBASE_PORT% .*LISTENING" >nul
if errorlevel 1 (
  echo Serveren blev startet, men porten kunne ikke bekraeftes endnu.
) else (
  echo Svarbasen er startet: http://127.0.0.1:%SVARBASE_PORT%/
)

echo.
pause
