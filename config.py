"""
MOTOSIRA — Central configuration
Motorcycle Sound-based Identification & Reporting Assistant
"""
import os

# Load per-machine settings (.env) so the SAME code runs on the PC and the Pi.
try:
    from dotenv import load_dotenv  # type: ignore
    load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))
except ImportError:
    pass

# ── Paths ──────────────────────────────────────────────────
BASE_DIR      = os.path.dirname(os.path.abspath(__file__))
MODEL_PATH    = os.path.join(BASE_DIR, "model", "trained", "motosira_rf.pkl")
SCALER_PATH   = os.path.join(BASE_DIR, "model", "trained", "scaler.pkl")
META_PATH     = os.path.join(BASE_DIR, "model", "trained", "model_meta.json")
TRAINING_DIR  = os.path.join(BASE_DIR, "model", "training_data")
LOG_DIR       = os.path.join(BASE_DIR, "logs")
DB_PATH       = os.path.join(BASE_DIR, "dashboard", "motosira.db")
REPORT_DIR    = os.path.join(BASE_DIR, "logs", "reports")

# ── Audio capture ────────────────────────────────────────────
SAMPLE_RATE   = 22050          # Hz — resampled target (mic runs at 44.1k/48k natively)
DURATION      = 3              # seconds per diagnostic capture
N_MFCC        = 40             # MFCC coefficients (13–40 range per literature)
MIC_NATIVE_RATE = 44100        # INMP441 typical native sample rate on I2S
MIC_BIT_DEPTH   = 32           # INMP441 sends 24-bit samples packed in 32-bit I2S frames
MIC_SHIFT_BITS  = 8            # right-shift to recover the 24-bit value from the 32-bit frame
MIC_CHANNELS    = int(os.getenv("MOTOSIRA_MIC_CHANNELS", "1"))  # auto-falls back to 2 if the I2S card needs stereo

# ── Signal quality thresholds ────────────────────────────────
# Peak dBFS below this is treated as clipping/too loud; above the noise
# threshold with insufficient headroom is treated as noisy input.
SIGNAL_CLIP_DBFS   = -1.0
SIGNAL_NOISE_FLOOR_DBFS = -40.0
SIGNAL_GOOD_SNR_DB = 12.0

# ── MQTT ──────────────────────────────────────────────────────
MQTT_BROKER        = os.getenv("MOTOSIRA_BROKER", "localhost")   # Pi: set to the dashboard PC's IP in .env
MQTT_PORT          = 1883
MQTT_TOPIC_AUDIO   = "motosira/audio"
MQTT_TOPIC_RESULT  = "motosira/result"

# ── RPM sensor (optional Hall-effect KY-024) ─────────────────
RPM_SENSOR_ENABLED = True      # set False if the Hall sensor isn't wired
RPM_GPIO_PIN        = 17       # BCM numbering
RPM_MAGNETS_PER_REV = 1        # single magnet on flywheel/crankshaft

# ── Motorcycle models in scope ────────────────────────────────
# Honda TMX 125 Alpha is the primary platform and must reach full
# functional maturity before Rusi Macho 125 / Suzuki Smash Carb are
# addressed (staged research design). All three share the same
# acoustic fault classes below.
MOTORCYCLE_MODELS = ["Honda TMX 125 Alpha", "Rusi Macho 125", "Suzuki Smash Carb"]
PRIMARY_MODEL      = MOTORCYCLE_MODELS[0]
DEFAULT_MODEL       = MOTORCYCLE_MODELS[0]

def model_slug(name: str) -> str:
    """Filesystem/URL-safe slug for a motorcycle model name."""
    return name.lower().replace(" ", "_")

# ── Fault classes ──────────────────────────────────────────────
CLASSES = ["normal", "knocking", "misfire", "valve_ticking"]

# Dataset target per objectives: ~1,000 recordings total, evenly
# distributed across classes and models.
DATASET_TARGET_TOTAL = 1000
DATASET_TARGET_PER_CLASS = DATASET_TARGET_TOTAL // len(CLASSES)              # 250
DATASET_TARGET_PER_CLASS_PER_MODEL = DATASET_TARGET_PER_CLASS // len(MOTORCYCLE_MODELS)  # ~83

SEVERITY = {
    "normal": {
        "level": 0, "color": "green", "action": "Engine OK — no action needed",
        "steps": ["No fault detected in this capture.",
                   "Continue normal operation and scheduled maintenance."]
    },
    "valve_ticking": {
        "level": 1, "color": "amber", "action": "Check valve clearance",
        "steps": ["Let the engine cool, then remove the valve cover.",
                   "Check intake/exhaust valve clearance with a feeler gauge against spec.",
                   "Adjust clearance if out of tolerance; re-check after adjustment.",
                   "Re-run a diagnosis to confirm the ticking has cleared."]
    },
    "misfire": {
        "level": 2, "color": "rust", "action": "Check spark plug and carburetor",
        "steps": ["Inspect the spark plug for fouling, wear, or incorrect gap.",
                   "Check carburetor air/fuel mixture and idle adjustment.",
                   "Inspect fuel line and filter for blockage.",
                   "Replace spark plug if worn; re-run diagnosis after adjustment."]
    },
    "knocking": {
        "level": 3, "color": "red", "action": "Check fuel grade and ignition timing",
        "steps": ["Stop the engine — knocking under load can damage internals.",
                   "Verify the fuel octane rating matches manufacturer spec.",
                   "Check ignition timing against spec; correct if advanced.",
                   "Inspect for carbon buildup in the combustion chamber.",
                   "Do not resume normal operation until knocking is resolved."]
    },
}

# ── Diagnostic cycle target (per literature: Lamrini & Nasim 2023) ──
LATENCY_TARGET_MIN_S = 1
LATENCY_TARGET_MAX_S = 3
