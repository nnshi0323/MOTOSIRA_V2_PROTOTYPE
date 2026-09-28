"""
MOTOSIRA — environment sanity check.
Run on both the dev PC (dashboard/training) and the Pi (capture) — the
Pi-only libs (sounddevice, RPi.GPIO) are reported separately since a dev
PC without audio hardware may legitimately fail those.
"""
import sys
print(f"Python: {sys.version}\n")

core_libs = [
    "librosa", "soundfile", "numpy", "scipy",
    "sklearn", "joblib", "pandas", "matplotlib",
    "paho.mqtt", "flask", "flask_socketio", "flask_limiter",
    "reportlab", "werkzeug", "dotenv",
]

pi_libs = ["sounddevice", "RPi.GPIO"]

def check(libs, label):
    print(f"-- {label} --")
    all_good = True
    for lib in libs:
        try:
            __import__(lib)
            print(f"  OK       {lib}")
        except ImportError:
            print(f"  MISSING  {lib}")
            all_good = False
    return all_good

core_ok = check(core_libs, "Core (dashboard + training)")
print()
pi_ok = check(pi_libs, "Raspberry Pi capture only")

print()
if core_ok:
    print("Core libraries OK — dashboard/training ready.")
else:
    print("Core libraries missing. Run: pip install -r requirements.txt")

if not pi_ok:
    print("Pi capture libraries missing — expected on a dev PC; "
          "install on the Raspberry Pi itself (pip install sounddevice RPi.GPIO).")
