#!/usr/bin/env bash
set -e

cd "$(dirname "$0")"

# Create venv if missing
if [ ! -d ".venv" ]; then
  echo "Creating virtual environment..."
  python3 -m venv .venv
fi

# Activate
source .venv/bin/activate

# Install / upgrade deps
pip install -q --upgrade pip
pip install -q -r requirements.txt

echo ""
echo "  Starting pdfer..."
echo ""
python app.py
