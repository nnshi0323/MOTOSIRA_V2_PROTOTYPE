@echo off
cd /d "%~dp0"
if not exist venv (echo Run setup_pc.bat first. & pause & exit /b 1)
call venv\Scripts\activate.bat
python tools\check_connections.py
pause
