FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/src

WORKDIR /app

COPY src /app/src

WORKDIR /workspace

ENTRYPOINT ["python", "-m", "hotspot_signal.cli"]
