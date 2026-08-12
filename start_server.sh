#!/bin/bash
# One-click starter for Khanya Test Maker (local development)
# Run: bash start_server.sh

cd "$(dirname "$0")"

echo "=== Khanya Test Maker - Starting local server ==="
echo

# Install dependencies if needed
if ! python3 -c "import flask; import reportlab; from docx import Document" 2>/dev/null; then
    echo "Installing required packages..."
    pip install -r requirements.txt
fi

echo
echo "Starting Flask server..."
echo "Open your browser at: http://127.0.0.1:5001"
echo "Press Ctrl+C to stop."
echo

python3 flask_app.py
