FROM docker.io/library/python@sha256:1e1f6334529d1fb26a2ef619d7cffb30a7c7d7cc1cc7338ebee283a58d1aeaca

WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 LANGSMITH_TRACING=false
COPY projects/p09_docker_agent/requirements-linux.txt /tmp/requirements.txt
RUN pip install --no-cache-dir --only-binary=:all: --require-hashes -r /tmp/requirements.txt
COPY portfolio_core /app/portfolio_core
COPY projects/__init__.py /app/projects/__init__.py
COPY projects/p05_self_healing_pipeline /app/projects/p05_self_healing_pipeline
COPY projects/p09_docker_agent/__init__.py projects/p09_docker_agent/healthcheck.py projects/p09_docker_agent/transport.py /app/projects/p09_docker_agent/
RUN mkdir -p /app/.runtime/pipeline \
    && touch /app/.runtime/pipeline/.volume-version \
    && chown -R 10001:10001 /app/.runtime

USER 10001:10001
CMD ["python", "-m", "uvicorn", "projects.p05_self_healing_pipeline.app:app", "--uds", "/tmp/clearflow.sock", "--no-proxy-headers"]
