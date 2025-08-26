FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim
#FROM python:3.12-alpine as build

#RUN apk add build-base libpq libpq-dev

COPY ./src/pyproject.toml /code/pyproject.toml

WORKDIR /code/app

RUN uv sync

ENV PATH="/code/.venv/bin:$PATH"

#FROM python:3.12-alpine as final

# copy files
#COPY ./src /code/app/

