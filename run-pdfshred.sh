#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

if command -v python3 >/dev/null 2>&1; then
  PY=python3
elif command -v python >/dev/null 2>&1; then
  PY=python
else
  echo "Python 3.10+ is required."
  exit 1
fi

if ! "$PY" -c "import customtkinter, fitz, PIL" >/dev/null 2>&1; then
  echo "Installing Python packages..."
  "$PY" -m pip install -r requirements.txt
fi

if ! "$PY" -c "import tkinter" >/dev/null 2>&1; then
  echo "Tk is missing. On Debian/Kali/Parrot run:"
  echo "  sudo apt install python3-tk python3-pip tesseract-ocr tesseract-ocr-eng"
  exit 1
fi

exec "$PY" app.py "$@"
