#!/usr/bin/env bash
# MOTOSIRA - run on the Raspberry Pi.
#   ./run_pi.sh              live diagnosis (capture -> PC dashboard)
#   ./run_pi.sh check        connection + mic check
#   ./run_pi.sh display      terminal result display
#   ./run_pi.sh --collect <class> [--seconds N] [--sessions N]   record training data
cd "$(dirname "$0")"
source venv/bin/activate
case "$1" in
  check)   python tools/check_connections.py ;;
  display) python pi_side/pi_display.py ;;
  *)       python pi_side/pi_capture.py "$@" ;;
esac
