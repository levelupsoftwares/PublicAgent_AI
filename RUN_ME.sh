#!/usr/bin/env bash
# PublicAgent AI — one-command local start (no Docker, no Node needed).
#
# Usage:
#   bash RUN_ME.sh
# Then open:  http://localhost:8000   →  click "Continue as Demo Citizen"
#
# What it does: creates a Python venv on first run, installs dependencies
# (skipped on later runs), seeds demo data automatically, and starts the
# server. The frontend is pre-built (frontend/dist) and served by the same
# server, so one port serves everything.
set -e
cd "$(dirname "$0")/backend"

if [ ! -d .venv ]; then
  echo ">>> Creating Python virtual environment (one-time)..."
  python3 -m venv .venv
fi
source .venv/bin/activate

echo ">>> Installing Python dependencies (skipped if already installed)..."
pip install -q -r requirements.txt

echo ""
echo "============================================================"
echo "  PublicAgent AI  →  http://localhost:8000"
echo "  Login: click 'Continue as Demo Citizen' (no password needed)"
echo "  Stop:  press Ctrl+C"
echo "============================================================"
echo ""
uvicorn app.main:app --port 8000
