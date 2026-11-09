FROM docker.io/library/node:22-alpine AS frontend
WORKDIR /opt/tool
COPY package.json package-lock.json ./
RUN npm ci --ignore-scripts --no-audit --no-fund

FROM docker.io/library/python@sha256:1e1f6334529d1fb26a2ef619d7cffb30a7c7d7cc1cc7338ebee283a58d1aeaca
COPY requirements.txt /opt/builder/requirements.txt
RUN pip install --no-cache-dir --only-binary=:all: -r /opt/builder/requirements.txt
COPY --from=frontend /opt/tool/node_modules /opt/tool/node_modules
COPY runner.py entry.jsx /opt/builder/
RUN mkdir /workspace && chown 65534:65534 /workspace
ENV PYTHONDONTWRITEBYTECODE=1 NODE_PATH=/opt/tool/node_modules GOMAXPROCS=2
WORKDIR /workspace
USER 65534:65534
ENTRYPOINT ["python", "-I", "-B", "/opt/builder/runner.py"]
