FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

COPY ./pyproject.toml ./uv.lock /code/

WORKDIR /code/src

ENV UV_LINK_MODE=copy
RUN uv sync --no-dev
ENV PATH="/code/.venv/bin:$PATH"
