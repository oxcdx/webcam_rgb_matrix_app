#!/bin/bash
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_PYTHON="$SCRIPT_DIR/venv/bin/python3"
if [ ! -f "$VENV_PYTHON" ]; then
    echo "Venv not found. Run: bash setup_venv.sh"
    exit 1
fi
if [ "$(id -u)" -ne 0 ]; then
    exec sudo "$VENV_PYTHON" "$SCRIPT_DIR/app.py"
else
    exec "$VENV_PYTHON" "$SCRIPT_DIR/app.py"
fi
