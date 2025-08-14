FROM python:3.12-alpine
#FROM python:3.12-alpine as build

#RUN apk add build-base libpq libpq-dev

COPY ./src/requirements.txt /code/requirements.txt

RUN pip install --upgrade pip \
  && pip install -r /code/requirements.txt

#FROM python:3.12-alpine as final

WORKDIR /code/app

# copy files
COPY ./src/transform /code/app/
COPY ./src/tasks /code/app

