FROM python:3.11-slim

WORKDIR /app

# Install system dependencies for PDF conversion (docling, marker) and other features
RUN apt-get update && apt-get install -y \
    # Basic utilities
    curl \
    # For docling/marker PDF conversion (X11 libraries)
    libxcb1 \
    libxcb-xinerama0 \
    libxrender1 \
    libxext6 \
    libxkbcommon0 \
    libxkbcommon-x11-0 \
    # For OpenCV (image processing)
    libgl1 \
    libglib2.0-0 \
    # For Tesseract OCR
    tesseract-ocr \
    libtesseract-dev \
    libtesseract5 \
    # For other ML libraries
    libomp-dev \
    # For easyocr
    libsm6 \
    # Clean up
    && rm -rf /var/lib/apt/lists/*

# Install docling OCR dependencies
RUN pip install --no-cache-dir \
    torch \
    torchvision \
    --index-url https://download.pytorch.org/whl/cpu

RUN pip install --no-cache-dir \
    easyocr \
    onnxruntime

# Install specific package versions for compatibility
RUN pip install --no-cache-dir mistralai==1.0.0

# Copy requirements first for better caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Make entrypoint executable
RUN chmod +x docker-entrypoint.sh

# Create data directory
RUN mkdir -p /app/data

# Expose port
EXPOSE 5000

# Use entrypoint script
ENTRYPOINT ["./docker-entrypoint.sh"]
