# syntax=docker/dockerfile:1.7

# ---------------------------------------------------------------------------
# Stage 1 — builder: install uv and sync the virtualenv
# ---------------------------------------------------------------------------
FROM python:3.10-slim AS builder

# Install uv (static binary, tiny)
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /usr/local/bin/

WORKDIR /app

# Copy only dependency manifests first — this layer is cached
# unless pyproject.toml / uv.lock change
COPY pyproject.toml uv.lock ./

# Install production deps into /app/.venv, no dev extras, no editable install
ENV UV_PROJECT_ENVIRONMENT=/app/.venv \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy
RUN uv sync --frozen --no-dev --no-install-project

# ---------------------------------------------------------------------------
# Stage 2 — runtime: slim image with just the venv + source
# ---------------------------------------------------------------------------
FROM python:3.10-slim AS runtime

# Non-root user for safety
RUN useradd --create-home --shell /bin/bash appuser

WORKDIR /app

# Copy the prebuilt virtualenv from the builder
COPY --from=builder /app/.venv /app/.venv

# Copy only the source we need to run the API
COPY src/ ./src/

# Put the venv on PATH so `uvicorn` and `python` resolve to it
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    MLFLOW_TRACKING_URI=http://host.docker.internal:5000

USER appuser

EXPOSE 8000

CMD ["uvicorn", "src.food11.serve:app", "--host", "0.0.0.0", "--port", "8000"]
