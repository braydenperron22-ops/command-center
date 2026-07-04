#!/usr/bin/env bash
# One-shot setup: creates the venv, installs deps, and launches the dashboard.
set -e
cd "$(dirname "$0")"

python3 -m venv .venv
.venv/bin/pip install -q --only-binary :all: -r requirements.txt

echo ""
echo "Setup done. Starting the dashboard..."
echo "Leave this window open, or press Ctrl+C and run: .venv/bin/streamlit run app.py"
echo ""
.venv/bin/streamlit run app.py
