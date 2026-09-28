@echo off
REM MOTOSIRA - start Mosquitto so the Raspberry Pi can connect. RUN AS ADMINISTRATOR.
cd /d "%~dp0"
net session >nul 2>&1
if errorlevel 1 (
  echo Please right-click start_broker.bat and choose "Run as administrator".
  pause & exit /b 1
)
set "MOSQ=%ProgramFiles%\mosquitto\mosquitto.exe"
if not exist "%MOSQ%" (
  echo Mosquitto not found at "%MOSQ%".
  echo Install it from https://mosquitto.org/download/ then run this again.
  pause & exit /b 1
)
REM The Windows service only listens on localhost; stop it and run with our network config.
net stop mosquitto >nul 2>&1
netsh advfirewall firewall show rule name="MOTOSIRA MQTT" >nul 2>&1 || netsh advfirewall firewall add rule name="MOTOSIRA MQTT" dir=in action=allow protocol=TCP localport=1883 >nul
netsh advfirewall firewall show rule name="MOTOSIRA Dashboard" >nul 2>&1 || netsh advfirewall firewall add rule name="MOTOSIRA Dashboard" dir=in action=allow protocol=TCP localport=5000 >nul
echo.
echo This PC's IP address(es) - put one of these in the Pi's .env as MOTOSIRA_BROKER:
ipconfig | findstr /R /C:"IPv4"
echo.
echo Broker running. Keep this window open. (Ctrl+C to stop)
"%MOSQ%" -c "%~dp0mosquitto\motosira.conf" -v
pause
