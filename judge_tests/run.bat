@echo off
setlocal
set "PYTHONDONTWRITEBYTECODE=1"
pushd "%~dp0.."
if not exist ".venv\Scripts\python.exe" goto missing
".venv\Scripts\python.exe" judge_tests\runner.py %*
set "JUDGE_EXIT=%errorlevel%"
popd
exit /b %JUDGE_EXIT%
:missing
echo Create .venv with Python 3.12 and install backend\requirements.txt first. See judge_tests\README.md.
popd
exit /b 2
