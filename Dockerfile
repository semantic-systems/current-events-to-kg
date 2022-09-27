# syntax=docker/dockerfile:1

FROM python:3-slim-bullseye

WORKDIR /usr/src/app

COPY requirements.txt requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY currenteventstokg/ currenteventstokg/