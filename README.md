# GenAI Portfolio Sprint

Ten runnable portfolio applications, built incrementally on **D:** from **5–18 November 2026 (Asia/Kolkata)**.

Current state: **6/10 new MVPs implemented and live-verified** (MCP Agents, Agentic RAG, Local AI, Self-Healing Pipeline, Code Assistant and SQL Assistant); Agent Eval Lab is completed existing work. The other four apps remain scheduled work. GitHub destination: [Anilrao96/genai-portfolio](https://github.com/Anilrao96/genai-portfolio). Completed projects are committed and pushed after verification; delivery status is recorded in PROGRESS.md.

Source: [Aman Kharwal's project list](https://amanxai.com/2026/07/31/10-end-to-end-genai-portfolio-projects/).

**Existing work:** [Agent Eval Lab](https://github.com/Anilrao96/agent-eval-lab) is already completed at `D:\agent-eval-lab`. Reuse its evaluation contracts and reporting rather than rebuilding an evaluation framework. Its checkout remains independent and untouched. Evaluation infrastructure does not by itself implement an MCP multi-agent application.

## Implemented applications

| Project | What works | Start command |
| --- | --- | --- |
| [01 Support Council MCP Agents](projects/p01_mcp_agents/README.md) | Three specialized local-model roles, actual scoped MCP discovery/tools/resources, checked pricing, versioned handoffs and traces | `scripts/Start-McpAgents.ps1` → port 8101 |
| [03 Reference Desk Agentic RAG](projects/p03_agentic_rag/README.md) | Persistent local vectors/full-text search, evidence grading, one recovery search, checked source passages and abstention | `scripts/Start-Rag.ps1` → port 8103 |
| [04 Local AI Studio](projects/p04_local_ai/README.md) | Local chat, model selection, bounded requests and measured responses | `scripts/Start-LocalAI.ps1` → port 8104 |
| [05 Clearflow Self-Healing Pipeline](projects/p05_self_healing_pipeline/README.md) | Model-proposed finite repairs, exact validation, atomic snapshots, quarantine/replay and reversible rollback | `scripts/Start-Pipeline.ps1` → port 8105 |
| [06 Repair Bench Code Assistant](projects/p06_code_assistant/README.md) | Real LangGraph generation/repair, inspected native WSL containers, hard resource limits, actual test feedback and saved attempts | `scripts/Start-CodeAssistant.ps1` → port 8106; run its setup first |
| [07 Retail Lens SQL Assistant](projects/p07_sql_assistant/README.md) | LangChain SQL planning, database-enforced read-only queries, visible results and summaries | `scripts/Start-SqlAssistant.ps1` → port 8107 |

The portfolio regression suite has **195 passing offline tests**. SQL verification covers model workflows and refused database operations; RAG covers citations, abstention and search recovery. MCP verifies actual role-scoped protocol calls and checked selections; numeric model notes use labeled tool fallbacks. Pipeline verification covers real model repair, saved-extractor reuse, whole-batch quarantine, corrected-source replay and snapshot rollback. Code Assistant also passed nine actual container isolation controls and real model generation/repair through API and browser. Captured-outcome checks reuse the existing Agent Eval Lab. These authored checks are smoke evidence, not a broad model benchmark.

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
- Push completed, verified projects to the portfolio GitHub repository. Keep runtime services local; hosting has not been requested.

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
