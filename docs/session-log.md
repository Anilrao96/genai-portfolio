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
