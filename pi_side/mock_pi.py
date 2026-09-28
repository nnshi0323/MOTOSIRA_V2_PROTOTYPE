"""
MOTOSIRA — Mock Pi simulator (no hardware required)

Publishes synthetic audio + fake RPM over MQTT, cycling through the 3
motorcycle models, so the dashboard/classifier pipeline can be exercised
end-to-end before real hardware/data is available.
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import time
import random
import math
import json
import paho.mqtt.client as mqtt  # type: ignore
import config

print("=== MOTOSIRA Mock Pi Simulator ===")
print(f"Connecting to MQTT broker at {config.MQTT_BROKER}:{config.MQTT_PORT}...")

def _connect_with_retry(client):
    while True:
        try:
            client.connect(config.MQTT_BROKER, config.MQTT_PORT, 60)
            return
        except Exception as e:
            print(f"MQTT broker not reachable at {config.MQTT_BROKER}:{config.MQTT_PORT} ({e}). Retrying in 3s...")
            time.sleep(3)


client = mqtt.Client()
_connect_with_retry(client)
client.loop_start()
print("Connected!\n")


def generate_fake_audio():
    samples = []
    freq = random.choice([100, 200, 440, 660, 880])
    for i in range(config.SAMPLE_RATE * config.DURATION):
        val = int(32767 * 0.3 * math.sin(2 * math.pi * freq * i / config.SAMPLE_RATE))
        samples.append(val)
    return samples


def fake_rpm():
    # Idle-ish range with occasional rev, just for UI/pipeline testing.
    return random.choice([None, 1350, 1500, 2200, 3100, 4200])


try:
    recording_num = 1
    while True:
        model = config.MOTORCYCLE_MODELS[(recording_num - 1) % len(config.MOTORCYCLE_MODELS)]
        rpm = fake_rpm()
        print(f"[Recording {recording_num}] Simulating {config.DURATION}s ({model})...")
        samples = generate_fake_audio()

        payload = json.dumps({
            "recording_id": recording_num,
            "sample_rate": config.SAMPLE_RATE,
            "duration": config.DURATION,
            "samples_count": len(samples),
            "samples": samples,
            "bit_depth": 16,
            "model": model,
            "rpm": rpm,
            "timestamp": time.time(),
        })

        client.publish(config.MQTT_TOPIC_AUDIO, payload)
        rpm_note = f", RPM={rpm}" if rpm is not None else ", RPM=sensor not connected"
        print(f"[Recording {recording_num}] Sent to dashboard via MQTT ({model}{rpm_note})\n")

        recording_num += 1
        time.sleep(5)

except KeyboardInterrupt:
    print("\nSimulator stopped.")
    client.loop_stop()
    client.disconnect()
