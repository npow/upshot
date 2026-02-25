FROM python:3.12-slim

RUN apt-get update && apt-get install -y git ca-certificates && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY . /app
RUN pip install --no-cache-dir -e ".[dev]"

ENTRYPOINT ["/bin/bash", "/app/scripts/run_daily.sh"]
