"""
MOTOSIRA — one-command dataset preparation

Takes RAW, long recordings (phone/recorder or pi_capture --collect) and
turns them into clean, training-ready 3-second clips in one step:

    raw_data/<class>/<model_slug>/*.wav
          |  segment into config.DURATION clips (skip 0.5s lead-in,
          |  drop tail fragments < 2.5s, never pad with silence)
          |  quality filter (same signal_quality() the live system uses)
          v
    model/training_data/<class>/<model_slug>/<class>_<source>_<nnn>.wav

Rejected clips are NOT deleted silently: they are written to
raw_data/_rejected/ so a teammate can listen and double-check them.
A per-run report is written to logs/dataset_report_<timestamp>.json
(counts per source file, kept vs rejected, SNR per clip) for the paper.

Usage:
    python tools/prepare_dataset.py                 # process every class/model found
    python tools/prepare_dataset.py --class normal --model honda_tmx_125_alpha
    python tools/prepare_dataset.py --dry-run       # report only, write nothing
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import argparse
import json
import time
import numpy as np      # type: ignore
import soundfile as sf  # type: ignore
import config
from dashboard.processor import low_pass_filter, signal_quality

RAW_DIR = os.path.join(config.BASE_DIR, "raw_data")
REJECT_DIR = os.path.join(RAW_DIR, "_rejected")
SKIP_START_S = 0.5
MIN_TAIL_S = 2.5


def load_mono(path, target_sr):
    audio, sr = sf.read(path, always_2d=False)
    if audio.ndim > 1:
        audio = audio.mean(axis=1)
    audio = audio.astype(np.float32)
    if np.max(np.abs(audio)) > 1.5:          # un-normalized int16 range
        audio = audio / 32768.0
    if sr != target_sr:
        import librosa  # type: ignore
        audio = librosa.resample(audio, orig_sr=sr, target_sr=target_sr)
    return audio


def segment(audio, sr):
    clip_len = int(config.DURATION * sr)
    pos = int(SKIP_START_S * sr)
    clips = []
    while pos + clip_len <= len(audio):
        clips.append(audio[pos:pos + clip_len])
        pos += clip_len
    # trailing fragment shorter than a full clip is dropped (never padded)
    return clips


def process(label, slug, dry_run, report):
    src_dir = os.path.join(RAW_DIR, label, slug)
    files = sorted(f for f in os.listdir(src_dir) if f.lower().endswith(".wav"))
    if not files:
        return
    out_dir = os.path.join(config.TRAINING_DIR, label, slug)
    rej_dir = os.path.join(REJECT_DIR, label, slug)
    if not dry_run:
        os.makedirs(out_dir, exist_ok=True)
        os.makedirs(rej_dir, exist_ok=True)

    print(f"\n[{label} / {slug}] {len(files)} raw file(s)")
    for f in files:
        base = os.path.splitext(f)[0]
        audio = load_mono(os.path.join(src_dir, f), config.SAMPLE_RATE)
        clips = segment(audio, config.SAMPLE_RATE)
        kept = rejected = 0
        clip_log = []
        for i, clip in enumerate(clips):
            q, snr, peak = signal_quality(low_pass_filter(clip, config.SAMPLE_RATE))
            name = f"{label}_{base}_{i:03d}.wav"
            ok = (q == "GOOD")
            if not dry_run:
                sf.write(os.path.join(out_dir if ok else rej_dir, name),
                         clip, config.SAMPLE_RATE, subtype="PCM_16")
            kept += ok
            rejected += (not ok)
            clip_log.append({"clip": name, "kept": ok, "snr_db": round(snr, 1),
                             "peak_dbfs": round(peak, 1)})
        dur = len(audio) / config.SAMPLE_RATE
        print(f"  {f:<28} {dur:6.1f}s -> {len(clips):3d} clips | kept {kept:3d} | rejected {rejected:3d}")
        report["files"].append({"class": label, "model": slug, "source": f,
                                "duration_s": round(dur, 2), "segments": len(clips),
                                "kept": kept, "rejected": rejected, "clips": clip_log})
        report["totals"]["segments"] += len(clips)
        report["totals"]["kept"] += kept
        report["totals"]["rejected"] += rejected


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--class", dest="label", choices=config.CLASSES)
    parser.add_argument("--model", help="model slug, e.g. honda_tmx_125_alpha")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if not os.path.isdir(RAW_DIR):
        print(f"No raw_data/ folder. Create raw_data/<class>/<model_slug>/ and put raw .wav files in it.")
        return

    report = {"run_at": time.strftime("%Y-%m-%d %H:%M:%S"), "dry_run": args.dry_run,
              "clip_seconds": config.DURATION, "skip_start_s": SKIP_START_S,
              "quality_rule": f"GOOD if SNR >= {config.SIGNAL_GOOD_SNR_DB} dB and peak < {config.SIGNAL_CLIP_DBFS} dBFS",
              "files": [], "totals": {"segments": 0, "kept": 0, "rejected": 0}}

    labels = [args.label] if args.label else config.CLASSES
    for label in labels:
        class_dir = os.path.join(RAW_DIR, label)
        if not os.path.isdir(class_dir):
            continue
        slugs = [args.model] if args.model else sorted(os.listdir(class_dir))
        for slug in slugs:
            if os.path.isdir(os.path.join(class_dir, slug)):
                process(label, slug, args.dry_run, report)

    t = report["totals"]
    print(f"\nTOTAL: {t['segments']} segments -> {t['kept']} kept, {t['rejected']} rejected")
    if not args.dry_run and t["segments"]:
        os.makedirs(config.LOG_DIR, exist_ok=True)
        path = os.path.join(config.LOG_DIR, f"dataset_report_{time.strftime('%Y%m%d_%H%M%S')}.json")
        with open(path, "w") as fh:
            json.dump(report, fh, indent=2)
        print(f"Report: {path}")
        print(f"Rejected clips (listen to double-check): {REJECT_DIR}")


if __name__ == "__main__":
    main()
