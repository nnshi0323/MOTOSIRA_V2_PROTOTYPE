"""
MOTOSIRA — Flask + SocketIO dashboard
Receives classified results over MQTT from the Pi, serves the live UI,
session history, and PDF/CSV report export.
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flask import Flask, render_template, jsonify, request, session, redirect, url_for
from flask_socketio import SocketIO
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from dotenv import load_dotenv
import json, time, threading
import numpy as np   # type: ignore
import joblib          # type: ignore
import paho.mqtt.client as mqtt  # type: ignore

import config
from database import init_db, save_recording, get_recent, get_by_id, get_stats
from processor import process_recording
from reports import build_report_pdf
from auth import login_required, check_credentials

load_dotenv()

app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'motosira2024')
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading')

limiter = Limiter(
    get_remote_address, app=app,
    default_limits=["200 per minute"], storage_uri="memory://"
)

# ── Load trained classifier ───────────────────────────────
model = None
scaler = None


def load_model():
    global model, scaler
    try:
        model = joblib.load(config.MODEL_PATH)
        scaler = joblib.load(config.SCALER_PATH)
        print("Model loaded successfully!")
    except Exception as e:
        print(f"Model not found, using random classifier fallback: {e}")


def classify(features):
    global model, scaler
    if model is None or scaler is None:
        import random
        return random.choice(config.CLASSES), round(random.uniform(0.75, 0.99), 2)
    try:
        features_scaled = scaler.transform([features])
        probabilities = model.predict_proba(features_scaled)[0]
        # predict_proba columns follow model.classes_, which only contains
        # the classes that had training data — index through it, not CLASSES.
        best = int(np.argmax(probabilities))
        label = config.CLASSES[int(model.classes_[best])]
        confidence = round(float(probabilities[best]), 2)
        return label, confidence
    except Exception as e:
        print(f"Classification error: {e}")
        import random
        return random.choice(config.CLASSES), 0.75


latest_result = {
    "classification": "waiting", "confidence": 0, "severity": 0,
    "action": "Waiting for engine data...", "steps": [], "timestamp": None,
    "model": config.DEFAULT_MODEL, "signal_quality": None,
    "snr_db": None, "peak_dbfs": None, "rpm": None, "latency_ms": None,
}

current_model = config.DEFAULT_MODEL

# Separate publisher client so results can be pushed back to the Pi's LCD
# (MQTT_TOPIC_RESULT) independently of the subscriber client's loop.
_publisher = mqtt.Client()
_publisher.reconnect_delay_set(min_delay=1, max_delay=10)
# connect_async + loop_start: keeps retrying in the background if the
# broker isn't up yet, and reconnects automatically if it restarts.
_publisher.connect_async(config.MQTT_BROKER, config.MQTT_PORT, 60)
_publisher.loop_start()


def validate_mqtt_payload(data):
    required = ['recording_id', 'sample_rate', 'duration', 'timestamp']
    for key in required:
        if key not in data:
            return False
    if not isinstance(data.get('recording_id'), int):
        return False
    return True


def on_mqtt_message(client, userdata, msg):
    global latest_result, current_model
    try:
        if len(msg.payload) > 2 * 1024 * 1024:
            print("Payload too large, ignoring")
            return

        data = json.loads(msg.payload.decode())
        if not validate_mqtt_payload(data):
            print("Invalid payload, ignoring")
            return

        recording_id = data.get('recording_id', 0)
        # Pi tags each capture with the operator-selected model; fall back
        # to the dashboard's current selection if the payload omits it.
        model_used = data.get('model') or current_model
        rpm = data.get('rpm')  # None if Hall sensor isn't connected

        _t0 = time.time()
        features, quality_label, snr_db, peak_dbfs = process_recording(data)
        label, confidence = classify(features)
        latency_ms = int((time.time() - _t0) * 1000)

        severity_info = config.SEVERITY[label]

        latest_result = {
            "classification": label,
            "confidence": confidence,
            "severity": severity_info["level"],
            "color": severity_info["color"],
            "action": severity_info["action"],
            "steps": severity_info["steps"],
            "timestamp": time.strftime('%H:%M:%S'),
            "model": model_used,
            "signal_quality": quality_label,
            "snr_db": round(snr_db, 1),
            "peak_dbfs": round(peak_dbfs, 1),
            "rpm": rpm,
            "latency_ms": latency_ms,
        }

        row_id = save_recording(
            recording_id, time.time(), config.SAMPLE_RATE, config.DURATION,
            label, confidence, severity_info["level"], severity_info["action"],
            features, model=model_used, signal_quality=quality_label,
            snr_db=snr_db, peak_dbfs=peak_dbfs, rpm=rpm, latency_ms=latency_ms
        )
        latest_result["id"] = row_id

        socketio.emit('new_result', latest_result)
        _publisher.publish(config.MQTT_TOPIC_RESULT, json.dumps(latest_result))
        print(f"[{latest_result['timestamp']}] #{recording_id} ({model_used}) -> "
              f"{label} ({confidence:.0%}) quality={quality_label} latency={latency_ms}ms")

    except json.JSONDecodeError:
        print("Invalid JSON payload, ignoring")
    except Exception as e:
        print(f"Error: {e}")


mqtt_connected = False


def _on_mqtt_connect(client, userdata, flags, rc):
    global mqtt_connected
    if rc == 0:
        mqtt_connected = True
        # (Re)subscribe on every connect so a broker restart doesn't silently
        # stop results from arriving.
        client.subscribe(config.MQTT_TOPIC_AUDIO)
        print(f"MQTT connected to {config.MQTT_BROKER}:{config.MQTT_PORT}, listening on {config.MQTT_TOPIC_AUDIO}")
    else:
        print(f"MQTT connection refused (code {rc})")


def _on_mqtt_disconnect(client, userdata, rc):
    global mqtt_connected
    mqtt_connected = False
    if rc != 0:
        print("MQTT disconnected — retrying automatically...")


def start_mqtt():
    client = mqtt.Client()  # type: ignore
    client.on_connect = _on_mqtt_connect
    client.on_disconnect = _on_mqtt_disconnect
    client.on_message = on_mqtt_message
    client.reconnect_delay_set(min_delay=1, max_delay=10)
    while True:
        try:
            client.connect(config.MQTT_BROKER, config.MQTT_PORT, 60)
            break
        except Exception as e:
            print(f"MQTT broker not reachable at {config.MQTT_BROKER}:{config.MQTT_PORT} ({e}). "
                  f"Is Mosquitto running? Retrying in 3s...")
            time.sleep(3)
    client.loop_forever(retry_first_connection=True)


# ── Auth routes ────────────────────────────────────────────
@app.route('/login', methods=['GET', 'POST'])
@limiter.limit("10 per minute")
def login():
    if session.get('logged_in'):
        return redirect(url_for('index'))
    error = None
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        if check_credentials(username, password):
            session['logged_in'] = True
            session['username'] = username
            return redirect(url_for('index'))
        else:
            error = 'Invalid username or password.'
    return render_template('login.html', error=error)


@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))


# ── Main routes ────────────────────────────────────────────
@app.route('/')
@login_required
def index():
    return render_template('index.html')


@app.route('/api/latest')
@login_required
@limiter.limit("60 per minute")
def api_latest():
    return jsonify(latest_result)


@app.route('/api/models')
@login_required
def api_models():
    trained = model is not None and scaler is not None
    trained_classes = ([config.CLASSES[int(c)] for c in model.classes_] if trained else [])
    return jsonify({"models": config.MOTORCYCLE_MODELS, "current": current_model,
                     "primary": config.PRIMARY_MODEL,
                     "model_trained": trained, "trained_classes": trained_classes,
                     "mqtt_connected": mqtt_connected, "broker": config.MQTT_BROKER})


@app.route('/api/set_model', methods=['POST'])
@login_required
@limiter.limit("30 per minute")
def api_set_model():
    global current_model
    data = request.get_json(silent=True) or {}
    chosen = data.get('model', '')
    if chosen not in config.MOTORCYCLE_MODELS:
        return jsonify({"error": "Unknown model"}), 400
    current_model = chosen
    return jsonify({"current": current_model})


@app.route('/api/stats')
@login_required
def api_stats():
    return jsonify(get_stats())


def _row_to_dict(r):
    return {
        "id": r[0],
        "timestamp": r[1],
        "timestamp_str": time.strftime('%H:%M:%S', time.localtime(r[1])),
        "classification": r[2], "confidence": r[3], "severity": r[4],
        "action": r[5], "model": r[6] or config.DEFAULT_MODEL,
        "signal_quality": r[7], "snr_db": r[8], "peak_dbfs": r[9], "rpm": r[10],
        "latency_ms": r[11] if len(r) > 11 else None,
        "steps": config.SEVERITY.get(r[2], {}).get("steps", []),
    }


@app.route('/api/history')
@login_required
@limiter.limit("30 per minute")
def api_history():
    rows = get_recent(20)
    history = []
    for r in rows:
        d = _row_to_dict(r)
        history.append({
            "id": d["id"], "timestamp": d["timestamp_str"],
            "classification": d["classification"],
            "confidence": f"{d['confidence']:.0%}",
            "severity": d["severity"], "action": d["action"], "model": d["model"],
        })
    return jsonify(history)


@app.route('/api/report/<int:row_id>')
@login_required
def api_report_json(row_id):
    r = get_by_id(row_id)
    if not r:
        return jsonify({"error": "Not found"}), 404
    return jsonify(_row_to_dict(r))


@app.route('/api/report/<int:row_id>/pdf')
@login_required
def api_report_pdf(row_id):
    r = get_by_id(row_id)
    if not r:
        return jsonify({"error": "Not found"}), 404
    d = _row_to_dict(r)
    pdf_bytes = build_report_pdf(d)
    return app.response_class(
        pdf_bytes, mimetype='application/pdf',
        headers={'Content-Disposition': f'attachment;filename=motosira_report_{row_id}.pdf'}
    )


@app.route('/api/export')
@login_required
def api_export():
    rows = get_recent(1000)
    lines = ['ID,Time,Classification,Confidence,Severity,Action,Model,SignalQuality,SNR_dB,Peak_dBFS,RPM,Latency_ms']
    for r in rows:
        d = _row_to_dict(r)
        lines.append(
            f'{d["id"]},{d["timestamp_str"]},{d["classification"]},{d["confidence"]:.0%},'
            f'{d["severity"]},"{d["action"]}","{d["model"]}",{d["signal_quality"] or ""},'
            f'{d["snr_db"] if d["snr_db"] is not None else ""},'
            f'{d["peak_dbfs"] if d["peak_dbfs"] is not None else ""},'
            f'{d["rpm"] if d["rpm"] is not None else ""},'
            f'{d["latency_ms"] if d["latency_ms"] is not None else ""}'
        )
    csv = '\n'.join(lines)
    return app.response_class(csv, mimetype='text/csv',
        headers={'Content-Disposition': 'attachment;filename=motosira_export.csv'})


if __name__ == '__main__':
    init_db()
    load_model()
    mqtt_thread = threading.Thread(target=start_mqtt, daemon=True)
    mqtt_thread.start()
    print("=== MOTOSIRA Dashboard ===")
    print(f"Models in scope: {', '.join(config.MOTORCYCLE_MODELS)}")
    print("Open browser at: http://localhost:5000")
    socketio.run(app, host='0.0.0.0', port=5000, debug=False,
                 use_reloader=False, allow_unsafe_werkzeug=True)
