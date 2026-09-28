"""
MOTOSIRA — standalone MQTT audio-topic listener (debug/dev tool).
Prints incoming raw audio payloads without running the full dashboard.
Useful for verifying the Pi -> MQTT link independently of Flask/SocketIO.
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import json
import time
import paho.mqtt.client as mqtt  # type: ignore
import config

print("=== MOTOSIRA Dashboard Receiver (debug tool) ===")
print(f"Listening on topic: {config.MQTT_TOPIC_AUDIO}")
print("Waiting for data from Pi...\n")


def on_connect(client, userdata, flags, rc):
    if rc == 0:
        print("Connected to MQTT broker!")
        client.subscribe(config.MQTT_TOPIC_AUDIO)
        print(f"Subscribed to {config.MQTT_TOPIC_AUDIO}\n")
    else:
        print(f"Connection failed with code {rc}")


def on_message(client, userdata, msg):
    data = json.loads(msg.payload.decode())
    print(f"Received recording #{data.get('recording_id')}")
    print(f"  Model       : {data.get('model', '—')}")
    print(f"  Sample rate : {data.get('sample_rate')} Hz")
    print(f"  Duration    : {data.get('duration')}s")
    print(f"  Samples     : {data.get('samples_count')}")
    print(f"  RPM         : {data.get('rpm', 'sensor not connected')}")
    print(f"  Timestamp   : {time.strftime('%H:%M:%S', time.localtime(data.get('timestamp', time.time())))}")
    print()


client = mqtt.Client()
client.on_connect = on_connect
client.on_message = on_message
client.connect(config.MQTT_BROKER, config.MQTT_PORT, 60)
client.loop_forever()
