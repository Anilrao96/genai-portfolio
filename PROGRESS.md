# Sprint progress

Last updated: 5 November 2026, Asia/Kolkata.

## Existing completed work

- **Agent Eval Lab** — `D:\agent-eval-lab`, `https://github.com/Anilrao96/agent-eval-lab`. User confirmed it is already done. README and clean Git working tree inspected; includes an evaluation runner, dataset contracts, tool traces, reports, offline cases and a live HTTP model adapter. Existing test suite was not rerun. Reuse for evaluation integration and do not rebuild it.

## Current milestone

**Day 1 completed as an MVP:** foundation and project 04, Local AI. Real browser → FastAPI → Ollama → browser inference verified with `qwen2.5:1.5b` in CPU mode. All **27 offline tests passed**. Headless Edge checked a live response, desktop/mobile layouts, no horizontal mobile overflow, no JavaScript errors and clearing a conversation.

Evidence: `docs/local-ai-live.json`, `docs/local-ai-cpu-probe.json`, `docs/local-ai-browser.json`, desktop/mobile PNGs and the session log. Initial GPU inference timed out; that failure is retained in `docs/local-ai-initial-timeout.json`. CPU is the verified default. This is a scoped local MVP; streaming and cancellation are documented follow-ups.

**Git:** local repository initialized on `main`; no remote is configured and nothing has been pushed to GitHub. GitHub delivery has not been authorized in this sprint.

**Schedule:** active hourly continuation in this chat, automation ID `build-genai-portfolio-over-two-weeks`, ending before 19 November 00:00 Asia/Kolkata. Local files require the computer and desktop app to be running.

## Next actions

1. Start project 07: natural language → read-only SQLite SQL → bounded results → explanation.
2. Read current primary documentation before choosing the LangChain integration; retain database-level read-only enforcement independently of prompt behavior.
3. Add a fictional sample database and cases for correct answers, ambiguous questions, attempted writes, expensive queries and invalid generated SQL.
4. Reuse the shared local model transport and later connect evaluation cases to the existing Agent Eval Lab. Do not rebuild its evaluator.

## Known dependencies

- Working Python 3.13 exists under the existing uv installation; the Python 3.10 launcher registration is stale.
- 24 GB system RAM; Intel i5-9300H; about 688 GB available on D:. GPU not established.
- NVIDIA GTX 1650 with 4 GB VRAM detected by Ollama; automatic GPU inference hit the 120-second read timeout. CPU inference works.
- The dedicated portfolio Ollama at `127.0.0.1:11435` has `qwen2.5:1.5b` (about 986 MB) under `.models` on D:. The existing default instance remains independent.
- Docker not found in PATH. Gemini key/budget not configured by this task.
- The normal filesystem sandbox restricts local sockets and uv executable creation; verified commands may need narrowly scoped approval review.
