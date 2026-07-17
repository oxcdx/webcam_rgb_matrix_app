#!/bin/bash
set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
echo "Creating venv (with system-site-packages for rpi-rgb-led-matrix)..."
python3 -m venv --system-site-packages "$SCRIPT_DIR/venv"
echo "Installing requirements into venv..."
"$SCRIPT_DIR/venv/bin/pip" install --upgrade pip
"$SCRIPT_DIR/venv/bin/pip" install -r "$SCRIPT_DIR/requirements.txt"
echo "Setup complete. Run: bash run.sh"
