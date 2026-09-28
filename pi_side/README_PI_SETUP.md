# MOTOSIRA — Raspberry Pi Setup Guide

## Hardware Required
- Raspberry Pi 4 Model B (4GB)
- INMP441 I2S MEMS microphone
- 3.5" TFT LCD Display (480x320, SPI)
- MicroSD Card (32GB+)
- (Optional) KY-024 Hall-effect sensor + neodymium magnet, for RPM

## Step 1 — Flash Raspberry Pi OS
Download Raspberry Pi OS (64-bit) and flash to SD card using Raspberry Pi Imager.
Enable SSH during setup for remote access.

## Step 2 — Enable the I2S interface (required for INMP441)
The INMP441 is NOT a USB device — it talks I2S directly to the Pi's GPIO
and needs the kernel I2S driver enabled before any Python audio library
can see it.

```bash
sudo raspi-config
# Interface Options -> I2S -> Enable
sudo reboot
```

Then add the I2S microphone overlay to `/boot/firmware/config.txt`
(or `/boot/config.txt` on older OS images):

```
dtoverlay=googlevoicehat-soundcard
```

Reboot again, then confirm the mic shows up as an ALSA capture device:

```bash
arecord -l
```

You should see a card entry for the I2S codec. If it's missing, double
check wiring (INMP441 SD -> GPIO20/DIN, WS -> GPIO19, SCK -> GPIO18,
L/R -> GND for left channel) and the overlay name.

### Known gotcha — 24-bit-in-32-bit frames
The INMP441 outputs 24-bit audio packed into 32-bit I2S frames. If you
capture as int32 and normalize directly, you'll get near-silent or
clipped-sounding audio. `pi_side/pi_capture.py` already handles this by
right-shifting each sample by `config.MIC_SHIFT_BITS` (8) to recover the
real 24-bit value — this is done automatically, but it's worth knowing
about if you write any other capture tooling.

## Step 3 — Install dependencies on the Pi
```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y python3-pip mosquitto mosquitto-clients libatlas-base-dev
pip3 install -r requirements.txt
pip3 install RPi.GPIO   # only needed if using the Hall-effect RPM sensor
```

## Step 4 — Copy project files to the Pi
Copy the whole repo (or at minimum `pi_side/`, `config.py`, `dashboard/processor.py`
if you want to test locally) to the Pi.

## Step 5a — Let the PC's MQTT broker accept the Pi (REQUIRED)
Mosquitto 2.x only accepts connections from the same machine by default,
so the Pi will fail to connect until you allow network access. On the
dashboard PC, edit `mosquitto.conf` (Windows: `C:\Program Files\mosquitto\mosquitto.conf`)
and add:
```
listener 1883
allow_anonymous true
```
Then restart the service (PowerShell as Administrator):
```powershell
net stop mosquitto
net start mosquitto
```
Also allow port 1883 through Windows Firewall if prompted. Test from the Pi:
```bash
mosquitto_sub -h 192.168.100.8 -t motosira/result -v
```
(`allow_anonymous true` is fine on a private lab network; do not expose it to the internet.)

## Step 5 — Point the Pi at the dashboard PC
Edit `config.py` on the Pi:
```python
MQTT_BROKER = "192.168.100.8"  # your dashboard PC's LAN IP
```

## Step 6 — Wire the optional RPM sensor
KY-024 signal pin -> GPIO17 (BCM, matches `config.RPM_GPIO_PIN`), VCC -> 3.3V, GND -> GND.
Mount the sensor near the flywheel/crankshaft with a single neodymium
magnet passing it once per revolution. If unwired, `pi_capture.py`
detects the missing `RPi.GPIO` import/hardware and continues without RPM
data — the dashboard shows "sensor not connected" instead of failing.

## Step 7 — Run on the Pi
Terminal 1 — audio capture (prompts you to pick the motorcycle model under test):
```bash
python3 pi_side/pi_capture.py
```

Terminal 2 — LCD/terminal result display:
```bash
python3 pi_side/pi_display.py
```

## Step 7b — Data collection mode (recording training data with the device mic)
Record labeled raw sessions with the INMP441 itself, so training data comes
from the same mic used in the field:
```bash
python3 pi_side/pi_capture.py --collect knocking --seconds 30 --sessions 5
```
- Pick the motorcycle model, press ENTER per session, confirm with the
  mechanic (y/N) before each recording is kept.
- Files land in `raw_data/<class>/<model_slug>/` on the Pi.
- Copy `raw_data/` to the dashboard PC (USB or `scp -r pi@<pi-ip>:~/MOTOSIRA/raw_data .`),
  then on the PC run `python tools/prepare_dataset.py` and `python model/train.py`.
- Stop recording promptly when the engine stops; trailing silence gets rejected.

## Step 8 — Kiosk mode (auto-start on boot)
Add to a systemd service or `/etc/rc.local` before `exit 0`:
```bash
python3 /home/pi/MOTOSIRA/pi_side/pi_capture.py &
python3 /home/pi/MOTOSIRA/pi_side/pi_display.py &
```
(Auto-selecting the motorcycle model for unattended kiosk mode requires
piping a choice into `pi_capture.py`'s prompt, or removing the prompt in
favor of a fixed model per deployed unit — flag this if you want that
kiosk variant added.)

## Step 9 — Dashboard kiosk on the touchscreen
```bash
sudo apt install -y chromium-browser
# add to autostart:
chromium-browser --kiosk --noerrdialogs http://192.168.100.8:5000
```

## Notes
- The dashboard PC (`dashboard/app.py`) must be running before the Pi starts capturing.
- Pi and PC must be on the same network; the MQTT broker (mosquitto) runs on the PC.
- Test the mic in isolation before wiring the full pipeline:
  ```bash
  arecord -D plughw:1,0 -f S32_LE -r 44100 -c 1 -d 3 test.wav
  aplay test.wav
  ```
