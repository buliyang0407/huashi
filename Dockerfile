FROM docker.m.daocloud.io/library/python:3.12-slim-bookworm

WORKDIR /app

COPY huashi ./huashi
COPY web ./web
COPY .env.example ./.env.example

ENV HUASHI_HOST=0.0.0.0
ENV HUASHI_PORT=8787
ENV HUASHI_DATA_DIR=data

EXPOSE 8787

CMD ["python", "-m", "huashi.server", "--host", "0.0.0.0", "--port", "8787", "--data", "data"]
