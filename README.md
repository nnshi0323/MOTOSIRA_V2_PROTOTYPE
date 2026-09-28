# MOTOSIRA
**Motorcycle Sound-based Identification & Reporting Assistant**

Portable embedded diagnostic device that detects and classifies motorcycle
engine fault conditions in real time from acoustic signal analysis alone —
no OBD port, no electrical/ignition interface.

BS Computer Engineering thesis — Holy Angel University.

## Scope

| | |
|---|---|
| **Motorcycle models** | Honda TMX 125 Alpha (primary), Rusi Macho 125, Suzuki Smash Carb |
| **Fault classes** | Normal, Knocking, Misfire, Valve Ticking |
| **Dataset target** | ~1,000 recordings total (~250/class, ~83/class/model) |
| **Latency target** | 1–3 seconds per diagnostic cycle |
| **Hardware** | Raspberry Pi 4B, INMP441 I2S mic, 3.5" TFT LCD, microSD, optional KY-024 RPM sensor |

Honda TMX 125 Alpha must reach full functional maturity before Rusi Macho 125
/ Suzuki Smash Carb are addressed (staged research design). If either
secondary platform fails to meet targets within the study timeline, the
attempted methodology and root-cause analysis are documented rather than
omitted.

## Architecture

```
 [INMP441 mic] --I2S--> [Raspberry Pi 4]
                              |  low-pass filter -> MFCC (13-40 coeff)
                              |  optional RPM (Hall-effect, KY-024)
                              v
                         MQTT publish (motosira/audio)
                              |
                              v
                    [Dashboard PC: Flask + SocketIO]
                    - Random Forest classification
                    - SQLite session log
                    - Live web UI (SocketIO push)
                    - CSV + PDF report export
                              |
                              v
                    MQTT publish (motosira/result) --> [Pi LCD display]
```

## Repository layout

```
config.py                    Central configuration (models, classes, paths, thresholds)
requirements.txt             Python dependencies (dev PC + dashboard)
dashboard/
  app.py                     Flask + SocketIO server, MQTT subscriber, REST API
  auth.py                    Login (hashed password)
  database.py                SQLite session log
  processor.py                Low-pass filter, MFCC extraction, signal-quality metrics
  reports.py                  PDF diagnosis report generator (reportlab)
  receiver.py                 Standalone MQTT debug listener
  templates/
    index.html                Main dashboard UI (UCID-aligned)
    login.html                 Login screen
model/
  train.py                    Random Forest training (per-model-aware dataset loader)
  training_data/<class>/<model_slug>/*.wav   Labeled training audio
  trained/                     motosira_rf.pkl, scaler.pkl, model_meta.json (generated)
pi_side/
  pi_capture.py                Real INMP441 I2S capture + optional RPM sensor
  mock_pi.py                   Synthetic-data simulator (no hardware needed)
  pi_display.py                Terminal/LCD result display
  README_PI_SETUP.md           Raspberry Pi hardware + I2S driver setup
tools/
  check_setup.py               Environment/dependency check
```

## Quick start (dashboard PC)

```bash
python -m venv venv && source venv/bin/activate   # or venv\Scripts\activate on Windows
pip install -r requirements.txt
cp .env.example .env   # edit SECRET_KEY / MOTOSIRA_USER / MOTOSIRA_PASS

# terminal 1 — MQTT broker
mosquitto

# terminal 2 — dashboard (also starts the MQTT subscriber + trains-model loader)
python dashboard/app.py

# terminal 3 — no hardware yet? simulate a Pi:
python pi_side/mock_pi.py
```

Open `http://localhost:5000`.

## Training the classifier

1. Collect audio per the layout in `model/train.py`'s docstring:
   `model/training_data/<class>/<model_slug>/*.wav`
   (model slugs: `honda_tmx_125_alpha`, `rusi_macho_125`, `suzuki_smash_carb`)
2. Each recording must be verified/labeled by a licensed mechanic before
   being added, per the thesis methodology.
3. Run:
   ```bash
   python model/train.py
   ```
   If no real audio is found, training falls back to synthetic data for
   **pipeline verification only** — this is clearly flagged in
   `model_meta.json` (`trained_on_synthetic_data: true`) and must never be
   reported as real classifier performance.

## Real hardware (Raspberry Pi)

See `pi_side/README_PI_SETUP.md` for I2S driver setup (the INMP441 needs
the ALSA I2S overlay enabled before Python can see it — it is not a plug
-and-play USB mic), the 24-bit-in-32-bit sample gotcha, and the optional
RPM sensor wiring.

## UCID → software mapping

The dashboard UI (`dashboard/templates/index.html`) implements the V3 UCID
wireframe: sidebar navigation (Dashboard / New Diagnosis / Diagnosis Report
/ History / Help), the Capture → Analyze → Result → Report workflow
stepper, live Audio Capture + Live Engine Data panels, a Diagnosis Result
panel, and a Diagnosis Report view with real PDF export
(`/api/report/<id>/pdf`) alongside the full-session CSV export
(`/api/export`).

## Known limitations (declared, not hidden)

- RPM is only available if the optional KY-024 Hall-effect sensor is
  wired; otherwise the UI/report show "sensor not connected" rather than
  a fabricated value.
- Signal-quality ("GOOD" / "CHECK NOISE") is computed from peak level and
  an SNR estimate against a rolling noise floor — a practical proxy, not
  a calibrated acoustic instrument reading.
- The classifier does not interface with the motorcycle's electrical or
  ignition system; it is acoustic-only and cannot detect faults requiring
  compression testing or internal mechanical inspection.
