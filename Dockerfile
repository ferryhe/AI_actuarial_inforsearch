FROM python:3.11-slim

ARG BUILD_GIT_SHA=unknown
ARG BUILD_RELEASE_ID=unknown
ARG BUILD_GIT_DIRTY=unknown
ARG BUILD_UTC=unknown
ARG BUILD_SOURCE_URL=https://github.com/ferryhe/AI_actuarial_inforsearch

LABEL org.opencontainers.image.revision="${BUILD_GIT_SHA}" \
      org.opencontainers.image.created="${BUILD_UTC}" \
      org.opencontainers.image.source="${BUILD_SOURCE_URL}" \
      com.aiinforsearch.git-dirty="${BUILD_GIT_DIRTY}"

LABEL com.aiinforsearch.release-id="${BUILD_RELEASE_ID}"
ENV BUILD_RELEASE_ID=${BUILD_RELEASE_ID} BUILD_GIT_SHA=${BUILD_GIT_SHA} BUILD_UTC=${BUILD_UTC}

WORKDIR /app
ENV TIKTOKEN_CACHE_DIR=/app/.tiktoken-cache

# Install system dependencies for PDF conversion and OpenDataLoader.
RUN apt-get update && apt-get install -y \
    # Basic utilities
    curl \
    # OpenDataLoader requires Java 11+ on PATH
    default-jre-headless \
    # For docling PDF conversion (X11 libraries)
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
    # For CPU document processing libraries
    libomp-dev \
    libsm6 \
    # Clean up
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .
# Keep the hermetic image acceptance probe available even when future build
# context rules narrow the application copy.
COPY ./tests /app/tests

# Make entrypoint executable
RUN chmod +x docker-entrypoint.sh

# Keep tokenizer cache writable for current and older tiktoken releases.
RUN mkdir -p /app/.tiktoken-cache && chmod 777 /app/.tiktoken-cache && chown -R root:root /app/.tiktoken-cache

# Create data directory
RUN mkdir -p /app/data

# Verify all supported built-in tokenizers resolve without network access.
RUN python -c "import tiktoken, os; os.environ['TIKTOKEN_CACHE_DIR']='/app/.tiktoken-cache'; [tiktoken.get_encoding(n) for n in ('cl100k_base','p50k_base','p50k_edit','o200k_base','o200k_harmony','gpt2','r50k_base')]; [tiktoken.encoding_for_model(m) for m in ('gpt-4','gpt-4o','gpt-4.1','gpt-5','o1','o3','o4-mini','text-embedding-3-large','text-embedding-3-small','text-embedding-ada-002')]; print('tiktoken warm', tiktoken.__version__)"

# Expose port
EXPOSE 5000

# Use entrypoint script
ENTRYPOINT ["./docker-entrypoint.sh"]
