# BotForge API — multi-stage build using uv
FROM ghcr.io/astral-sh/uv:python3.11-bookworm-slim AS base

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

# Install dependencies first (cached layer) using the lockfile.
COPY pyproject.toml uv.lock* ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-install-project --no-dev || uv sync --no-install-project --no-dev

# Copy source and install the project itself.
COPY . .
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --no-dev || true

# Run as a non-root user.
RUN useradd -m -u 10001 appuser && chown -R appuser:appuser /app
USER appuser

ENV PATH="/app/.venv/bin:$PATH"

EXPOSE 8000

# Migrations run via the compose entrypoint before uvicorn (see docker-compose.yml).
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
