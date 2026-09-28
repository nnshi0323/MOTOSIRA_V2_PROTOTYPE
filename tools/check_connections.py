"""
MOTOSIRA — connection checker. Run on the PC or the Pi; it tells you
exactly which link is broken.

    python tools/check_connections.py

Checks:
  1. .env exists and which broker it points to
  2. MQTT broker reachable + a real publish/subscribe round trip
  3. (Pi) audio input devices, and whether an I2S/INMP441 device is visible
  4. (PC) trained model present or not
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import threading
import time
import config

OK, WARN, FAIL = "[ OK ]", "[WARN]", "[FAIL]"
problems = 0


def report(status, msg):
    global problems
    if status == FAIL:
        problems += 1
    print(f"{status} {msg}")


def check_env():
    path = os.path.join(config.BASE_DIR, ".env")
    if os.path.exists(path):
        report(OK, f".env found — broker = {config.MQTT_BROKER}:{config.MQTT_PORT}")
    else:
        report(WARN, ".env missing — run setup_pc.bat (PC) or setup_pi.sh (Pi). Using defaults.")


def check_mqtt():
    try:
        import paho.mqtt.client as mqtt  # type: ignore
    except ImportError:
        report(FAIL, "paho-mqtt not installed (pip install -r requirements.txt)")
        return
    got = threading.Event()
    topic = f"motosira/selftest/{os.getpid()}"
    client = mqtt.Client()
    client.on_message = lambda c, u, m: got.set()
    try:
        client.connect(config.MQTT_BROKER, config.MQTT_PORT, 10)
    except Exception as e:
        report(FAIL, f"Cannot reach MQTT broker at {config.MQTT_BROKER}:{config.MQTT_PORT} — {e}")
        print("       PC: is start_broker.bat running?  Pi: is MOTOSIRA_BROKER in .env the PC's IP,")
        print("       and did start_broker.bat add the firewall rule (run as administrator)?")
        return
    client.subscribe(topic)
    client.loop_start()
    time.sleep(0.5)
    client.publish(topic, "ping")
    if got.wait(3):
        report(OK, f"MQTT round trip works via {config.MQTT_BROKER}:{config.MQTT_PORT}")
    else:
        report(FAIL, "Connected to broker but message round trip failed")
    client.loop_stop()
    client.disconnect()


def check_audio():
    try:
        import sounddevice as sd  # type: ignore
    except Exception:
        report(WARN, "sounddevice not available — fine on the PC, required on the Pi")
        return
    try:
        devices = [d for d in sd.query_devices() if d["max_input_channels"] > 0]
    except Exception as e:
        report(WARN, f"Could not list audio devices: {e}")
        return
    if not devices:
        report(WARN, "No audio input devices (expected on a PC without a mic; on the Pi, I2S is not set up)")
        return
    i2s = [d for d in devices if any(k in d["name"].lower() for k in ("i2s", "inmp", "googlevoicehat", "voicehat"))]
    for d in devices:
        print(f"       input: {d['name']} ({d['max_input_channels']} ch, {int(d['default_samplerate'])} Hz)")
    if i2s:
        report(OK, f"I2S mic device visible: {i2s[0]['name']}")
    else:
        report(WARN, "No I2S device name found — on the Pi, re-run setup_pi.sh and reboot")


def check_model():
    if os.path.exists(config.MODEL_PATH) and os.path.exists(config.SCALER_PATH):
        report(OK, "Trained model found — dashboard will use real classification")
    else:
        report(WARN, "No trained model yet — dashboard will show 'UNTRAINED — results are random'")


if __name__ == "__main__":
    print("=== MOTOSIRA connection check ===")
    check_env()
    check_mqtt()
    check_audio()
    check_model()
    print("=" * 33)
    print("All required links OK." if problems == 0 else f"{problems} problem(s) — fix the [FAIL] lines above.")
    sys.exit(1 if problems else 0)
