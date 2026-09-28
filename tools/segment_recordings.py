"""
MOTOSIRA — recording segmentation tool

Cuts long, continuous field recordings (e.g. a phone/recorder capturing
a full engine idle session) into fixed-length clips matching
config.DURATION (3s), the unit model/train.py and the live capture
pipeline both expect. Skips a short lead-in (mic handling noise) and
drops any trailing fragment shorter than a usable threshold rather than
padding it with silence.

Usage:
    python tools/segment_recordings.py \
        --source /path/to/raw_long_recordings \
        --class normal \
        --model honda_tmx_125_alpha
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import argparse
import numpy as np      # type: ignore
import soundfile as sf  # type: ignore
import config


def segment_file(path, clip_len_s, skip_start_s, min_tail_s, target_sr):
    audio, sr = sf.read(path)
    if audio.ndim > 1:
        audio = audio.mean(axis=1)
    audio = audio.astype(np.float32)
    if np.max(np.abs(audio)) > 1.5:  # raw int16 range, not yet normalized
        audio = audio / 32768.0

    if sr != target_sr:
        import librosa  # type: ignore
        audio = librosa.resample(audio, orig_sr=sr, target_sr=target_sr)
        sr = target_sr

    start_sample = int(skip_start_s * sr)
    clip_len = int(clip_len_s * sr)
    min_tail = int(min_tail_s * sr)

    clips = []
    pos = start_sample
    while pos + min_tail <= len(audio):
        end = pos + clip_len
        if end <= len(audio):
            clips.append(audio[pos:end])
        else:
            remaining = audio[pos:]
            if len(remaining) >= min_tail:
                pass  # trailing fragment shorter than clip_len: dropped, not padded
        pos += clip_len

    return clips, sr


def main(source_dir, label, model_slug, clip_len_s, skip_start_s, min_tail_s):
    out_dir = os.path.join(config.TRAINING_DIR, label, model_slug)
    os.makedirs(out_dir, exist_ok=True)

    files = [f for f in os.listdir(source_dir) if f.lower().endswith('.wav')]
    if not files:
        print(f"No .wav files found in {source_dir}")
        return

    total_clips = 0
    for f in sorted(files):
        path = os.path.join(source_dir, f)
        clips, sr = segment_file(path, clip_len_s, skip_start_s, min_tail_s, config.SAMPLE_RATE)
        base = os.path.splitext(f)[0]
        for i, clip in enumerate(clips):
            out_name = f"{label}_{base}_{i:03d}.wav"
            out_path = os.path.join(out_dir, out_name)
            sf.write(out_path, clip, sr)
        print(f"  {f}: {len(clips)} clip(s) -> {out_dir}")
        total_clips += len(clips)

    print(f"\n{len(files)} source recording(s) -> {total_clips} clips of {clip_len_s}s each.")
    print(f"Written to: {out_dir}")
    print("Run tools/validate_recordings.py on this folder next to confirm quality per-clip.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, help="Folder of long raw .wav recordings")
    parser.add_argument("--class", dest="label", required=True, choices=config.CLASSES)
    parser.add_argument("--model", required=True, help="Motorcycle model slug")
    parser.add_argument("--clip-len", type=float, default=config.DURATION)
    parser.add_argument("--skip-start", type=float, default=0.5,
                         help="Seconds to skip at the start of each recording (mic handling noise)")
    parser.add_argument("--min-tail", type=float, default=2.5,
                         help="Minimum trailing seconds required to keep a final fragment")
    args = parser.parse_args()
    main(args.source, args.label, args.model, args.clip_len, args.skip_start, args.min_tail)
