"""
MOTOSIRA — create/update .env (used by setup_pc.bat and setup_pi.sh)

    python tools/make_env.py                       # PC: broker = localhost
    python tools/make_env.py --broker 192.168.1.20 # Pi: broker = the PC's IP

Existing values are kept; only missing keys (or --broker) are written.
"""
import argparse
import os
import secrets

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENV_PATH = os.path.join(ROOT, ".env")


def read_env():
    values = {}
    if os.path.exists(ENV_PATH):
        for line in open(ENV_PATH, encoding="utf-8"):
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                values[k.strip()] = v.strip()
    return values


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--broker", help="MQTT broker host/IP (dashboard PC)")
    args = ap.parse_args()

    env = read_env()
    env.setdefault("SECRET_KEY", secrets.token_hex(32))
    env.setdefault("MOTOSIRA_USER", "admin")
    env.setdefault("MOTOSIRA_PASS", "motosira123")
    env.setdefault("MOTOSIRA_PASS_HASH", "")
    env.setdefault("MOTOSIRA_MIC_CHANNELS", "1")
    if args.broker:
        env["MOTOSIRA_BROKER"] = args.broker
    env.setdefault("MOTOSIRA_BROKER", "localhost")

    with open(ENV_PATH, "w", encoding="utf-8") as f:
        f.write("# MOTOSIRA local settings — never commit this file\n")
        for k, v in env.items():
            f.write(f"{k}={v}\n")

    print(f".env ready at {ENV_PATH}")
    print(f"  Login   : {env['MOTOSIRA_USER']} / {env['MOTOSIRA_PASS']}  (change MOTOSIRA_PASS before any public demo)")
    print(f"  Broker  : {env['MOTOSIRA_BROKER']}")


if __name__ == "__main__":
    main()
