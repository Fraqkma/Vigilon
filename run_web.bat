@echo off
setlocal
pushd "%~dp0"

if /I "%~1"=="worker" goto worker
if /I "%~1"=="api" goto api

set "PYTHON_COMMAND=python"
where python >nul 2>nul
if not errorlevel 1 goto check_python
goto select_python_launcher

:check_python
call %PYTHON_COMMAND% -c "import sys; sys.exit(sys.version_info.major != 3 or sys.version_info.minor < 10 or sys.version_info.minor > 13)"
if not errorlevel 1 goto python_ready
goto select_python_launcher

:select_python_launcher
where py >nul 2>nul
if errorlevel 1 goto no_python
set "PYTHON_COMMAND=py -3.13"
call %PYTHON_COMMAND% -c "import sys; sys.exit(sys.version_info.major != 3 or sys.version_info.minor < 10 or sys.version_info.minor > 13)"
if errorlevel 1 goto no_python

:python_ready
if exist ".venv\Scripts\python.exe" goto install_requirements
echo Creating Python virtual environment...
call %PYTHON_COMMAND% -m venv .venv
if errorlevel 1 goto failed

:install_requirements
set "VIGILON_PYTHON=%CD%\.venv\Scripts\python.exe"
echo Installing runtime requirements...
"%VIGILON_PYTHON%" -m pip install -r requirements.txt
if errorlevel 1 goto failed

echo Setting up local environment...
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%CD%\scripts\setup.ps1"
if errorlevel 1 goto failed

set "PYTHONPATH=backend"
echo Applying database migrations...
"%VIGILON_PYTHON%" -m app.commands migrate
if errorlevel 1 goto failed

echo Preparing administrator account...
"%VIGILON_PYTHON%" -m app.commands bootstrap-admin
if errorlevel 1 goto failed

echo Starting API and worker in separate windows...
start "Vigilon Worker" "%ComSpec%" /k ""%~f0" worker"
start "Vigilon API" "%ComSpec%" /k ""%~f0" api"
timeout /t 3 /nobreak >nul
start "" "http://127.0.0.1:8000"
echo Vigilon is starting at http://127.0.0.1:8000
popd
exit /b 0

:worker
set "PYTHONPATH=backend"
".venv\Scripts\python.exe" -m app.worker
exit /b %errorlevel%

:api
set "PYTHONPATH=backend"
".venv\Scripts\python.exe" -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000
exit /b %errorlevel%

:no_python
echo Python 3.10 through 3.13 is required. Install it and ensure "python" or "py -3.13" is available.
goto failed

:failed
echo.
echo Vigilon setup failed. Review the error above and try again.
popd
pause
exit /b 1
