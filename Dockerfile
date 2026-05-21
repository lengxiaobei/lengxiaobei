# =============================================================================
# LengXiaobei Dockerfile — Production
# =============================================================================
FROM python:3.11-slim

LABEL maintainer="lengxiaobei"
LABEL description="数字生命体 - Self-evolving AI Agent"

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    curl \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy dependency files first for better caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create non-root user for security
RUN useradd -m -u 1000 appuser && chown -R appuser:appuser /app
USER appuser

# Environment defaults
ENV LENGXIAOBEI_ROOT=/app
ENV PYTHONUNBUFFERED=1
ENV LOG_LEVEL=INFO

# Expose ports
EXPOSE 8000 8080 8081 8082

# Health check (health_check.py defaults to port 8000)
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Default command: run as daemon
CMD ["python", "-m", "src.core"]
