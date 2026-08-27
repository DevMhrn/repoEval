FROM python:3.11-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends git curl ca-certificates && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir pytest pytest-cov pytest-json-report
COPY . /app
ENV PYTHONPATH=/app/src:/app
RUN touch /tmp/.container_built
