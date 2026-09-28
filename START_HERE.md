# MOTOSIRA v2 Prototype — START HERE

## On the PC (Windows) — first time only
1. Install **Python 3.12** (tick "Add to PATH") and **Mosquitto** (https://mosquitto.org/download/).
2. Double-click **`setup_pc.bat`** — creates venv, installs everything, writes `.env`.

## On the PC — every time
1. Right-click **`start_broker.bat` → Run as administrator** (keep open).
   It opens the firewall and prints this PC's IP — note it for the Pi.
2. Double-click **`start_dashboard.bat`** → open http://localhost:5000
   Login: `admin` / `motosira123` (change `MOTOSIRA_PASS` in `.env` before a public demo).
3. No Pi yet? Double-click **`start_mock_pi.bat`** to simulate one.
4. Something not working? Double-click **`check_connections.bat`**.

## On the Raspberry Pi 4 — first time only
Copy this whole folder to the Pi, then:
```bash
cd MOTOSIRA
bash setup_pi.sh        # installs packages, enables I2S mic, asks for the PC's IP
sudo reboot
arecord -l              # the I2S mic card should be listed
```
Wiring (INMP441 → Pi 4): VDD→3.3V (pin 1), GND→GND (pin 6), SCK→GPIO18 (pin 12),
WS→GPIO19 (pin 35), SD→GPIO20 (pin 38), L/R→GND.

## On the Pi — every time
```bash
./run_pi.sh check                                          # broker + mic check
./run_pi.sh                                                # live diagnosis → PC dashboard
./run_pi.sh display                                        # results on the Pi screen (terminal)
./run_pi.sh --collect knocking --seconds 30 --sessions 5   # record training data
```

## Dataset → model (on the PC)
```powershell
venv\Scripts\activate
python tools\prepare_dataset.py     # raw_data\ -> 3s clips, quality filtered
python model\train.py               # needs >= 2 classes with data
```
Restart the dashboard — the top-right badge changes from **UNTRAINED** to **trained**.
Full details: `PROTOTYPE_GUIDE.md` and `pi_side/README_PI_SETUP.md`.
