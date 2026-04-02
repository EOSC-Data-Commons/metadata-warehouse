FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

WORKDIR /app

COPY pyproject.toml .
RUN uv sync --no-dev
ENV PATH="/app/.venv/bin:$PATH"

COPY config config
COPY scheduler scheduler
