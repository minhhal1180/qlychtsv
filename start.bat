@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  python -m venv .venv
  if errorlevel 1 goto :failed
)
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto :failed
echo Open http://127.0.0.1:5000
".venv\Scripts\python.exe" app.py
if errorlevel 1 goto :failed
exit /b 0
:failed
echo Could not start. Check Python 3.11+ and the message above.
pause
exit /b 1
