# syntax=docker/dockerfile:1

# --- build stage ---------------------------------------------------------------
FROM python:3.13-slim AS builder

COPY --from=ghcr.io/astral-sh/uv:0.11.26 /uv /usr/local/bin/uv

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never

WORKDIR /app

# Install dependencies first for layer caching (re-runs only when deps change).
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

# Add the app and finish the install.
COPY . .
RUN uv sync --frozen --no-dev

# --- runtime stage -------------------------------------------------------------
FROM python:3.13-slim AS runtime

RUN useradd --create-home --uid 1000 app
WORKDIR /app
COPY --from=builder --chown=app:app /app /app

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1
USER app

# One-shot auditor: runs once against the PR context in the environment, then exits.
CMD ["python", "app.py"]
