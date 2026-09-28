# MOTOSIRA — Prototype Guide (dataset → training → device)

This is the test/prototype copy. Main copy stays untouched.

## The data pipeline

```
 Phone/recorder  ─┐
                  ├─> raw_data/<class>/<model_slug>/*.wav   (long raw sessions)
 Pi --collect  ───┘
                          │  python tools/prepare_dataset.py
                          │  - cut into 3s clips (skip first 0.5s, drop short tail)
                          │  - quality filter: GOOD = SNR >= 12 dB and peak < -1 dBFS
                          │  - rejected clips -> raw_data/_rejected/ (listen to check)
                          │  - JSON report -> logs/dataset_report_*.json
                          v
            model/training_data/<class>/<model_slug>/*.wav   (training-ready)
                          │  python model/train.py
                          v
            model/trained/motosira_rf.pkl + scaler.pkl + model_meta.json
                          │  restart python dashboard/app.py
                          v
            Dashboard shows "Model: trained (...)" instead of "UNTRAINED"
```

Model slugs: `honda_tmx_125_alpha`, `rusi_macho_125`, `suzuki_smash_carb`
Classes: `normal`, `knocking`, `misfire`, `valve_ticking`

## Commands (PC, inside this folder, venv active)

```powershell
python tools/prepare_dataset.py --dry-run      # preview counts, writes nothing
python tools/prepare_dataset.py                # segment + filter everything in raw_data/
python tools/validate_recordings.py --dir model/training_data/normal/honda_tmx_125_alpha
python model/train.py                          # train (needs >= 2 classes with data)
python dashboard/app.py                        # dashboard, then open http://localhost:5000
```

Small anomaly sets (real recordings only) can be multiplied with:
```powershell
python tools/augment_recordings.py --source <folder of real clips> --class knocking --model honda_tmx_125_alpha --count 8
```
Report real vs augmented counts separately in the paper.

## Current dataset status

| Class | Honda TMX 125 Alpha | Target |
|---|---|---|
| normal | 55 clips (from 9 raw recordings) | ~83 |
| knocking | 0 | ~83 |
| misfire | 0 | ~83 |
| valve_ticking | 0 | ~83 |

`train.py` refuses to train until at least 2 classes have data (a one-class
model would label every sound as that class). It also never falls back to
synthetic data unless run with `--allow-synthetic` (pipeline testing only).

## Fixes in this copy vs. the main v2

- `tools/prepare_dataset.py` (new): one-command raw → training-ready clips
- `pi_side/pi_capture.py --collect` (new): record labeled training data with the INMP441
- `model/train.py`: same low-pass filter as the live pipeline (fixes train/diagnosis
  feature mismatch); refuses one-class training; no silent synthetic fallback;
  works when only some classes have data
- `dashboard/app.py`: confidence now read via `model.classes_` (old code crashed
  or mislabeled when not all 4 classes were trained)
- Dashboard shows model status (trained / UNTRAINED — results are random)
- `pi_side/README_PI_SETUP.md`: Mosquitto remote-access setup (Pi cannot connect without it)
- One-click scripts: `setup_pc.bat`, `start_broker.bat`, `start_dashboard.bat`,
  `start_mock_pi.bat`, `check_connections.bat`, `setup_pi.sh`, `run_pi.sh`
- `mosquitto/motosira.conf`: network-enabled broker config (no editing Program Files)
- Broker IP and mic channels come from `.env` (`MOTOSIRA_BROKER`, `MOTOSIRA_MIC_CHANNELS`)
- Dashboard, Pi capture, mock Pi and Pi display all auto-retry/reconnect to MQTT
  (start order no longer matters)
- Pi capture falls back to stereo and keeps the left channel if the I2S card rejects mono
- `tools/check_connections.py`: pinpoints which link is broken
- Verified in sandbox with a real Mosquitto broker: dashboard-before-broker retry,
  mock Pi -> MQTT -> classify -> DB, login, history, PDF/CSV export, 401 without login,
  results published to motosira/result for the Pi display

## Not yet verified on real hardware

- INMP441 capture on the Pi (channel count/overlay may need adjusting on first run)
- RPM sensor
- Pi ↔ PC MQTT over the network
- 3.5" TFT LCD output (`pi_display.py` is still terminal-only)
