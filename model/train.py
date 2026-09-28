"""
MOTOSIRA — Random Forest training pipeline

Expected dataset layout (per model_meta scope: ~1,000 recordings total,
~250/class, split across the 3 motorcycle models):

    model/training_data/<class>/<motorcycle_model_slug>/*.wav
    e.g. model/training_data/knocking/honda_tmx_125_alpha/rec001.wav

Flat layout model/training_data/<class>/*.wav (no per-model subfolder)
is also supported for backward compatibility / early single-model data.
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
import librosa
import joblib
import json
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split, cross_val_score
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import classification_report, confusion_matrix
import config
from dashboard.processor import low_pass_filter

MODEL_SLUGS = {config.model_slug(m): m for m in config.MOTORCYCLE_MODELS}


def extract_features(file_path):
    try:
        audio, sr = librosa.load(file_path, sr=config.SAMPLE_RATE, duration=config.DURATION)
        if len(audio) < config.SAMPLE_RATE * config.DURATION:
            audio = np.pad(audio, (0, config.SAMPLE_RATE * config.DURATION - len(audio)))
        # Same preprocessing as the live pipeline (dashboard/processor.py):
        # low-pass filter BEFORE MFCC, so training and diagnosis see
        # identically-processed input.
        audio = low_pass_filter(audio.astype(np.float32), sr)
        mfccs = librosa.feature.mfcc(y=audio, sr=sr, n_mfcc=config.N_MFCC)
        return np.mean(mfccs, axis=1)
    except Exception as e:
        print(f"  Error loading {file_path}: {e}")
        return None


def load_dataset():
    X, y, models_used = [], [], []
    counts = {label: {m: 0 for m in config.MOTORCYCLE_MODELS} for label in config.CLASSES}

    print("Loading dataset...")
    for label in config.CLASSES:
        class_dir = os.path.join(config.TRAINING_DIR, label)
        if not os.path.exists(class_dir):
            print(f"  WARNING: {class_dir} not found, skipping")
            continue

        # Per-model subfolders (preferred layout)
        subdirs = [d for d in os.listdir(class_dir)
                   if os.path.isdir(os.path.join(class_dir, d))]
        if subdirs:
            for sub in subdirs:
                model_name = MODEL_SLUGS.get(sub, sub)
                sub_path = os.path.join(class_dir, sub)
                files = [f for f in os.listdir(sub_path) if f.endswith(('.wav', '.mp3', '.ogg'))]
                print(f"  {label} / {model_name}: {len(files)} files")
                for fname in files:
                    feats = extract_features(os.path.join(sub_path, fname))
                    if feats is not None:
                        X.append(feats)
                        y.append(config.CLASSES.index(label))
                        models_used.append(model_name)
                        if model_name in counts[label]:
                            counts[label][model_name] += 1
        else:
            # Flat fallback: class folder has .wav files directly, no model tag
            files = [f for f in os.listdir(class_dir) if f.endswith(('.wav', '.mp3', '.ogg'))]
            print(f"  {label} (flat, no model subfolder): {len(files)} files")
            for fname in files:
                feats = extract_features(os.path.join(class_dir, fname))
                if feats is not None:
                    X.append(feats)
                    y.append(config.CLASSES.index(label))
                    models_used.append("unspecified")

    return np.array(X), np.array(y), models_used, counts


def print_dataset_balance(counts):
    print("\nDataset balance (target: ~%d per class-model cell):" %
          config.DATASET_TARGET_PER_CLASS_PER_MODEL)
    header = "  {:<15}".format("class") + "".join(f"{m[:18]:>20}" for m in config.MOTORCYCLE_MODELS)
    print(header)
    for label in config.CLASSES:
        row = "  {:<15}".format(label)
        for m in config.MOTORCYCLE_MODELS:
            row += f"{counts[label].get(m, 0):>20}"
        print(row)


def train(allow_synthetic=False):
    print("=== MOTOSIRA Model Training ===\n")
    X, y, models_used, counts = load_dataset()
    synthetic = False

    if len(X) == 0:
        print("\nNo audio files found in training_data folders.")
        print("Expected layout:")
        for label in config.CLASSES:
            print(f"  model/training_data/{label}/<motorcycle_model_slug>/*.wav")
        print("Model slugs:", ", ".join(MODEL_SLUGS.keys()))
        if not allow_synthetic:
            print("\nNo model trained. (Synthetic pipeline test only with --allow-synthetic.)")
            sys.exit(1)
        print("\n--allow-synthetic: SYNTHETIC data, pipeline verification only —")
        print("do NOT report these metrics as real performance.")
        X, y = generate_synthetic_data()
        synthetic = True
    else:
        print_dataset_balance(counts)

    present = sorted(set(int(v) for v in y))
    present_names = [config.CLASSES[i] for i in present]
    if len(present) < 2:
        print(f"\nOnly one class has data: {present_names}.")
        print("A classifier needs at least 2 classes to learn a difference; a one-class")
        print("model would answer that class for EVERY sound. No model was saved.")
        print("Add real recordings for at least one anomaly class, then re-run.")
        sys.exit(1)
    missing = [c for c in config.CLASSES if c not in present_names]
    if missing:
        print(f"\nWARNING: no data yet for {missing}. The model can only ever predict {present_names}.")

    min_count = min(int((y == c).sum()) for c in present)
    if min_count < 5:
        print(f"\nSmallest class has only {min_count} clips; need >= 5 per class for 5-fold CV.")
        sys.exit(1)

    print(f"\nDataset: {len(X)} samples, {len(present)} classes present: {present_names}")
    print(f"Features per sample: {X.shape[1]}")

    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)

    X_train, X_test, y_train, y_test = train_test_split(
        X_scaled, y, test_size=0.2, random_state=42, stratify=y
    )

    print(f"\nTrain: {len(X_train)} | Test: {len(X_test)}")
    print("\nTraining Random Forest...")

    clf = RandomForestClassifier(
        n_estimators=100, max_depth=None,
        min_samples_split=2, min_samples_leaf=1,
        random_state=42, n_jobs=-1
    )
    clf.fit(X_train, y_train)

    cv_scores = cross_val_score(clf, X_scaled, y, cv=5)
    print(f"\nCross-validation accuracy: {cv_scores.mean():.2%} (+/- {cv_scores.std():.2%})")

    y_pred = clf.predict(X_test)
    print(f"Test accuracy: {(y_pred == y_test).mean():.2%}")

    print("\nClassification Report:")
    print(classification_report(y_test, y_pred, labels=present, target_names=present_names,
                                zero_division=0))

    print(f"Confusion Matrix (rows=true, cols=predicted, order={present_names}):")
    print(confusion_matrix(y_test, y_pred, labels=present))

    os.makedirs(os.path.join(config.BASE_DIR, "model", "trained"), exist_ok=True)
    joblib.dump(clf, config.MODEL_PATH)
    joblib.dump(scaler, config.SCALER_PATH)

    meta = {
        "classes": config.CLASSES,
        "classes_trained": present_names,
        "motorcycle_models": config.MOTORCYCLE_MODELS,
        "n_features": X.shape[1],
        "n_estimators": 100,
        "training_samples": len(X),
        "cv_accuracy": float(cv_scores.mean()),
        "test_accuracy": float((y_pred == y_test).mean()),
        "trained_on_synthetic_data": synthetic,
        "samples_per_class": {n: int((y == i).sum()) for i, n in zip(present, present_names)},
        "trained_at": __import__("time").strftime("%Y-%m-%d %H:%M:%S"),
    }
    with open(config.META_PATH, 'w') as f:
        json.dump(meta, f, indent=2)

    print(f"\nModel saved to: {config.MODEL_PATH}")
    print(f"Scaler saved to: {config.SCALER_PATH}")
    print(f"Metadata saved to: {config.META_PATH}")
    print("\nTraining complete!")


def generate_synthetic_data():
    """Pipeline-verification only — not real acoustic data. Do not report
    these metrics as evidence of classifier performance in the paper."""
    import math
    print("Generating synthetic audio features...")
    X, y = [], []
    np.random.seed(42)
    patterns = {0: (440, 0.1), 1: (660, 0.2), 2: (220, 0.3), 3: (880, 0.4)}
    for label_idx, (freq, noise) in patterns.items():
        for _ in range(50):
            samples = np.array([
                int(32767 * 0.3 * math.sin(2 * math.pi * freq * i / config.SAMPLE_RATE))
                for i in range(config.SAMPLE_RATE * config.DURATION)
            ], dtype=np.float32) / 32767.0
            samples += np.random.normal(0, noise, len(samples))
            mfccs = librosa.feature.mfcc(y=samples, sr=config.SAMPLE_RATE, n_mfcc=config.N_MFCC)
            X.append(np.mean(mfccs, axis=1))
            y.append(label_idx)
    return np.array(X), np.array(y)


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--allow-synthetic", action="store_true",
                    help="pipeline test only; never use for reported results")
    train(allow_synthetic=ap.parse_args().allow_synthetic)
