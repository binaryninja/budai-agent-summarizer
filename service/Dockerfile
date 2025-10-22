# Agent Summarizer Dockerfile
FROM python:3.11-slim

WORKDIR /app
RUN apt-get update && apt-get install -y git && rm -rf /var/lib/apt/lists/*
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

COPY requirements.txt /app/
RUN uv pip install --system -r requirements.txt

COPY shared/ /app/shared/
COPY installer/ /app/installer/
COPY services/agent-summarizer/ /app/services/agent-summarizer/

ENV PYTHONPATH=/app
EXPOSE 8002

HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8002/health')"

CMD ["python", "services/agent-summarizer/service.py"]

