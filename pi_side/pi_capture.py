"""
MOTOSIRA — Raspberry Pi audio capture (real hardware)

Captures from the INMP441 I2S MEMS microphone via the Pi's ALSA I2S
driver (must be enabled first — see pi_side/README_PI_SETUP.md) and
publishes each recording over MQTT for the dashboard to classify.

Hardware gotcha handled here: the INMP441 outputs 24-bit audio packed
into 32-bit I2S frames. We capture as int32 and right-shift by
config.MIC_SHIFT_BITS to recover the real 24-bit sample value before
sending it on — sending the raw 32-bit frame instead produces
near-silent / clipped-sounding audio at the dashboard.

Optional: reads engine RPM from a KY-024 Hall-effect sensor via GPIO
interrupt counting over the capture window, if config.RPM_SENSOR_ENABLED.
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import json
import time
import numpy as np           # type: ignore
import sounddevice as sd     # type: ignore
import paho.mqtt.client as mqtt  # type: ignore
import config

# ── Optional RPM sensor (Raspberry Pi GPIO only) ──────────────
_rpm_pulse_count = 0
_gpio_ready = False
if config.RPM_SENSOR_ENABLED:
    try:
        import RPi.GPIO as GPIO  # type: ignore

        def _on_pulse(channel):
            global _rpm_pulse_count
            _rpm_pulse_count += 1

        GPIO.setmode(GPIO.BCM)
        GPIO.setup(config.RPM_GPIO_PIN, GPIO.IN, pull_up_down=GPIO.PUD_UP)
        GPIO.add_event_detect(config.RPM_GPIO_PIN, GPIO.FALLING,
                               callback=_on_pulse, bouncetime=2)
        _gpio_ready = True
        print(f"RPM sensor armed on GPIO{config.RPM_GPIO_PIN}")
    except (ImportError, RuntimeError) as e:
        print(f"RPM sensor unavailable ({e}) — continuing without RPM data.")
        _gpio_ready = False


def read_rpm(window_seconds):
    """RPM = (pulses in window / revs-per-pulse) / window-minutes."""
    global _rpm_pulse_count
    if not _gpio_ready:
        return None
    pulses = _rpm_pulse_count
    _rpm_pulse_count = 0
    revs = pulses / config.RPM_MAGNETS_PER_REV
    rpm = revs / (window_seconds / 60.0)
    return int(round(rpm))


def unpack_i2s_24in32(int32_block):
    return np.right_shift(int32_block.astype(np.int32), config.MIC_SHIFT_BITS)


def select_input_device():
    print("Available audio input devices:")
    devices = sd.query_devices()
    candidates = []
    for i, d in enumerate(devices):
        if d['max_input_channels'] > 0:
            print(f"  [{i}] {d['name']} ({d['max_input_channels']} ch, "
                  f"{int(d['default_samplerate'])} Hz)")
            candidates.append(i)
    if not candidates:
        raise RuntimeError("No input audio devices found. Check I2S driver setup "
                            "(see pi_side/README_PI_SETUP.md).")
    # Prefer a device whose name hints at I2S/INMP441, else first candidate.
    for i in candidates:
        name = devices[i]['name'].lower()
        if 'i2s' in name or 'inmp' in name or 'googlevoicehat' in name:
            return i
    return candidates[0]


def select_motorcycle_model():
    print("\nSelect motorcycle model under test:")
    for i, m in enumerate(config.MOTORCYCLE_MODELS, 1):
        tag = " (primary)" if m == config.PRIMARY_MODEL else ""
        print(f"  [{i}] {m}{tag}")
    while True:
        choice = input(f"Model [1-{len(config.MOTORCYCLE_MODELS)}]: ").strip()
        if choice.isdigit() and 1 <= int(choice) <= len(config.MOTORCYCLE_MODELS):
            return config.MOTORCYCLE_MODELS[int(choice) - 1]
        print("Invalid choice, try again.")


def record_audio(device_index, duration=config.DURATION, native_rate=config.MIC_NATIVE_RATE):
    """Capture int32 I2S frames, correct the 24-in-32 packing, then
    resample down to config.SAMPLE_RATE for the classifier pipeline."""
    frames = int(duration * native_rate)
    # The I2S overlay often exposes the INMP441 as a STEREO device; asking for
    # mono then fails. Try the configured channel count, fall back to stereo,
    # and keep the LEFT channel (INMP441 L/R pin tied to GND = left).
    last_err = None
    for ch in dict.fromkeys([config.MIC_CHANNELS, 2]):
        try:
            block = sd.rec(frames, samplerate=native_rate, channels=ch,
                           dtype='int32', device=device_index)
            sd.wait()
            break
        except Exception as e:  # PortAudioError: invalid channel count / rate
            last_err = e
    else:
        raise RuntimeError(f"Could not record from device {device_index}: {last_err}. "
                           f"Check I2S setup (pi_side/README_PI_SETUP.md).")
    mono = block[:, 0] if block.ndim > 1 else block.flatten()
    corrected = unpack_i2s_24in32(mono)

    if native_rate != config.SAMPLE_RATE:
        import librosa  # local import: only needed here, keeps startup light
        float_audio = corrected.astype(np.float32) / (2 ** 23)
        resampled = librosa.resample(float_audio, orig_sr=native_rate,
                                      target_sr=config.SAMPLE_RATE)
        corrected = (resampled * (2 ** 23)).astype(np.int32)

    return corrected.tolist()


def main():
    print("=== MOTOSIRA Pi Audio Capture (INMP441 / I2S) ===")
    print(f"Target sample rate : {config.SAMPLE_RATE} Hz (native {config.MIC_NATIVE_RATE} Hz)")
    print(f"Duration           : {config.DURATION}s per recording")
    print(f"MQTT Broker        : {config.MQTT_BROKER}:{config.MQTT_PORT}")

    motorcycle_model = select_motorcycle_model()
    print(f"\nRecording against: {motorcycle_model}\n")

    device_index = select_input_device()
    print(f"Using input device index: {device_index}")

    client = mqtt.Client()
    client.reconnect_delay_set(min_delay=1, max_delay=10)
    while True:
        try:
            client.connect(config.MQTT_BROKER, config.MQTT_PORT, 60)
            break
        except Exception as e:
            print(f"Cannot reach MQTT broker at {config.MQTT_BROKER}:{config.MQTT_PORT} ({e}).")
            print("  Is the PC's Mosquitto running (start_broker.bat) and is MOTOSIRA_BROKER in .env the PC's IP?")
            print("  Retrying in 3s... (Ctrl+C to quit)")
            time.sleep(3)
    client.loop_start()
    print("Connected to MQTT broker!\n")

    recording_num = 1
    try:
        while True:
            print(f"[Recording {recording_num}] Capturing {config.DURATION}s "
                  f"({motorcycle_model})...")
            samples = record_audio(device_index)
            rpm = read_rpm(config.DURATION)

            payload = json.dumps({
                "recording_id": recording_num,
                "sample_rate": config.SAMPLE_RATE,
                "duration": config.DURATION,
                "samples_count": len(samples),
                "samples": samples,
                "bit_depth": 24,
                "model": motorcycle_model,
                "rpm": rpm,
                "timestamp": time.time(),
            })

            client.publish(config.MQTT_TOPIC_AUDIO, payload)
            rpm_note = f", RPM={rpm}" if rpm is not None else ""
            print(f"[Recording {recording_num}] Sent — {len(samples)} samples{rpm_note}\n")

            recording_num += 1
            time.sleep(2)

    except KeyboardInterrupt:
        print("\nStopping...")
        client.loop_stop()
        client.disconnect()
        if _gpio_ready:
            GPIO.cleanup()
        print("Done.")


def collect(label, seconds, sessions):
    """
    DATA COLLECTION MODE — records LONG raw sessions with the INMP441 and
    saves them as labeled .wav files into raw_data/<class>/<model_slug>/
    on the Pi. No MQTT, no classification. Afterwards copy raw_data/ to
    the dashboard PC and run:  python tools/prepare_dataset.py
    which segments them into 3s clips and quality-filters them — the
    same path your phone recordings take.

    Each session must be confirmed (mechanic-verified label) before it is
    kept, per the thesis data-collection protocol.
    """
    import soundfile as sf  # type: ignore
    from dashboard.processor import low_pass_filter, signal_quality

    motorcycle_model = select_motorcycle_model()
    slug = config.model_slug(motorcycle_model)
    out_dir = os.path.join(config.BASE_DIR, "raw_data", label, slug)
    os.makedirs(out_dir, exist_ok=True)
    device_index = select_input_device()

    print(f"\n=== COLLECT MODE: {label.upper()} / {motorcycle_model} ===")
    print(f"{seconds}s per session, {sessions} session(s). Saving to {out_dir}")
    print("Engine running at target RPM, mic ~30cm from engine block.\n")

    kept = 0
    for n in range(1, sessions + 1):
        input(f"[Session {n}/{sessions}] Press ENTER to start recording...")
        print(f"  Recording {seconds}s...")
        samples = np.asarray(record_audio(device_index, duration=seconds), dtype=np.float32)
        audio = np.clip(samples / (2 ** 23), -1.0, 1.0)   # 24-bit -> float [-1, 1]

        q, snr, peak = signal_quality(low_pass_filter(audio, config.SAMPLE_RATE))
        print(f"  Captured {len(audio) / config.SAMPLE_RATE:.1f}s | quality={q} "
              f"SNR={snr:.1f} dB peak={peak:.1f} dBFS")
        if peak < -40:
            print("  WARNING: very quiet — check mic wiring/placement before keeping.")

        ans = input(f"  Mechanic confirms this is {label.upper()}? Keep it? [y/N]: ").strip().lower()
        if ans != "y":
            print("  Discarded.\n")
            continue
        name = f"pi_{time.strftime('%Y%m%d_%H%M%S')}.wav"
        sf.write(os.path.join(out_dir, name), audio, config.SAMPLE_RATE, subtype="PCM_16")
        kept += 1
        print(f"  Saved {name}\n")

    print(f"Done. {kept}/{sessions} session(s) saved to {out_dir}")
    print("Next (on the PC): copy raw_data/ over, then run  python tools/prepare_dataset.py")
    if _gpio_ready:
        GPIO.cleanup()


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="MOTOSIRA Pi capture")
    ap.add_argument("--collect", choices=config.CLASSES,
                    help="data collection mode: record labeled raw sessions for training")
    ap.add_argument("--seconds", type=int, default=30, help="collect mode: seconds per session")
    ap.add_argument("--sessions", type=int, default=5, help="collect mode: number of sessions")
    args = ap.parse_args()
    if args.collect:
        collect(args.collect, args.seconds, args.sessions)
    else:
        main()
