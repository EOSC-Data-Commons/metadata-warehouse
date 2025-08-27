FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

COPY ./pyproject.toml /code/pyproject.toml

WORKDIR /code/app

ENV UV_LINK_MODE=copy

RUN uv sync --no-dev

ENV PATH="/code/.venv/bin:$PATH"




