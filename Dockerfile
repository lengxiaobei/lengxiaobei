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
ENV LX_WEB_HOST=0.0.0.0
ENV LX_WEB_PORT=8088

# Expose the Web API port
EXPOSE 8088

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD python -c "import os, urllib.request; urllib.request.urlopen('http://127.0.0.1:%s/api/status' % os.environ.get('LX_WEB_PORT', '8088'))" || exit 1

# Default command: run the Blueprint-based Web app
CMD ["python", "-m", "lx_web.app"]
