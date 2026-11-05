# GenAI Portfolio Sprint

Ten runnable portfolio applications, built incrementally on **D:** from **5–18 November 2026 (Asia/Kolkata)**.

Current state: **1/10 new MVPs implemented and live-verified** (Local AI); Agent Eval Lab is completed existing work. The other nine apps remain scheduled work. A local Git repository is used for checkpoints; no GitHub remote or push has been created.

Source: [Aman Kharwal's project list](https://amanxai.com/2026/07/31/10-end-to-end-genai-portfolio-projects/).

**Existing work:** [Agent Eval Lab](https://github.com/Anilrao96/agent-eval-lab) is already completed at `D:\agent-eval-lab`. Reuse its evaluation contracts and reporting rather than rebuilding an evaluation framework. Its checkout remains independent and untouched. Evaluation infrastructure does not by itself implement an MCP multi-agent application.

## Start the first application

```powershell
cd D:\genai-portfolio
.\scripts\Setup.ps1
.\scripts\Start-Ollama.ps1
# In another terminal; model files are saved on D:
$env:OLLAMA_HOST = '127.0.0.1:11435'
ollama pull qwen2.5:1.5b
.\scripts\Start-LocalAI.ps1
```

Open <http://127.0.0.1:8104>. Ollama uses a dedicated port and `D:\genai-portfolio\.models`; no system-wide Ollama settings are changed. The default model is a small starting point, not a claim of frontier quality. Other installed models can be selected in the app.

CPU is the verified default on this machine because automatic CUDA inference timed out. The existing GTX 1650 was detected; its presence is not a successful GPU benchmark.

```powershell
.\scripts\Test.ps1
```

For the browser check, with both services running: `npm ci --cache .cache/npm`, then `npm run test:ui`. This uses an existing Edge installation and a separate profile under `.runtime`; it does not use your normal browser profile. The arithmetic probe is a smoke test, not a model-quality evaluation.

Read [ROADMAP.md](ROADMAP.md) for the fourteen-day sequence and acceptance criteria; [PROGRESS.md](PROGRESS.md) and [progress.json](progress.json) record resumable state. Project numbers follow the article; implementation order follows dependencies.

## Working agreement

- Build useful, tested MVPs with an explicit scope and honest limitations. Two weeks is a target conditioned on available computer time, dependencies and credentials.
- Keep source, environments, downloads, datasets and generated artifacts inside this folder on D:.
- Default to local inference and fictional datasets. Paid API calls require a configured provider and an agreed budget. Never store credentials in Git.
- Keep offline fixtures clearly distinct from live inference. A stub is not a completed AI integration.
- Each app needs a reproducible start command, example workflow, architecture notes, focused tests, and evidence of what actually ran.
- Work resumes hourly through 18 November when the computer and desktop app are available. This is scheduled work, not a persistent startup service; unavailable time reduces the build window.
- Keep all work local unless the user later requests GitHub publishing or hosting.

## Layout

```text
portfolio_core/       Shared model transport
projects/             Ten independently described applications
tests/                Focused offline contract and API tests
scripts/              Windows setup, launch and verification
docs/                 Architecture and sprint evidence
.models/              Local model weights (ignored)
.venv/, .cache/        Project environment and dependency cache (ignored)
```
