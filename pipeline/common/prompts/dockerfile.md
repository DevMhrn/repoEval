---
name: dockerfile
purpose: standard python dockerfile with pinned deps and test tooling
inputs: [base]
outputs: dockerfile_contents
---
FROM {base}
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends \
    git curl ca-certificates && rm -rf /var/lib/apt/lists/*
COPY requirements.lock /tmp/requirements.lock
RUN pip install --no-cache-dir -r /tmp/requirements.lock
RUN pip install --no-cache-dir pytest pytest-cov pytest-json-report
COPY . /app
ENV PYTHONPATH=/app/src:/app
RUN touch /tmp/.container_built
