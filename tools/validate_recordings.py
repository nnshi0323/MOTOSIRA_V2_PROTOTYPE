"""
MOTOSIRA — recording validation tool

Sanity-checks real captured .wav files BEFORE they go into training:
format, sample rate, duration, channel count, clipping/silence, and
whether the actual signal-processing pipeline (low-pass filter, MFCC,
signal-quality/SNR) produces sane output on them.

This does NOT classify or train anything -- it only tells you whether
your recordings are usable input for model/train.py later.

Usage:
    python tools/validate_recordings.py --dir model/training_data/normal/honda_tmx_125_alpha
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import argparse
import numpy as np      # type: ignore
import soundfile as sf  # type: ignore
import config
from dashboard.processor import low_pass_filter, signal_quality
import librosa  # type: ignore


def check_file(path):
    issues = []
    info = sf.info(path)

    if info.channels != 1:
        issues.append(f"NOT MONO ({info.channels} channels) — will be downmixed, but re-record mono if possible")

    if abs(info.duration - config.DURATION) > 0.3:
        issues.append(f"DURATION off target: {info.duration:.2f}s (target {config.DURATION}s)")

    audio, sr = sf.read(path)
    if audio.ndim > 1:
        audio = audio.mean(axis=1)

    if sr != config.SAMPLE_RATE:
        audio_rs = librosa.resample(audio.astype(np.float32), orig_sr=sr, target_sr=config.SAMPLE_RATE)
    else:
        audio_rs = audio.astype(np.float32)

    peak = np.max(np.abs(audio_rs)) if len(audio_rs) else 0
    if peak >= 0.999:
        issues.append("CLIPPING detected (peak at/near max) — mic gain too high, re-record quieter")
    if peak < 0.02:
        issues.append(f"VERY QUIET (peak={peak:.4f}) — mic too far/gain too low, likely unusable")

    filtered = low_pass_filter(audio_rs, config.SAMPLE_RATE)
    quality_label, snr_db, peak_dbfs = signal_quality(filtered)

    mfccs = librosa.feature.mfcc(y=filtered, sr=config.SAMPLE_RATE, n_mfcc=config.N_MFCC)
    feat_vector = np.mean(mfccs, axis=1)
    if np.isnan(feat_vector).any() or np.isinf(feat_vector).any():
        issues.append("MFCC extraction produced NaN/Inf — file likely corrupt or silent")

    return {
        "file": os.path.basename(path),
        "duration": info.duration,
        "sample_rate": info.samplerate,
        "channels": info.channels,
        "peak_amplitude": round(float(peak), 4),
        "signal_quality": quality_label,
        "snr_db": round(snr_db, 1),
        "peak_dbfs": round(peak_dbfs, 1),
        "mfcc_dims": len(feat_vector),
        "issues": issues,
    }


def main(directory):
    files = [f for f in os.listdir(directory) if f.endswith('.wav')]
    if not files:
        print(f"No .wav files found in {directory}")
        return

    print(f"Validating {len(files)} file(s) in {directory}\n")
    print(f"{'File':<30} {'Dur(s)':>7} {'SR':>7} {'Ch':>3} {'Peak':>7} {'Quality':>12} {'SNR(dB)':>8}")
    print("-" * 85)

    good, flagged = 0, 0
    for f in sorted(files):
        r = check_file(os.path.join(directory, f))
        flag = " <-- CHECK" if r["issues"] else ""
        print(f"{r['file']:<30} {r['duration']:>7.2f} {r['sample_rate']:>7} {r['channels']:>3} "
              f"{r['peak_amplitude']:>7.3f} {r['signal_quality']:>12} {r['snr_db']:>8.1f}{flag}")
        for issue in r["issues"]:
            print(f"    - {issue}")
        if r["issues"]:
            flagged += 1
        else:
            good += 1

    print("-" * 85)
    print(f"\n{good}/{len(files)} clean, {flagged}/{len(files)} flagged for review.")
    if flagged:
        print("Review flagged files before including them in training -- re-record if needed.")
    else:
        print("All files passed basic sanity checks. Safe to use as training input.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dir", required=True, help="Folder of .wav files to validate")
    args = parser.parse_args()
    main(args.dir)
