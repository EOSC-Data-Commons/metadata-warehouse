FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

WORKDIR /app

COPY pyproject.toml uv.lock* ./
RUN uv sync --no-dev

RUN apt-get update && \
    apt-get install -y docker.io docker-compose

ENV PATH="/app/.venv/bin:$PATH"

COPY config config
COPY scheduler scheduler

CMD ["python", "-m", "scheduler.run"]
