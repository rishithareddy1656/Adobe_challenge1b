# Dockerfile
# Use a slim Python image to keep the size down for the 1GB constraint
# Ensure it's compatible with AMD64 (linux/amd64)
FROM python:3.9-slim-buster AS builder

# Set the working directory in the container
WORKDIR /app

# Install system dependencies required by PyMuPDF (fitz)
# Run update and install in a single layer to minimize image size
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        libjpeg-dev \
        zlib1g-dev \
        libpng-dev \
        libfreetype6-dev \
        pkg-config \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements file (if you use one)
# COPY requirements.txt .
# RUN pip install --no-cache-dir -r requirements.txt

# Manually install required Python packages to ensure minimal dependencies
# PyMuPDF is 'pymupdf'
# If you add scikit-learn or NLTK, list them here.
# NLTK requires downloading data, which might need internet, so be careful.
RUN pip install --no-cache-dir pymupdf

# Copy your application code
COPY app/ ./app/

# Create input and output directories as specified in the challenge
RUN mkdir -p /app/input /app/output

# Set the entry point for your application
# This command will be executed when the Docker container starts.
# It automatically runs the 'run_solution' function in main.py.
CMD ["python", "/app/main.py"]