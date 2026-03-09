#!/bin/bash
set -e

echo "Installing system dependencies..."

# Install system dependencies if not already present
if ! dpkg -s libxcb1 >/dev/null 2>&1; then
    apt-get update
    apt-get install -y \
        libxcb1 \
        libxcb-xinerama0 \
        libxrender1 \
        libxext6 \
        libxkbcommon0 \
        libxkbcommon-x11-0 \
        libgl1 \
        libglib2.0-0 \
        tesseract-ocr \
        libtesseract-dev \
        libomp-dev
    apt-get clean
    rm -rf /var/lib/apt/lists/*
fi

echo "Starting application..."
exec python -m ai_actuarial web --host 0.0.0.0 --port 5000
