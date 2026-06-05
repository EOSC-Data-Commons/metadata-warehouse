FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

COPY ./pyproject.toml ./uv.lock /code/

WORKDIR /code
ENV UV_LINK_MODE=copy
RUN uv sync --frozen --no-dev

COPY ./src /code/src
COPY ./config /code/config

WORKDIR /code/src
ENV PATH="/code/.venv/bin:$PATH"
