FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    ffmpeg \
    libmagic1 \
    curl \
    build-essential \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create upload directory and other necessary directories
RUN mkdir -p uploads && chmod 777 uploads && \
    mkdir -p input && chmod 777 input && \
    mkdir -p output && chmod 777 output

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV PIP_NO_CACHE_DIR=1
ENV PIP_DISABLE_PIP_VERSION_CHECK=1

# Make the start script executable
RUN chmod +x /app/start.sh

# Expose port
EXPOSE 8000

# Make our run script executable
RUN chmod +x /app/run_app.py

# Make sure .env file is loaded
RUN echo "Checking for .env file" && \
    if [ -f /app/.env ]; then echo "Found .env file"; else echo "No .env file found"; fi

# Use our custom wrapper script that shows the correct external port
CMD ["python", "/app/run_app.py"]