FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates tzdata \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY . /app/potions

CMD ["python", "-m", "potions.live.config_runner", "--config", "/config/engine.conf.json", "run-loop"]
