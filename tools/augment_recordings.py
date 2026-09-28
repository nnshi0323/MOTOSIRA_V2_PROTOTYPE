"""
MOTOSIRA — real-recording augmentation tool

Multiplies a SMALL set of REAL recordings (per class, per motorcycle
model) into a larger training set using pitch shift, time stretch,
background noise mixing, gain variation, and time-crop -- as already
described in the thesis defense Q&A prep as the data-augmentation
contingency for classes with limited sample counts.

This tool NEVER fabricates a fault. Every output file is a transformed
copy of a real recording you actually captured. Nothing is invented.

Usage (augment a small set of real knocking recordings):
    python tools/augment_recordings.py \
        --source model/training_data/knocking/honda_tmx_125_alpha/raw \
        --class knocking \
        --model honda_tmx_125_alpha \
        --count 8

Optional: mix in real recorded shop background noise instead of
synthetic noise, if you have separate ambient-only recordings:
    python tools/augment_recordings.py \
        --source model/training_data/knocking/honda_tmx_125_alpha/raw \
        --class knocking \
        --model honda_tmx_125_alpha \
        --count 8 \
        --noise-dir model/training_data/_ambient_noise
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import argparse
import json
import random
import numpy as np       # type: ignore
import soundfile as sf   # type: ignore
import librosa            # type: ignore
import config


def load_wav(path, sr=config.SAMPLE_RATE):
    audio, file_sr = sf.read(path)
    if audio.ndim > 1:
        audio = audio.mean(axis=1)
    if file_sr != sr:
        audio = librosa.resample(audio.astype(np.float32), orig_sr=file_sr, target_sr=sr)
    return audio.astype(np.float32)


def pitch_shift(audio, sr, semitones):
    return librosa.effects.pitch_shift(audio, sr=sr, n_steps=semitones)


def time_stretch(audio, rate):
    stretched = librosa.effects.time_stretch(audio, rate=rate)
    # Keep output duration consistent with config.DURATION by pad/trim
    target_len = int(config.SAMPLE_RATE * config.DURATION)
    if len(stretched) > target_len:
        start = random.randint(0, len(stretched) - target_len)
        stretched = stretched[start:start + target_len]
    elif len(stretched) < target_len:
        stretched = np.pad(stretched, (0, target_len - len(stretched)))
    return stretched


def apply_gain(audio, gain_db):
    factor = 10 ** (gain_db / 20)
    return np.clip(audio * factor, -1.0, 1.0)


def mix_noise(audio, sr, noise_files, snr_db):
    """Mix in real ambient noise if provided, else fall back to shaped
    (pink-ish) noise -- clearly logged either way in the manifest."""
    if noise_files:
        noise_path = random.choice(noise_files)
        noise = load_wav(noise_path, sr)
        if len(noise) < len(audio):
            reps = int(np.ceil(len(audio) / len(noise)))
            noise = np.tile(noise, reps)
        start = random.randint(0, len(noise) - len(audio))
        noise = noise[start:start + len(audio)]
        source = "real_ambient_recording"
    else:
        # Pink-ish noise via filtered white noise -- an approximation,
        # logged as such, not a substitute for real ambient recordings.
        white = np.random.normal(0, 1, len(audio)).astype(np.float32)
        b = [0.049922035, -0.095993537, 0.050612699, -0.004408786]
        a = [1, -2.494956002, 2.017265875, -0.522189400]
        from scipy.signal import lfilter  # type: ignore
        noise = lfilter(b, a, white).astype(np.float32)
        source = "synthetic_pink_noise_approximation"

    sig_rms = np.sqrt(np.mean(audio ** 2)) + 1e-12
    noise_rms = np.sqrt(np.mean(noise ** 2)) + 1e-12
    target_noise_rms = sig_rms / (10 ** (snr_db / 20))
    noise = noise * (target_noise_rms / noise_rms)
    return np.clip(audio + noise, -1.0, 1.0), source


def random_time_crop_shift(audio, sr, max_shift_s=0.15):
    shift = int(random.uniform(-max_shift_s, max_shift_s) * sr)
    return np.roll(audio, shift)


def augment_one(audio, sr, noise_files):
    """Apply a randomized combination of real-signal-preserving transforms."""
    params = {}

    semitones = round(random.uniform(-1.5, 1.5), 2)
    audio = pitch_shift(audio, sr, semitones)
    params["pitch_shift_semitones"] = semitones

    rate = round(random.uniform(0.92, 1.08), 3)
    audio = time_stretch(audio, rate)
    params["time_stretch_rate"] = rate

    gain_db = round(random.uniform(-3, 3), 2)
    audio = apply_gain(audio, gain_db)
    params["gain_db"] = gain_db

    snr_db = round(random.uniform(10, 25), 1)
    audio, noise_source = mix_noise(audio, sr, noise_files, snr_db)
    params["noise_snr_db"] = snr_db
    params["noise_source"] = noise_source

    audio = random_time_crop_shift(audio, sr)
    params["time_shift_applied"] = True

    return audio, params


def augment(source_dir, label, model_slug, count, noise_dir=None, sr=config.SAMPLE_RATE):
    if not os.path.isdir(source_dir):
        raise FileNotFoundError(f"Source directory not found: {source_dir}")

    source_files = [f for f in os.listdir(source_dir) if f.endswith('.wav')]
    if not source_files:
        raise FileNotFoundError(
            f"No real .wav recordings found in {source_dir}. "
            f"This tool multiplies REAL recordings you already captured -- "
            f"record the real (small-sample) anomaly clips first."
        )

    noise_files = None
    if noise_dir and os.path.isdir(noise_dir):
        noise_files = [os.path.join(noise_dir, f) for f in os.listdir(noise_dir) if f.endswith('.wav')]
        if noise_files:
            print(f"Using {len(noise_files)} real ambient noise recording(s) from {noise_dir}")
        else:
            print(f"--noise-dir given but no .wav files found in it; falling back to synthetic noise approximation.")

    out_dir = os.path.join(config.TRAINING_DIR, label, model_slug)
    os.makedirs(out_dir, exist_ok=True)

    manifest = []
    total = 0
    for src_name in source_files:
        src_path = os.path.join(source_dir, src_name)
        base_audio = load_wav(src_path, sr)

        for i in range(count):
            audio, params = augment_one(base_audio, sr, noise_files)
            out_name = f"aug_{os.path.splitext(src_name)[0]}_{i:03d}.wav"
            out_path = os.path.join(out_dir, out_name)
            sf.write(out_path, audio, sr)

            manifest.append({
                "file": out_path, "class": label, "model": model_slug,
                "source_real_recording": src_path,
                "augmented": True, "fabricated": False,
                "params": params,
            })
            total += 1
            print(f"  Wrote {out_path} (from real source: {src_name})")

    manifest_path = os.path.join(config.TRAINING_DIR, f"augmentation_manifest_{label}_{model_slug}.json")
    with open(manifest_path, 'w') as f:
        json.dump(manifest, f, indent=2)

    print(f"\n{len(source_files)} real recording(s) -> {total} augmented training samples.")
    print(f"Manifest (for disclosure/audit): {manifest_path}")
    print("\nEvery output file is a transformed copy of a real recording -- no fault")
    print("was fabricated. Cite this augmentation step in your methodology per the")
    print("defense-script Q&A contingency already on file.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--source", required=True,
                         help="Folder of REAL recordings for this class+model to multiply")
    parser.add_argument("--class", dest="label", required=True, choices=config.CLASSES,
                         help="Fault class these recordings belong to")
    parser.add_argument("--model", required=True,
                         help="Motorcycle model slug, e.g. honda_tmx_125_alpha")
    parser.add_argument("--count", type=int, default=8,
                         help="How many augmented variants to generate per real source file")
    parser.add_argument("--noise-dir", default=None,
                         help="Optional folder of real ambient shop-noise .wav recordings to mix in")
    args = parser.parse_args()
    augment(args.source, args.label, args.model, args.count, args.noise_dir)
