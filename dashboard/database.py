"""
MOTOSIRA — SQLite session log
Stores every diagnostic result with model, signal-quality, and RPM metadata.
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import sqlite3
import json
import config


def init_db():
    os.makedirs(os.path.dirname(config.DB_PATH), exist_ok=True)
    conn = sqlite3.connect(config.DB_PATH)
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS recordings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            recording_id INTEGER,
            timestamp REAL,
            sample_rate INTEGER,
            duration INTEGER,
            classification TEXT,
            confidence REAL,
            severity INTEGER,
            action TEXT,
            features TEXT,
            model TEXT,
            signal_quality TEXT,
            snr_db REAL,
            peak_dbfs REAL,
            rpm INTEGER,
            latency_ms INTEGER
        )
    ''')
    # Migrate DBs created by earlier versions of this file.
    c.execute("PRAGMA table_info(recordings)")
    cols = [row[1] for row in c.fetchall()]
    for col, coltype in [("model", "TEXT"), ("signal_quality", "TEXT"),
                          ("snr_db", "REAL"), ("peak_dbfs", "REAL"), ("rpm", "INTEGER"),
                          ("latency_ms", "INTEGER")]:
        if col not in cols:
            c.execute(f"ALTER TABLE recordings ADD COLUMN {col} {coltype}")
    conn.commit()
    conn.close()
    print("Database initialized!")


def save_recording(recording_id, timestamp, sample_rate, duration,
                    classification, confidence, severity, action, features,
                    model=None, signal_quality=None, snr_db=None,
                    peak_dbfs=None, rpm=None, latency_ms=None):
    conn = sqlite3.connect(config.DB_PATH)
    c = conn.cursor()
    c.execute('''
        INSERT INTO recordings
        (recording_id, timestamp, sample_rate, duration, classification,
         confidence, severity, action, features, model, signal_quality,
         snr_db, peak_dbfs, rpm, latency_ms)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        recording_id, timestamp, sample_rate, duration, classification,
        confidence, severity, action, json.dumps(features.tolist()),
        model or config.DEFAULT_MODEL, signal_quality, snr_db, peak_dbfs, rpm,
        latency_ms
    ))
    conn.commit()
    new_id = c.lastrowid
    conn.close()
    return new_id


def get_recent(limit=20):
    conn = sqlite3.connect(config.DB_PATH)
    c = conn.cursor()
    c.execute('''
        SELECT id, timestamp, classification, confidence, severity, action,
               model, signal_quality, snr_db, peak_dbfs, rpm, latency_ms
        FROM recordings ORDER BY timestamp DESC LIMIT ?
    ''', (limit,))
    rows = c.fetchall()
    conn.close()
    return rows


def get_by_id(row_id):
    conn = sqlite3.connect(config.DB_PATH)
    c = conn.cursor()
    c.execute('''
        SELECT id, timestamp, classification, confidence, severity, action,
               model, signal_quality, snr_db, peak_dbfs, rpm, latency_ms
        FROM recordings WHERE id = ?
    ''', (row_id,))
    row = c.fetchone()
    conn.close()
    return row


def get_stats():
    """Per-class and per-model counts, for the Dashboard view."""
    conn = sqlite3.connect(config.DB_PATH)
    c = conn.cursor()
    c.execute("SELECT classification, COUNT(*) FROM recordings GROUP BY classification")
    by_class = dict(c.fetchall())
    c.execute("SELECT model, COUNT(*) FROM recordings GROUP BY model")
    by_model = dict(c.fetchall())
    c.execute("SELECT COUNT(*) FROM recordings")
    total = c.fetchone()[0]
    conn.close()
    return {"total": total, "by_class": by_class, "by_model": by_model}


if __name__ == "__main__":
    import numpy as np
    import time
    init_db()
    test_features = np.random.rand(config.N_MFCC)
    save_recording(1, time.time(), config.SAMPLE_RATE, config.DURATION,
                   "normal", 0.95, 0, "Engine OK", test_features,
                   model="Honda TMX 125 Alpha", signal_quality="GOOD",
                   snr_db=18.2, peak_dbfs=-6.4, rpm=1450)
    save_recording(2, time.time(), config.SAMPLE_RATE, config.DURATION,
                   "knocking", 0.87, 3, "Check fuel grade", test_features,
                   model="Rusi Macho 125", signal_quality="GOOD",
                   snr_db=15.1, peak_dbfs=-4.1, rpm=2100)
    print("Recent:", get_recent(5))
    print("Stats:", get_stats())
