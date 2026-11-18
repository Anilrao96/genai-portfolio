# Sprint results

The 5–18 November 2026 build window ended at 19 November 00:00 Asia/Kolkata. Nine of the ten article projects met their MVP acceptance checks and were pushed to GitHub. The recurring build automation was deleted during closeout.

| Article project | Result |
| --- | --- |
| 01 Support Council | Live MCP role calls, checked decisions and persisted handoffs delivered. |
| 02 Relay | Local voice capture, recognition, streamed replies, speech and cancellation delivered. Browser verification used a synthetic microphone. |
| 03 Reference Desk | Persistent retrieval, source passages, recovery search and abstention delivered. |
| 04 Local AI Studio | Local Ollama chat and browser workflow delivered. |
| 05 Clearflow | Model extraction plans, validation, quarantine, replay and snapshot rollback delivered. |
| 06 Repair Bench | Code generation and repair in the verified native WSL container runtime delivered. |
| 07 Retail Lens | LangChain SQL workflow with SQLite-enforced read-only access delivered. |
| 08 Assembly | Generated tracker app, isolated build and tests, and interactive browser preview delivered. |
| 09 Clearflow Docker Agent | Actual Compose readiness, local model repair and audit volume persistence delivered. |
| 10 Sightline | Implemented and offline-verified locally. Live Gemini verification and GitHub delivery remain pending. |

GitHub main matched local `69610c39b63faadd73bcc56be1751b39b7635e98` at the start of closeout. That history contains all nine delivered projects, the Docker evaluation report and the clean setup audit. The closeout report is published in a subsequent commit. [Repository](https://github.com/Anilrao96/genai-portfolio) · [Demo walkthrough](portfolio-walkthrough.md).

The released nine-project revision passed **237 tests** in a clean archive with a fresh environment. The local working tree including Sightline passed **269 tests**, including **32** Sightline cases. These are recorded verification results from the build sessions. The clean archive also launched Local AI Studio and returned `42` through real local Ollama and Edge. The release audit records the nine delivery commits and hashes of 33 evidence files. [Release audit](portfolio-release-audit.json).

Sightline's local implementation validates image uploads, constructs Gemini requests, validates graph reports and generates a Windows speech summary. Its browser demo and provider transport fixtures passed, and the WAV played to completion. The captured diagram report is authored fixture data. At closeout, `GEMINI_API_KEY` was absent from the launch environment, no budget had been agreed, and there was no live Gemini capture. Its source, tests, offline evidence and pending documentation remain in the working tree at `D:\genai-portfolio`.

Finishing Sightline requires renewed work authorization after the sprint, a securely configured Gemini key and an agreed request budget. The local project README contains the single-request verification procedure. After a real response passes the graph and speech checks, the remaining delivery steps are documentation review, commit, push and remote SHA verification.

The independent Agent Eval Lab checkout was clean at closeout. Its existing contracts and reports were reused in the portfolio evaluations.
