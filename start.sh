#!/usr/bin/env bash
# One-click startup: activates the venv (if present) and starts the server.
# Run this from the project root: ./start.sh
#
# First-time setup still needs to happen once before this works:
#   python3 -m venv venv
#   source venv/bin/activate
#   pip install -r requirements.txt
set -e

if [ ! -f venv/bin/activate ]; then
    echo "No virtual environment found at ./venv"
    echo "Run this first, one line at a time:"
    echo "  python3 -m venv venv"
    echo "  source venv/bin/activate"
    echo "  pip install -r requirements.txt"
    exit 1
fi

source venv/bin/activate
echo "Starting NPL NSW Intelligence Engine on http://127.0.0.1:8000/ui/"
uvicorn npl_engine.server:app --reload
