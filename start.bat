@echo off
setlocal
pushd "%~dp0"
set "PYTHONDONTWRITEBYTECODE=1"

if exist ".venv\Scripts\python.exe" goto check_venv

rem Prefer the standard Windows Python launcher, then a Python 3.12 executable.
py -3.12 -c "import sys; sys.exit(sys.version_info[:2] != (3, 12))" >nul 2>&1
if not errorlevel 1 (
    py -3.12 -m venv .venv
    goto created_venv
)
python -c "import sys; sys.exit(sys.version_info[:2] != (3, 12))" >nul 2>&1
if not errorlevel 1 (
    python -m venv .venv
    goto created_venv
)
if exist "%LocalAppData%\Programs\Python\Python312\python.exe" (
    "%LocalAppData%\Programs\Python\Python312\python.exe" -m venv .venv
    goto created_venv
)
rem Codex desktop also bundles Python 3.12 on this workstation.
if exist "%USERPROFILE%\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" (
    "%USERPROFILE%\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -m venv .venv
    goto created_venv
)
echo Python 3.12 is required. Install it and run start.bat again.
goto failed

:created_venv
if errorlevel 1 (
    echo Could not create .venv. Check your Python 3.12 installation.
    goto failed
)

:check_venv
".venv\Scripts\python.exe" -c "import sys; sys.exit(sys.version_info[:2] != (3, 12))" >nul 2>&1
if errorlevel 1 (
    echo Existing .venv must use Python 3.12. Rename it and run start.bat again.
    goto failed
)
".venv\Scripts\python.exe" -m pip --version >nul 2>&1
if errorlevel 1 (
    ".venv\Scripts\python.exe" -m ensurepip --upgrade
    if errorlevel 1 goto failed
)
echo Installing Proofport dependencies...
".venv\Scripts\python.exe" -m pip install --disable-pip-version-check -r backend\requirements.txt
if errorlevel 1 (
    echo Dependency installation failed. Check your internet connection and try again.
    goto failed
)
if not defined PROOFPORT_PORT set "PROOFPORT_PORT=8000"
echo Starting Proofport at http://127.0.0.1:%PROOFPORT_PORT% - press Ctrl+C to stop.
echo Real verification requires Docker images and PROOFPORT_CASES_FILE.
echo Live Meta requires key/model. Non-AI fixtures require explicit fixture mode.
".venv\Scripts\python.exe" -m backend.launcher
set "PROOFPORT_EXIT=%errorlevel%"
popd
exit /b %PROOFPORT_EXIT%

:failed
popd
exit /b 1
