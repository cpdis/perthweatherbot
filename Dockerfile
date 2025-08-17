# Use Python 3.12 slim image for smaller size
FROM python:3.12-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy source code
COPY *.py ./
COPY *.json ./
COPY *.html ./
COPY *.jpg ./
COPY *.mp3 ./

# Create necessary directories
RUN mkdir -p .cache logs

# Set environment variables
ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1

# Create non-root user for security
RUN useradd -m -u 1000 weatherbot && \
    chown -R weatherbot:weatherbot /app
USER weatherbot

# Health check
HEALTHCHECK --interval=5m --timeout=30s --start-period=30s --retries=3 \
    CMD python health.py || exit 1

# Default command
CMD ["python", "weatherbot.py"]