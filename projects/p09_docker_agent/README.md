# 09 Clearflow Docker Agent

Run the [Clearflow pipeline](../p05_self_healing_pipeline/README.md) as a Docker Compose service. The FastAPI app serves the browser UI, validates fictional order CSVs, asks local Qwen3 for a bounded repair plan when the schema drifts, and commits accepted snapshots to a named SQLite audit volume.

## Start on Windows

This path uses the portfolio's owned native WSL 3.0.3 container session and D-backed virtual disk. It needs the native WSL Containers CLI, the repository's Python environment, and the portfolio Ollama server with `qwen3:4b` installed. Run `scripts/Setup.ps1` for a fresh checkout. Start Ollama in a separate terminal with `scripts/Start-Ollama.ps1` and pull the model into that instance if needed.

```powershell
cd D:\genai-portfolio
.\scripts\Start-DockerAgent.ps1
```

Open <http://127.0.0.1:8109>. Select **01 Clean** and ingest it, then select **02 Format drift**, choose **Month / day / year** and ingest again. The batch should show a six-field extraction plan and two valid repaired rows. The snapshot should contain four orders, eight units and $2,524.85. The exact totals assume an empty audit volume.

Stop the Windows relay with Ctrl+C. Run `scripts/Start-DockerAgent.ps1 -Stop` to remove the Compose container and keep the audit volume. Starting again reconnects to that volume. The underlying WSL session is shared with the other portfolio container projects.

## Runtime and configuration

```text
Edge -> Windows loopback relay -> fixed Docker exec -> Unix socket -> FastAPI
                                                                      |-> Ollama on Windows loopback
                                                                      `-> named audit volume (SQLite)
```

The launcher verifies the owned WSL session and installs the pinned, checksum-verified Compose plugin in its private CLI directory if needed. It stages 22 allowlisted files, builds the hash-labeled image with `wslc build`, then runs `docker compose up --no-build --wait`. Compose 5.6.0 requires Buildx 0.17 or later for `compose build`. The native WSL builder works with the installed engine. The base image uses a manifest digest and Linux wheels use exact versions and hashes. The first build needs access to Docker Hub and PyPI.

The app runs as UID/GID 10001 with a read-only root filesystem, dropped capabilities, a 384 MB memory limit, 0.75 CPU quota and a 64 PID limit. The WSL kernel reports that swap limits are unavailable. The only persistent mount is the named `audit` volume at `/app/.runtime`, backed by the D: virtual disk. The health command checks the `orders-v1` HTTP contract, reads the SQLite snapshot pointer via `mode=ro` and verifies the configured model is present. Use `-Port`, `-OllamaPort` and `-Model` to set the Windows loopback ports and model. [Compose configuration and local defaults](compose.yaml).

The trusted app uses guest host networking to reach Ollama. The first TCP readiness check failed because the container's connection to its own guest loopback listener was refused. Uvicorn now serves HTTP through a Unix socket in its private `/tmp`, with no published Docker ports. The Windows loopback relay accepts only Clearflow routes, then uses one fixed Docker exec command per request to reach that socket. The web app receives no Docker socket mount, and setup adds no system network rules.

The verified path uses a local model and needs no credentials. The build receives allowlisted source and fictional sample CSVs. Keep local credentials and private feeds outside the build inputs and Git. `compose down` preserves the volume. Use a separate QA project to test from an empty audit database.

## Verification

```powershell
.\scripts\Test.ps1
. .\scripts\Use-Environment.ps1
uv run --frozen python scripts/probe-docker-agent.py
```

The offline suite uses fixture relay responses and a real temporary SQLite database. The live probe needs Node, the repository's Playwright dependency and Edge. It creates a fresh Compose project, sends real model-backed ingestion requests through a temporary Windows loopback relay, and removes the test container when finished. It leaves the D-backed test volume for audit.

Docker Engine 25.0.3 and Compose 5.6.0 reached healthy state in 5.73 seconds from an empty volume and 5.75 seconds after container recreation. A missing model produced readiness exit 1. One CPU Qwen3 call repaired two rows in 94.04 seconds over HTTP. A duplicate request made zero model calls. Snapshot and original batch matched after recreation. Edge loaded the recreated service and opened the persisted repair trace. [Live run evidence](../../docs/docker-agent-live.json) · [Edge screenshot](../../docs/docker-agent-desktop.png).
