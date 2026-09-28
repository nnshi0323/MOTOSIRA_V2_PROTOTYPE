@echo off
REM MOTOSIRA - one-time PC setup: venv + dependencies + .env
cd /d "%~dp0"
where python >nul 2>&1 || (echo Python not found. Install Python 3.12 and tick "Add to PATH". & pause & exit /b 1)
if not exist venv (
  echo Creating virtual environment...
  python -m venv venv || (echo venv creation failed & pause & exit /b 1)
)
call venv\Scripts\activate.bat
echo Installing dependencies (first time takes a few minutes)...
python -m pip install --upgrade pip >nul
pip install -r requirements.txt || (echo pip install failed & pause & exit /b 1)
python tools\make_env.py
echo.
echo Setup complete. Next: start_broker.bat (Run as administrator), then start_dashboard.bat
pause
