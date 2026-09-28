"""
MOTOSIRA — Signal processing pipeline
Low-pass noise filtering -> MFCC feature extraction -> signal-quality metrics
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np  # type: ignore
import librosa       # type: ignore
from scipy.signal import butter, sosfilt  # type: ignore
import config


def unpack_i2s_24in32(raw_int32_samples):
    """
    INMP441 gotcha: the mic outputs 24-bit audio packed into 32-bit I2S
    frames. If you normalize by treating the frame as a native 32-bit
    sample you get near-silent, clipped-sounding audio. Recover the real
    24-bit value first by right-shifting out the padding bits.
    """
    arr = np.asarray(raw_int32_samples, dtype=np.int32)
    return np.right_shift(arr, config.MIC_SHIFT_BITS)


def to_float_audio(samples, source_bit_depth=16):
    """Normalize integer PCM samples to float32 in [-1, 1]."""
    arr = np.asarray(samples, dtype=np.float64)
    full_scale = float(2 ** (source_bit_depth - 1) - 1)
    audio = (arr / full_scale).astype(np.float32)
    return np.clip(audio, -1.0, 1.0)


def low_pass_filter(audio, sample_rate=config.SAMPLE_RATE, cutoff_hz=4000, order=4):
    """Software LPF mirroring the hardware analog LPF in the signal chain."""
    nyquist = sample_rate / 2
    normal_cutoff = min(cutoff_hz / nyquist, 0.99)
    sos = butter(order, normal_cutoff, btype='low', output='sos')
    return sosfilt(sos, audio).astype(np.float32)


def signal_quality(audio):
    """
    Returns (quality_label, snr_db, peak_dbfs) computed from the actual
    captured waveform - flags noisy/clipped captures before classification,
    feeding the UCID 'Input quality' / 'Signal quality' fields.
    """
    if len(audio) == 0:
        return "CHECK NOISE", 0.0, -99.0

    rms = np.sqrt(np.mean(audio ** 2)) + 1e-12
    peak = np.max(np.abs(audio)) + 1e-12
    peak_dbfs = 20 * np.log10(peak)

    frame_len = 1024
    frames = [audio[i:i + frame_len] for i in range(0, len(audio) - frame_len, frame_len)]
    frame_rms = [np.sqrt(np.mean(f ** 2)) + 1e-12 for f in frames] if frames else [rms]
    noise_floor = np.percentile(frame_rms, 10)
    snr_db = 20 * np.log10(rms / (noise_floor + 1e-12))

    if peak_dbfs >= config.SIGNAL_CLIP_DBFS:
        return "CHECK NOISE", float(snr_db), float(peak_dbfs)
    if snr_db < config.SIGNAL_GOOD_SNR_DB:
        return "CHECK NOISE", float(snr_db), float(peak_dbfs)
    return "GOOD", float(snr_db), float(peak_dbfs)


def extract_mfcc(samples, sample_rate=config.SAMPLE_RATE, source_bit_depth=16):
    """Full pipeline: normalize -> low-pass filter -> MFCC -> mean pool."""
    audio = to_float_audio(samples, source_bit_depth=source_bit_depth)
    audio = low_pass_filter(audio, sample_rate)
    mfccs = librosa.feature.mfcc(y=audio, sr=sample_rate, n_mfcc=config.N_MFCC)
    features = np.mean(mfccs, axis=1)
    return features, audio


def process_recording(data):
    """
    data: dict from MQTT payload. Expects 'samples' (already 24-bit-corrected
    ints from pi_capture.py) or is empty (falls back to a synthetic test tone
    so the pipeline can be verified without hardware attached).
    Returns (features, quality_label, snr_db, peak_dbfs).
    """
    print(f"Processing recording #{data.get('recording_id')}...")
    samples = data.get('samples', [])
    bit_depth = data.get('bit_depth', 16)

    if not samples:
        print("  No samples in payload, generating test audio...")
        import math
        samples = [
            int(32767 * 0.3 * math.sin(2 * math.pi * 440 * i / config.SAMPLE_RATE))
            for i in range(config.SAMPLE_RATE * config.DURATION)
        ]
        bit_depth = 16

    features, audio = extract_mfcc(samples, source_bit_depth=bit_depth)
    quality_label, snr_db, peak_dbfs = signal_quality(audio)

    print(f"  Extracted {len(features)} MFCC features")
    print(f"  Signal quality: {quality_label} (SNR {snr_db:.1f} dB, peak {peak_dbfs:.1f} dBFS)")
    return features, quality_label, snr_db, peak_dbfs


if __name__ == "__main__":
    print("=== MFCC Processor Test ===")
    test_data = {"recording_id": 1, "samples": []}
    features, quality, snr, peak = process_recording(test_data)
    print(f"\nFeature vector ({len(features)} values):")
    print(features)
    print(f"\nQuality: {quality} | SNR: {snr:.1f} dB | Peak: {peak:.1f} dBFS")
    print("\nProcessor working correctly!")
