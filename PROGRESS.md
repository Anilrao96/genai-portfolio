# Sprint progress

Last updated: 6 November 2026, Asia/Kolkata.

## Existing completed work

- **Agent Eval Lab** — `D:\agent-eval-lab`, `https://github.com/Anilrao96/agent-eval-lab`. User confirmed it is already done. README and clean Git working tree inspected; includes an evaluation runner, dataset contracts, tool traces, reports, offline cases and a live HTTP model adapter. Existing test suite was not rerun. Reuse for evaluation integration and do not rebuild it.

## Current milestone

**Day 1 completed as an MVP:** foundation and project 04, Local AI. Real browser → FastAPI → Ollama → browser inference verified with `qwen2.5:1.5b` in CPU mode. All **27 offline tests passed**. Headless Edge checked a live response, desktop/mobile layouts, no horizontal mobile overflow, no JavaScript errors and clearing a conversation.

Evidence: `docs/local-ai-live.json`, `docs/local-ai-cpu-probe.json`, `docs/local-ai-browser.json`, desktop/mobile PNGs and the session log. Initial GPU inference timed out; that failure is retained in `docs/local-ai-initial-timeout.json`. CPU is the verified default. This is a scoped local MVP; streaming and cancellation are documented follow-ups.

**Day 2 completed as an MVP:** project 07, Retail Lens SQL Assistant. Real LangChain → Qwen3 4B CPU → read-only SQLite → result summary works. The full portfolio suite passes **77 tests**, including **50 SQL tests**. Six authored API scenarios passed (four actual model workflows, two finite scope-policy cases), four direct forbidden-query probes were refused, and the sample database fingerprint stayed unchanged. Desktop/mobile browser checks and six recorded-outcome contracts through the existing Agent Eval Lab passed. The replay makes no fresh model calls and does not establish summary faithfulness or broad model quality.

Evidence: `docs/sql-assistant-live.json`, `docs/sql-assistant-browser.json`, desktop/mobile screenshots and `docs/sql-assistant-eval/`. The smaller model's failed join, unsupported-profit answer and currency conversion are preserved in the initial/unit failure captures. Qwen3's observed CPU HTTP requests took about 120 seconds cold and 25–32 seconds warm; the separate UI request took about 48 seconds. SQL is a fictional SQLite MVP; PostgreSQL remains an upgrade path.

**Git:** published to `https://github.com/Anilrao96/genai-portfolio`, branch `main`. Local AI and the roadmap were remotely verified at `6dded5a2a939f122f3beb99b516e3b72cf57466d`. SQL implementation, documentation and evidence were committed, pushed and remotely verified at `9fd2c94fde9d3b15efdbd39a817fcae035281bb7`. This delivery record is committed and pushed separately. Reuse this one repository for all ten applications and shared code.

**Schedule:** active hourly continuation in this chat, automation ID `build-genai-portfolio-over-two-weeks`, ending before 19 November 00:00 Asia/Kolkata. Local files require the computer and desktop app to be running.

## Next actions

1. Start project 03: ingest fictional documents, persist a local index, retrieve source IDs and generate cited answers.
2. Add bounded retrieval grading/query rewrite and abstention on insufficient evidence; test grounding and failure paths.
3. Keep using the existing Agent Eval Lab contracts and reporting; do not rebuild or modify that repository.

## Known dependencies

- Working Python 3.13 exists under the existing uv installation; the Python 3.10 launcher registration is stale.
- 24 GB system RAM; Intel i5-9300H; about 688 GB available on D: at initial inspection.
- NVIDIA GTX 1650 with 4 GB VRAM detected by Ollama; automatic GPU inference hit the 120-second read timeout. CPU inference works.
- The dedicated portfolio Ollama at `127.0.0.1:11435` has `qwen2.5:1.5b` (about 986 MB) and `qwen3:4b` (about 2.5 GB) under `.models` on D:. The existing default instance remains independent. Local AI Studio keeps its verified smaller model as the default when present.
- Docker not found in PATH. Gemini key/budget not configured by this task.
- The normal filesystem sandbox restricts local sockets and uv executable creation; verified commands may need narrowly scoped approval review.
