# Fourteen-day roadmap

Window: **5–18 November 2026**, Asia/Kolkata. Aim: ten portfolio-quality MVPs. This is a build schedule, not a promise of ten production systems. Finish a working slice before starting another. Use spare sessions for evidence, integration and polish.

| Day / date | Article project | Deliverable |
| --- | --- | --- |
| 1 / Nov 5 | 04 Local AI | Shared model adapter; local chat UI; model selection; bounded requests; first real response |
| 2 / Nov 6 | 07 SQL assistant | Natural language to read-only SQLite queries; schema grounding; result explanation; adversarial query checks |
| 3 / Nov 7 | 03 Agentic RAG | Document ingestion; persistent index; cited answers; retrieval grading and bounded query rewrite |
| 4 / Nov 8 | 01 MCP agents | Researcher, analyst and reviewer using actual MCP tools; shared structured state; bounded orchestration and traces |
| 5 / Nov 9 | 05 Data pipeline | Detect schema drift; propose constrained repairs; validate, quarantine and replay; audit evidence |
| 6 / Nov 10 | 06 Code assistant | Generate, execute in actual isolation, inspect failures and repair; strict resource/attempt limits |
| 7 / Nov 11 | 08 App builder | Structured specification; backend generator; isolated workspace; build validation |
| 8 / Nov 12 | 08 App builder | React frontend generator; QA feedback loop; one complete generated sample application |
| 9 / Nov 13 | 02 Voice agent | Microphone capture; real speech-to-text; local model response; measurable stage timing |
| 10 / Nov 14 | 02 Voice agent | Speech playback; streaming/cancellation; permission and failure handling; recorded demo |
| 11 / Nov 15 | 09 Docker agent | FastAPI agent in Docker; Compose health checks, volumes and configuration; tested clean startup |
| 12 / Nov 16 | 10 Multimodal Gemini | Real Gemini image input to validated JSON report and speech summary; credential-free contract tests |
| 13 / Nov 17 | All + existing Eval Lab | Integrate selected apps with existing Agent Eval Lab; regression cases; real model evidence and limits |
| 14 / Nov 18 | All | Clean-start walkthroughs; architecture notes; demo evidence; portfolio index and interview notes |

## Definition of done

Every project needs: an actual AI path, reproducible setup and one-command startup, a concrete end-to-end sample, architecture/data-flow notes, failure handling, focused tests, and a demo artifact or live run log. Document actual model, runtime, latency and resource constraints. Keep fixture-based results explicitly labeled. Mark live verification blocked when required hardware, isolation, Docker or a provider key is absent; continue independent work.

## Project-specific checks

1. **MCP agents:** real MCP client/server discovery and calls, independently specialized roles, run/step budgets, inspectable tool trace and at least one failure case. Python SDK and orchestration framework chosen after current-doc verification.
2. **Voice:** actual audio input and output, replaceable STT/TTS adapters, cancellation and latency measurement. Do not claim subsecond performance without measurements on this machine.
3. **RAG:** retrieval source IDs, abstention on insufficient evidence, bounded recovery search, persisted documents/index and answer-grounding cases. Start local; add a second retrieval backend if useful.
4. **Local AI:** real Ollama inference, browser chat, model list/selection, request bounds, history control, useful offline/unavailable behavior, measured latency and explicit CPU/GPU limits.
5. **Pipeline:** schema change detection; repair suggestions validated against a constrained transformation language rather than unrestricted patch execution; rollback/quarantine; before/after data-quality evidence.
6. **Code:** real isolation, time/output/memory limits and attempt budget; a failing sample corrected successfully; disallowed file/network operations rejected. If isolation is unavailable, keep live execution blocked.
7. **SQL:** schema-only prompt context; actual read-only connection/authorizer; deny writes and unsafe extensions; cap work and rows; return SQL, results and an evidence-based summary. SQLite MVP; PostgreSQL upgrade documented.
8. **App builder:** backend, frontend and QA roles; generated files limited to a dedicated workspace; actual build/tests; no untrusted code execution on the host; one working generated app.
9. **Docker:** build image, run Compose, readiness/health, persistent data and documented configuration/secrets; verify actual container execution instead of only creating YAML.
10. **Gemini:** actual image API integration, schema validation, input limits, no hard-coded key, useful provider errors and generated speech summary. Live verification depends on a securely configured key/budget.

## Reuse and dependencies

- Agent Eval Lab is completed external work at `D:\agent-eval-lab`, repository `https://github.com/Anilrao96/agent-eval-lab`. Reuse its `AgentInput`, `Prediction`, `ToolEvent` adapter contracts and reports. Do not recreate its evaluator.
- Python/FastAPI for shared services; React for the generated full-stack application. Use project-specific libraries where they materially serve the named architecture.
- Default Ollama instance is loopback port 11435 with weights under this project on D:. Do not change the existing user-wide Ollama configuration.
- Docker was not detected in PATH during initial inspection. Resolve availability before the code execution and container milestones; use non-executing independent work if installation needs user intervention.
- No API key or paid usage is assumed. Gemini live verification remains a dependency until a provider and budget are configured.
- Hourly continuation stops by 19 November 00:00 local time; no catch-up or startup-trigger behavior is assumed.
