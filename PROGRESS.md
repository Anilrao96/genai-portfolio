# Sprint progress

Last updated: 6 November 2026, Asia/Kolkata.

## Existing completed work

- **Agent Eval Lab** — `D:\agent-eval-lab`, `https://github.com/Anilrao96/agent-eval-lab`. User confirmed it is already done. README and clean Git working tree inspected; includes an evaluation runner, dataset contracts, tool traces, reports, offline cases and a live HTTP model adapter. Existing test suite was not rerun. Reuse for evaluation integration and do not rebuild it.

## Current milestone

**Day 1 completed as an MVP:** foundation and project 04, Local AI. Real browser → FastAPI → Ollama → browser inference verified with `qwen2.5:1.5b` in CPU mode. All **27 offline tests passed**. Headless Edge checked a live response, desktop/mobile layouts, no horizontal mobile overflow, no JavaScript errors and clearing a conversation.

Evidence: `docs/local-ai-live.json`, `docs/local-ai-cpu-probe.json`, `docs/local-ai-browser.json`, desktop/mobile PNGs and the session log. Initial GPU inference timed out; that failure is retained in `docs/local-ai-initial-timeout.json`. CPU is the verified default. This is a scoped local MVP; streaming and cancellation are documented follow-ups.

**Day 2 completed as an MVP:** project 07, Retail Lens SQL Assistant. Real LangChain → Qwen3 4B CPU → read-only SQLite → result summary works. The full portfolio suite passes **77 tests**, including **50 SQL tests**. Six authored API scenarios passed (four actual model workflows, two finite scope-policy cases), four direct forbidden-query probes were refused, and the sample database fingerprint stayed unchanged. Desktop/mobile browser checks and six recorded-outcome contracts through the existing Agent Eval Lab passed. The replay makes no fresh model calls and does not establish summary faithfulness or broad model quality.

Evidence: `docs/sql-assistant-live.json`, `docs/sql-assistant-browser.json`, desktop/mobile screenshots and `docs/sql-assistant-eval/`. The smaller model's failed join, unsupported-profit answer and currency conversion are preserved in the initial/unit failure captures. Qwen3's observed CPU HTTP requests took about 120 seconds cold and 25–32 seconds warm; the separate UI request took about 48 seconds. SQL is a fictional SQLite MVP; PostgreSQL remains an upgrade path.

**Project 03 completed as an MVP:** Reference Desk Agentic RAG. Real Nomic embeddings and SQLite FTS/vector persistence feed LangChain grading, one bounded rewritten search and source-checked Qwen3 answers. All **five live cases passed**, including actual search recovery and abstention; the nine-source/nine-chunk 768-dimensional QA index persisted across processes/restarts. The portfolio suite passes **113 tests** (36 RAG). Desktop/mobile browser checks and **5/5 recorded-outcome contracts** through the existing Agent Eval Lab passed. A numeric/time mismatch uses a verified source quotation instead of the model's faulty paraphrase.

Evidence: `docs/rag-live.json`, `docs/rag-persistence.json`, `docs/rag-browser.json`, desktop/mobile screenshots and `docs/rag-eval/`. Initial grading/ID failures and a manually noticed time-format error are preserved separately. Final CPU HTTP examples took approximately 19–42 seconds; the UI request took about 20 seconds. Source/quote/literal checks do not prove semantic entailment; the library is bounded and does not resolve conflicting source versions.

**Git:** published to `https://github.com/Anilrao96/genai-portfolio`, branch `main`. Local AI and SQL delivery are verified; the last metadata head before this session was `5177218481af489ff98cbc0c427d72e1bf96b2fb`. RAG implementation, documentation and evidence are complete and ready for the authorized commit/push. RAG delivery verification is pending. Reuse this one repository for all ten applications and shared code.

**Schedule:** active hourly continuation in this chat, automation ID `build-genai-portfolio-over-two-weeks`, ending before 19 November 00:00 Asia/Kolkata. Local files require the computer and desktop app to be running.

## Next actions

1. Finish and remotely verify the RAG GitHub delivery before reporting it pushed.
2. Start project 01: an actual MCP client/server, specialized research/analysis/review roles and structured shared state.
3. Bound orchestration/tool calls and record actual protocol/tool traces, including a failure case. Keep using the existing Agent Eval Lab rather than rebuilding its evaluator.

## Known dependencies

- Working Python 3.13 exists under the existing uv installation; the Python 3.10 launcher registration is stale.
- 24 GB system RAM; Intel i5-9300H; about 688 GB available on D: at initial inspection.
- NVIDIA GTX 1650 with 4 GB VRAM detected by Ollama; automatic GPU inference hit the 120-second read timeout. CPU inference works.
- The dedicated portfolio Ollama at `127.0.0.1:11435` has `qwen2.5:1.5b` (about 986 MB), `qwen3:4b` (about 2.5 GB) and `nomic-embed-text:v1.5` (about 274 MB) under `.models` on D:. The existing default instance remains independent. Chat choices exclude embedding-only models; Local AI Studio retains its verified smaller default.
- Docker not found in PATH. Gemini key/budget not configured by this task.
- The normal filesystem sandbox restricts local sockets and uv executable creation; verified commands may need narrowly scoped approval review.
