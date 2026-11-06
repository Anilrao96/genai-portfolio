# Session evidence

## 2026-11-05 — Sprint setup

- Read the source article and mapped all ten numbered projects.
- User confirmed Agent Eval Lab is already done. Inspected `D:\agent-eval-lab\README.md`, package metadata and clean working tree. Existing repository is independent and unchanged. Reuse its evaluation infrastructure; do not rebuild it.
- Working Python: existing uv-managed 3.13.13. Old 3.10 launcher points at a missing executable. Node 22.18.0 and Git 2.54.0 available. System reports 24 GB RAM and i5-9300H; GPU not established. D: has roughly 688 GB free.
- Existing Ollama responded to `ollama list` with no installed models. Local socket inspection required a narrowly scoped escalation due to the filesystem sandbox.
- Initial unprivileged uv environment creation hit a Windows executable-resource access restriction. Dependencies and live inference are pending; no verification results claimed yet.

### Completed verification

- Repaired only the incomplete `D:\genai-portfolio\.venv`, after checking its absolute path. Used the working existing Python 3.13.13; dependencies and caches are under D:. `uv sync --python <existing interpreter>` succeeded and generated `uv.lock`.
- Started a dedicated loopback-only Ollama on port 11435 with `OLLAMA_MODELS=D:\genai-portfolio\.models`; downloaded `qwen2.5:1.5b`, 986,061,892 bytes. No user-wide settings or default-instance models were changed. Runtime logs and PID files are ignored under `.runtime`.
- `D:\genai-portfolio\.venv\Scripts\python.exe -m pytest -q`: **27 passed in 1.65s**, with one upstream Starlette warning about future TestClient HTTP transport migration. Tests use fixtures, not a live model. They cover payload/schema limits, incomplete provider results, local endpoint restriction, provider errors, host/origin boundaries, actual body size, slot release, overlapping-generation rejection and explicit CPU configuration. Restricted-sandbox execution stalled at the event-loop socket boundary; the narrowly elevated run passed.
- `node --check projects/p04_local_ai/static/app.js`: passed.
- The built-in browser-control runtime failed to start twice with a sandbox path error. Used the installed Edge browser in headless mode via a project-local Playwright dependency instead; no normal browser profile was accessed.
- **Initial live GPU attempt failed:** the app returned 503 after the provider read timeout (120 seconds). The request did not establish working GPU inference. The failure record is `local-ai-initial-timeout.json`.
- **Direct CPU probe passed:** Ollama returned `42` for the arithmetic prompt, with about 6.37 seconds provider duration including about 5.57 seconds model load. See `local-ai-cpu-probe.json`.
- Configured the app to default to explicit CPU mode (`num_gpu=0`). Full HTTP app path returned `42`, with **3,785.4 ms** application elapsed time, 57 input tokens and 3 output tokens. This is one smoke-test observation, not a performance guarantee. See `local-ai-live.json`.
- `node scripts/check-ui.cjs`: **passed**. Real Edge UI request returned `42`, no JavaScript errors, mobile width 390 had no horizontal overflow, and New conversation cleared the message list. Saved desktop/mobile screenshots and inspected both; layout is readable. The screenshot's warm request timing is a separate observation from the HTTP run.
- Created and verified an active hourly chat automation, `build-genai-portfolio-over-two-weeks`, with an end before 19 November 2026 00:00 Asia/Kolkata. It resumes saved progress rather than rebuilding Agent Eval Lab. Computer and desktop app must be running for local work.
- Initialized a local Git repository on `main`. No remote, repository publication or GitHub push was performed. The user's follow-up was answered with that distinction.

Next scheduled slice: project 07, SQL assistant. Project 04 is a verified MVP, with non-streaming responses, CPU-only live evidence and no cancellation; see its README for scope limits.

## 2026-11-05 — GitHub delivery authorization

- User instructed: "Push it to my GitHub, and push each project as you complete it."
- Confirmed the connected GitHub account is `Anilrao96`. Destination is one `genai-portfolio` repository for the ten apps and shared code; completed apps receive tested commits and verified pushes.
- The GitHub connector can inspect repositories but does not provide repository creation. Using the existing Git Credential Manager authentication for that missing operation and native Git for pushes. Credentials remain in memory and are never printed or saved in project files.
- Reviewed tracked files and ignore rules: local model weights, node_modules, virtual environments, runtime/browser profiles, caches and secret `.env` files are excluded. Only the credential-free `.env.example` is tracked.
- Git Credential Manager has multiple saved GitHub accounts. Selected the already-connected `Anilrao96` account explicitly and configured that username only in this repository; no login or new credential was needed.
- Created the public `Anilrao96/genai-portfolio` repository and added it as origin. Committed the delivery policy as `70f7fb7326b07ed2c03e8f64a6af42b0e1039f69`, pushed `main`, and verified `git ls-remote origin refs/heads/main` returned exactly the local HEAD SHA.
- Updated the existing hourly automation in place to commit, push and remotely verify each completed project, preserve the existing end date and avoid rebuilding Agent Eval Lab. No duplicate schedule was created.
- Application code did not change during publication; the prior 27 passing tests and live HTTP/browser evidence remain the relevant verification. This delivery record receives a separate commit and push, followed by another remote-head comparison.

## 2026-11-05/06 — Project 07, Retail Lens SQL Assistant

- Resumed the earliest unfinished milestone after inspecting instructions, source and clean Git state. Added a fictional six-customer/twelve-order SQLite fixture, schema-only planning context, LangChain structured planning/summary chains, a FastAPI service, a browser UI and Windows launch/verification scripts.
- Verified current official LangChain ChatOllama and Python/SQLite authorizer/progress-handler documentation, and inspected the installed integration signatures. Locked LangChain Core 1.7.6, LangChain Ollama 1.1.0 and their project-local dependencies with uv; no provider key or paid API was used.
- Implemented independent database enforcement: read-only URI, query_only, approved table/column/function authorizer, one-statement execution, denied writes/ATTACH/PRAGMA/recursion/extensions, VM/time/compiler limits and bounded result rows/cells/payload. Tests caught SQLite 3.53.1 passing a NULL database name for COUNT(*) with no column; corrected only that read case while keeping default-deny authorization.
- The initial Qwen2.5 1.5B live run failed join planning and unsupported-profit behavior. A subsequent run fixed the join but omitted the dollars conversion. Both captures are retained (`sql-assistant-initial-evaluation.json`, `sql-assistant-unit-failure.json`); no success was claimed for them. Strengthened schema instructions and added finite dataset scope checks. Those policy checks do not replace the database guard and are not universal intent detection.
- Downloaded Qwen3 4B Q4_K_M to the existing D: model store. The first transfer hit a CDN DNS failure; a resumed transfer completed and registered the model. The interrupted session ended before final verification and did not publish unfinished SQL work. On 6 November, inspected all existing work, restarted only the project-local loopback services after finding them unavailable, and confirmed the previous GitHub head was still `6dded5a2a939f122f3beb99b516e3b72cf57466d`.
- Final `python scripts/probe-sql.py --model qwen3:4b`: **6/6 scenarios passed**. Four made actual LangChain model calls; missing-profit/write-request cases used deterministic scope routing with zero model calls. Four direct forbidden-query probes returned 403. The SQLite file SHA-256 was unchanged. Manually checked returned summaries against the actual rows: 12 orders; USD 1,430 completed revenue; South at USD 510; cancelled 2, completed 9, refunded 1.
- Actual HTTP app latencies were 120,245.2 ms cold, then 25,080.0 / 31,993.5 / 29,070.8 ms for supported cases. These are individual CPU observations, not a benchmark or performance guarantee. Thinking is disabled for Qwen3 structured responses.
- `python -m pytest -q --tb=short`: **77 passed in 11.48s** (50 SQL tests plus the existing 27), including actual SQLite write refusal, unknown schema/function refusal, computation interruption, row/cell/payload bounds, one repair, refusal/clarification and API boundaries. JavaScript and Python entry-point syntax checks passed.
- `node scripts/check-sql-ui.cjs`: **passed** using existing Edge in headless mode and an isolated D: profile. Real model result contained USD 1,430; SQL/result table were visible; no JavaScript errors; 390px mobile viewport had no horizontal overflow; missing-metric and write-refusal UI behavior passed. Saved and visually inspected desktop/mobile screenshots. This separate UI inference took about 48 seconds.
- `python scripts/evaluate-sql.py --eval-lab-root D:\agent-eval-lab`: **6/6 recorded-outcome contracts passed, zero execution errors**. Reused the existing runner, dataset contracts, ToolEvent/Prediction types and report renderer. The adapter replays actual captured outcomes and traces without new inference; report labels explicitly distinguish replay overhead from inference latency. Evaluation labels stay separate from the application. Agent Eval Lab's working tree remains clean and unchanged; bytecode writes to it were disabled.
- Preserved Local AI Studio's original verified Qwen2.5 default after adding a second installed model. No app service was hosted externally. SQL publication is the next authorized action, followed by project 03 Agentic RAG.
