# Sprint progress

Last updated: 9 November 2026, Asia/Kolkata.

## Existing completed work

- **Agent Eval Lab** — `D:\agent-eval-lab`, `https://github.com/Anilrao96/agent-eval-lab`. User confirmed it is already done. README and clean Git working tree inspected; includes an evaluation runner, dataset contracts, tool traces, reports, offline cases and a live HTTP model adapter. Existing test suite was not rerun. Reuse for evaluation integration and do not rebuild it.

## Current milestone

**Day 1 completed as an MVP:** foundation and project 04, Local AI. Real browser → FastAPI → Ollama → browser inference verified with `qwen2.5:1.5b` in CPU mode. All **27 offline tests passed**. Headless Edge checked a live response, desktop/mobile layouts, no horizontal mobile overflow, no JavaScript errors and clearing a conversation.

Evidence: `docs/local-ai-live.json`, `docs/local-ai-cpu-probe.json`, `docs/local-ai-browser.json`, desktop/mobile PNGs and the session log. Initial GPU inference timed out; that failure is retained in `docs/local-ai-initial-timeout.json`. CPU is the verified default. This is a scoped local MVP; streaming and cancellation are documented follow-ups.

**Day 2 completed as an MVP:** project 07, Retail Lens SQL Assistant. Real LangChain → Qwen3 4B CPU → read-only SQLite → result summary works. The full portfolio suite passes **77 tests**, including **50 SQL tests**. Six authored API scenarios passed (four actual model workflows, two finite scope-policy cases), four direct forbidden-query probes were refused, and the sample database fingerprint stayed unchanged. Desktop/mobile browser checks and six recorded-outcome contracts through the existing Agent Eval Lab passed. The replay makes no fresh model calls and does not establish summary faithfulness or broad model quality.

Evidence: `docs/sql-assistant-live.json`, `docs/sql-assistant-browser.json`, desktop/mobile screenshots and `docs/sql-assistant-eval/`. The smaller model's failed join, unsupported-profit answer and currency conversion are preserved in the initial/unit failure captures. Qwen3's observed CPU HTTP requests took about 120 seconds cold and 25–32 seconds warm; the separate UI request took about 48 seconds. SQL is a fictional SQLite MVP; PostgreSQL remains an upgrade path.

**Project 03 completed as an MVP:** Reference Desk Agentic RAG. Real Nomic embeddings and SQLite FTS/vector persistence feed LangChain grading, one bounded rewritten search and source-checked Qwen3 answers. All **five live cases passed**, including actual search recovery and abstention; the nine-source/nine-chunk 768-dimensional QA index persisted across processes/restarts. The portfolio suite passes **113 tests** (36 RAG). Desktop/mobile browser checks and **5/5 recorded-outcome contracts** through the existing Agent Eval Lab passed. A numeric/time mismatch uses a verified source quotation instead of the model's faulty paraphrase.

Evidence: `docs/rag-live.json`, `docs/rag-persistence.json`, `docs/rag-browser.json`, desktop/mobile screenshots and `docs/rag-eval/`. Initial grading/ID failures and a manually noticed time-format error are preserved separately. Final CPU HTTP examples took approximately 19–42 seconds; the UI request took about 20 seconds. Source/quote/literal checks do not prove semantic entailment; the library is bounded and does not resolve conflicting source versions.

**Project 01 completed as an MVP:** Support Council uses three specialized LangChain/Qwen3 roles and actual MCP SDK 2.3.0 stdio clients/servers. Role-specific tools and run-scoped resources carry versioned SQLite handoffs; integer-cent pricing and the least-cost eligible selection are checked independently. The full suite passes **137 tests** (24 MCP/state/API). **2/2 live decisions**, three actual negative protocol probes, persisted state, desktop/mobile browser checks and **2/2 Agent Eval Lab replays** passed. The actual negotiated MCP protocol is `2026-07-28`.

Evidence: `docs/mcp-live.json`, `docs/mcp-browser.json`, `docs/mcp-browser-saved.json`, screenshots and `docs/mcp-eval/`. CPU API requests took about **75s / 58s**, with the separate browser decision about **69s**. All six final probe handoff notes required a labeled tool fallback because the model kept inserting numeric literals; original model outputs remain inspectable. Model plan proposals and review approval still drive the workflow and are checked. Incorrect cents/dollars prose and a refused correct no-fit analysis are preserved in failure captures. Qualitative prose is not semantically proven, and this is a fixed fictional catalog rather than general web research.

**Project 05 completed as an MVP:** Clearflow detects CSV schema/format drift, obtains a real local-model extraction plan, enforces a finite transformation language, validates every row and atomically promotes a SQLite snapshot. Invalid batches remain quarantined; corrected replay retains immutable parent/source hashes, and snapshot rollback preserves history. Validated plans are reused with their original learned-from batch ID. The full frozen suite passes **174 tests** (37 pipeline checks). **7/7 API cases**, actual browser repair, desktop/mobile checks and **3/3 existing Eval Lab replays** passed. The API checks also prove stale rollback refusal, full restoration and persistence through a separate SQLite connection.

Evidence: `docs/pipeline-live.json`, `docs/pipeline-browser.json`, screenshots and `docs/pipeline-eval/`. Actual CPU repair took about **31s**; two refused proposals for a zero quantity took about **68s** before quarantine. Cached extraction/replay made no model calls. The separate browser repair took about **37s**. This is a bounded fictional CSV/order contract with approved aliases, not arbitrary ETL or generated script execution. New aliases and missing facts require review.

**Project 06 completed as an MVP:** Repair Bench uses actual LangGraph generation/execute/repair nodes, local Qwen3 and fresh inspected native WSL OCI containers. Nine actual isolation controls passed before generated code was enabled. A failing mean function was corrected using its real `ZeroDivisionError`; word generation passed all four authored examples; a sleeping candidate stopped without model retry. The full suite passes **195 tests** (21 code workflow/policy/API checks). **3/3 HTTP workflows**, actual browser repair, saved history, desktop/mobile checks and **3/3 existing Eval Lab replays** passed.

Evidence: `docs/code-isolation.json`, `docs/code-core-live.json`, `docs/code-assistant-live.json`, `docs/code-browser.json`, screenshots and `docs/code-eval/`. API repair/generation took **30.9s / 20.4s**, and the separate browser repair **17.6s**. The runtime is a project-owned D:-backed WSL 3.0.3 session with Python 3.13.18, unprivileged UID, no host mounts/network, hard address-space/process/file/CPU limits and bounded output. Swap-cgroup enforcement is unavailable; hard 128 MB address space and one-process limits supplement it. Nonempty regular-file writes are denied; empty-file metadata inside the disposable container is not a read-only filesystem. Scope is two small pure-function contracts, not general repository repair or proof of program correctness.

**Project 08 completed as an MVP:** Assembly generates Python tracker functions and a React component within a fixed item tracker contract. A third model role reviews actual results and selects edge cases. The live `qwen2.5-coder:1.5b` CPU HTTP build used three calls and passed **10/10** isolated API checks in **65.5s**. Five toolchain isolation controls and the full **215-test** suite passed. Edge added two fictional books, marked one done, deleted the other and recovered the remaining item after reload. The preview uses a separate local origin and a journal limited to 30 requests. The evidence includes the passing build, browser interactions, screenshots and earlier model failures.

**Git:** seven completed MVPs have verified delivery on `main`. Assembly was pushed as `cb542b9fe26b8cdc8f981d164f94a71829b2c8b6` and matched remote main after the push. This delivery record follows in a separate commit. [GitHub repository](https://github.com/Anilrao96/genai-portfolio).

**Schedule:** active hourly continuation in this chat, automation ID `build-genai-portfolio-over-two-weeks`, ending before 19 November 00:00 Asia/Kolkata. Local files require the computer and desktop app to be running.

## Next actions

1. Begin project 02 with microphone capture, local speech recognition and a measured model response.
2. Keep completed projects and Agent Eval Lab intact; record actual execution evidence before marking the next MVP complete.

## Known dependencies

- Working Python 3.13 exists under the existing uv installation; the Python 3.10 launcher registration is stale.
- 24 GB system RAM; Intel i5-9300H; about 688 GB available on D: at initial inspection.
- NVIDIA GTX 1650 with 4 GB VRAM detected by Ollama; automatic GPU inference hit the 120-second read timeout. CPU inference works.
- The dedicated portfolio Ollama at `127.0.0.1:11435` has `qwen2.5:1.5b` and `qwen2.5-coder:1.5b` (about 986 MB each), `qwen3:4b` (about 2.5 GB) and `nomic-embed-text:v1.5` (about 274 MB) under `.models` on D:. Chat choices exclude embedding-only models.
- Native WSL 3.0.3 containers are verified for project 06 with storage under this checkout on D:. Docker CLI/Compose are still absent; project 09 remains unfinished. Gemini key/budget are not configured by this task.
- The normal filesystem sandbox restricts local sockets and uv executable creation; verified commands may need narrowly scoped approval review.
