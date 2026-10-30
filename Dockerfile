FROM python:3.12-slim-bookworm

WORKDIR /app

COPY requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY huashi ./huashi
# Startup copy2 preserves asset modes; keep the 32 existing v6 icons at NAS baseline.
COPY --chmod=0770 huashi/assets/icon_library/*-v6.png ./huashi/assets/icon_library/
COPY web ./web
COPY .env.example ./.env.example

ENV HUASHI_HOST=0.0.0.0
ENV HUASHI_PORT=8787
ENV HUASHI_DATA_DIR=data

EXPOSE 8787

CMD ["python", "-m", "huashi.server", "--host", "0.0.0.0", "--port", "8787", "--data", "data"]
