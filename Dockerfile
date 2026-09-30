# Multi-stage Dockerfile for InterconnectAI
# Targets: base, backend (FastAPI), frontend (Streamlit), evals (DeepEval benchmarks)

# ---------------------------------------------------------------------------
# Base Layer
# ---------------------------------------------------------------------------
FROM python:3.12-slim AS base

WORKDIR /app

# Install system utilities for healthchecks and builds
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DEEPEVAL_TELEMETRY_OPT_OUT=YES \
    PYTHONPATH=/app

# Leverage Docker cache by copying dependency files first
COPY pyproject.toml requirements.txt requirements-dev.txt /app/
RUN pip install --no-cache-dir -r requirements.txt

# Copy source repository
COPY . /app/
RUN pip install --no-cache-dir -e .

# ---------------------------------------------------------------------------
# Backend Target: FastAPI Async Runner Service
# ---------------------------------------------------------------------------
FROM base AS backend

EXPOSE 8000

HEALTHCHECK --interval=10s --timeout=5s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]

# ---------------------------------------------------------------------------
# Frontend Target: Streamlit Review Console
# ---------------------------------------------------------------------------
FROM base AS frontend

EXPOSE 8501

HEALTHCHECK --interval=10s --timeout=5s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8501/_stcore/health || exit 1

CMD ["streamlit", "run", "frontend/app.py", "--server.port", "8501", "--server.address", "0.0.0.0", "--server.headless", "true"]

# ---------------------------------------------------------------------------
# Evals Target: DeepEval Benchmarks & CI Gate
# ---------------------------------------------------------------------------
FROM base AS evals

RUN pip install --no-cache-dir -r requirements-dev.txt

CMD ["python", "-m", "evals.run_benchmarks", "--threshold", "0.90"]
