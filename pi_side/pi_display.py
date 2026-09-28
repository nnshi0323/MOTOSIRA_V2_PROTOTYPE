"""
MOTOSIRA — Pi-side result display

Terminal preview on dev machines; swap the print block below for real
3.5" TFT LCD calls (e.g. adafruit-circuitpython-rgb-display) on-device.
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import json
import time
import paho.mqtt.client as mqtt  # type: ignore
import config

print("=== MOTOSIRA Pi Display Receiver ===")


def display_result(result):
    label = result.get('classification', 'unknown').replace('_', ' ').upper()
    confidence = int(result.get('confidence', 0) * 100)
    action = result.get('action', '')
    severity = result.get('severity', 0)
    timestamp = result.get('timestamp', '--:--:--')
    model = result.get('model', config.DEFAULT_MODEL)
    quality = result.get('signal_quality', '—')
    rpm = result.get('rpm')
    rpm_str = f"{rpm} RPM" if rpm else "sensor not connected"

    os.system('cls' if os.name == 'nt' else 'clear')
    print("=" * 44)
    print("          MOTOSIRA DIAGNOSIS")
    print("=" * 44)
    print(f"  Model     : {model}")
    print(f"  Status    : {label}")
    print(f"  Confidence: {confidence}%")
    print(f"  Severity  : {severity} / 3")
    print(f"  Quality   : {quality}")
    print(f"  RPM       : {rpm_str}")
    print(f"  Time      : {timestamp}")
    print("-" * 44)
    print(f"  Action: {action}")
    print("=" * 44)


def on_connect(client, userdata, flags, rc):
    if rc == 0:
        print("Connected to MQTT broker!")
        client.subscribe(config.MQTT_TOPIC_RESULT)
        print(f"Listening for results on: {config.MQTT_TOPIC_RESULT}\n")


def on_message(client, userdata, msg):
    try:
        result = json.loads(msg.payload.decode())
        display_result(result)
    except Exception as e:
        print(f"Error: {e}")


def _connect_with_retry(client):
    while True:
        try:
            client.connect(config.MQTT_BROKER, config.MQTT_PORT, 60)
            return
        except Exception as e:
            print(f"MQTT broker not reachable at {config.MQTT_BROKER}:{config.MQTT_PORT} ({e}). Retrying in 3s...")
            time.sleep(3)


client = mqtt.Client()
client.on_connect = on_connect
client.on_message = on_message
_connect_with_retry(client)
client.loop_forever()
