FROM mcr.microsoft.com/playwright/python:v1.40.0-jammy

ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1

# Install Tesseract OCR and language packs
RUN apt-get update && apt-get install -y \
    tesseract-ocr \
    tesseract-ocr-kor \
    tesseract-ocr-eng \
    libgl1-mesa-glx \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy dependency mappings
COPY requirements.txt .

# Install Python packages
RUN pip install --no-cache-dir -r requirements.txt

# Install Playwright Chromium binaries
RUN playwright install chromium

# Copy application payload
COPY . .

# Initialize FastMCP Server
CMD ["python", "main.py"]
