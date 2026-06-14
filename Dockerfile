FROM python:3.12-slim-bookworm

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md ./
COPY config ./config
COPY src ./src

RUN pip install --no-cache-dir -e .

EXPOSE 8080

CMD ["agentctl", "webhook", "serve", "--host", "0.0.0.0", "--port", "8080"]
