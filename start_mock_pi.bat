@echo off
REM MOTOSIRA - simulated Pi (no hardware needed) for testing the dashboard
cd /d "%~dp0"
if not exist venv (echo Run setup_pc.bat first. & pause & exit /b 1)
call venv\Scripts\activate.bat
python pi_side\mock_pi.py
pause
