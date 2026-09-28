#!/usr/bin/env bash
# MOTOSIRA - one-time Raspberry Pi 4 setup:
#   system packages, Python venv, I2S mic overlay, and .env pointing at the PC.
#   Usage:  bash setup_pi.sh            (then reboot when asked)
set -e
cd "$(dirname "$0")"

echo "== Installing system packages =="
sudo apt update
sudo apt install -y python3-venv python3-pip python3-dev libportaudio2 libsndfile1 \
                    python3-rpi.gpio mosquitto-clients alsa-utils

echo "== Creating Python venv (with system packages, for RPi.GPIO) =="
[ -d venv ] || python3 -m venv --system-site-packages venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements-pi.txt

echo "== Enabling I2S + INMP441 overlay =="
BOOTCFG=/boot/firmware/config.txt
[ -f "$BOOTCFG" ] || BOOTCFG=/boot/config.txt
REBOOT=0
if ! grep -q '^dtparam=i2s=on' "$BOOTCFG"; then
  echo 'dtparam=i2s=on' | sudo tee -a "$BOOTCFG" >/dev/null; REBOOT=1
fi
if ! grep -q '^dtoverlay=googlevoicehat-soundcard' "$BOOTCFG"; then
  echo 'dtoverlay=googlevoicehat-soundcard' | sudo tee -a "$BOOTCFG" >/dev/null; REBOOT=1
fi

echo "== Pointing the Pi at the dashboard PC =="
CURRENT=$(grep -s '^MOTOSIRA_BROKER=' .env | cut -d= -f2)
read -r -p "Dashboard PC IP address (shown by start_broker.bat) [${CURRENT:-none}]: " PCIP
PCIP=${PCIP:-$CURRENT}
if [ -z "$PCIP" ]; then echo "No IP given; edit MOTOSIRA_BROKER in .env later."; PCIP=localhost; fi
python tools/make_env.py --broker "$PCIP"

chmod +x run_pi.sh
echo
if [ "$REBOOT" = "1" ]; then
  echo "I2S was just enabled. REBOOT NOW:  sudo reboot"
  echo "After reboot: arecord -l   (the mic card should be listed)"
else
  echo "I2S already enabled."
fi
echo "Then:  ./run_pi.sh check      # test broker + mic"
echo "       ./run_pi.sh            # live diagnosis"
echo "       ./run_pi.sh --collect knocking --seconds 30 --sessions 5   # record training data"
