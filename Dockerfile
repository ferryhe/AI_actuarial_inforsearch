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
    libgl1-mesa-glx \
    libglib2.0-0 \
    # For Tesseract OCR
    tesseract-ocr \
    libtesseract-dev \
    # For other ML libraries
    libomp1 \
    # Clean up
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create data directory
RUN mkdir -p /app/data

# Expose port
EXPOSE 5000

# Run the application
CMD ["python", "-m", "ai_actuarial", "web", "--host", "0.0.0.0", "--port", "5000"]
