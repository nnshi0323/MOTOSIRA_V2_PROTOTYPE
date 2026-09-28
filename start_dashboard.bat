@echo off
REM MOTOSIRA - start the dashboard (http://localhost:5000)
cd /d "%~dp0"
if not exist venv (echo Run setup_pc.bat first. & pause & exit /b 1)
call venv\Scripts\activate.bat
python dashboard\app.py
pause
