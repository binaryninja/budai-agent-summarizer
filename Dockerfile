# Agent Summarizer Dockerfile
FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    git \
    && rm -rf /var/lib/apt/lists/*

# Install uv for fast dependency installation
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Copy requirements
COPY requirements.txt /app/
RUN uv pip install --system -r requirements.txt

# Copy shared libraries
COPY shared/ /app/shared/
COPY installer/ /app/installer/

# Copy service code
COPY service/ /app/service/

# Set Python path
ENV PYTHONPATH=/app

# Expose port
EXPOSE 8002

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8002/health')"

# Run the service
CMD ["python", "service/service.py"]

