# Portfolio walkthrough

The nine delivered applications run locally on Windows and use fictional inputs. Start with Local AI Studio to verify the common Ollama connection, then pick an application whose demo shows the boundary you want to inspect. The tenth project, Sightline, awaits live Gemini verification.

## Start from a fresh checkout

Run `scripts/Setup.ps1` from the checkout on D:. Setup uses the checked-in `uv.lock`. If Windows points `uv` to a missing interpreter, pass the path to an installed Python 3.13 executable. [uv lockfile behavior](https://docs.astral.sh/uv/concepts/projects/sync/).

```powershell
cd D:\genai-portfolio
.\scripts\Setup.ps1
# If an explicit interpreter is needed, replace the example path:
# .\scripts\Setup.ps1 -Python 'D:\path\to\python.exe'
.\scripts\Start-Ollama.ps1
```

In another terminal, pull the model into the portfolio instance and launch Local AI Studio. The models live under `.models` in the checkout.

```powershell
cd D:\genai-portfolio
$env:OLLAMA_HOST = '127.0.0.1:11435'
ollama pull qwen2.5:1.5b
.\scripts\Start-LocalAI.ps1
```

Open <http://127.0.0.1:8104>, select `qwen2.5:1.5b` and ask “What is 17 + 25? Reply with only the number.” The clean release probe returned `42`. Run `scripts/Test.ps1` for offline tests. For the browser probes, install the locked Playwright dependency with `npm ci --cache .cache/npm` and use the installed Edge browser.

## Demo and evidence index

Run each launcher from the portfolio root after completing its linked setup. Open the app on `127.0.0.1` at the port shown.

| Project and startup | Walkthrough | Recorded evidence |
| --- | --- | --- |
| [01 Support Council](../projects/p01_mcp_agents/README.md) · `Start-McpAgents.ps1` · 8101 | With `qwen3:4b`, submit the 12-seat brief and inspect the three roles and checked $236 recommendation. Use the $10 brief to see the no-fit branch. | [MCP run](mcp-live.json) · [Desktop](mcp-desktop.png) |
| [02 Relay](../projects/p02_voice_agent/README.md) · `Start-Voice.ps1` · 8102 | Run `Setup-Voice.ps1` and use `qwen2.5:1.5b`. Record “What is the capital of France?” Inspect the transcript and listen to the reply. | [Browser capture](voice-browser.json) · [Audio](voice-demo.wav) |
| [03 Reference Desk](../projects/p03_agentic_rag/README.md) · `Start-Rag.ps1` · 8103 | With `qwen3:4b` and `nomic-embed-text:v1.5`, load the fictional library, ask about the return window and open a cited passage. | [Retrieval cases](rag-live.json) · [Persistence](rag-persistence.json) |
| [04 Local AI Studio](../projects/p04_local_ai/README.md) · `Start-LocalAI.ps1` · 8104 | Select `qwen2.5:1.5b`, run the arithmetic prompt and clear the conversation. | [Clean release probe](portfolio-release-audit.json) · [Desktop](local-ai-desktop.png) |
| [05 Clearflow](../projects/p05_self_healing_pipeline/README.md) · `Start-Pipeline.ps1` · 8105 | With `qwen3:4b`, ingest the clean and format drift samples, then correct and replay the quarantined zero quantity. Compare the saved snapshots. | [Repair and replay](pipeline-live.json) |
| [06 Repair Bench](../projects/p06_code_assistant/README.md) · `Start-CodeAssistant.ps1` · 8106 | Run `Setup-CodeAssistant.ps1` for the native WSL sandbox. With `qwen3:4b`, load the failing mean example and inspect the error, repair and test results. | [Actual isolation controls](code-isolation.json) · [Repair run](code-assistant-live.json) |
| [07 Retail Lens](../projects/p07_sql_assistant/README.md) · `Start-SqlAssistant.ps1` · 8107 | With `qwen3:4b`, ask for completed revenue in dollars. Check the SQL, returned rows and the explanation. | [Queries and refusal cases](sql-assistant-live.json) |
| [08 Assembly](../projects/p08_app_builder/README.md) · `Start-AppBuilder.ps1` · 8108 | Run `Setup-AppBuilder.ps1` and use `qwen2.5-coder:1.5b`. Build the Reading Room tracker, add a fictional book and mark it done. | [Isolated checks](app-builder-core-live.json) · [Interactive preview](app-builder-browser.json) |
| [09 Clearflow Docker Agent](../projects/p09_docker_agent/README.md) · `Start-DockerAgent.ps1` · 8109 | Start the native WSL and Compose workflow with `qwen3:4b`. Ingest the sample orders, stop via `-Stop`, restart and reopen the saved repair trace. | [Container recreation](docker-agent-live.json) · [Eval Lab replay](docker-agent-eval/run.json) |

The release audit installed the published Python lockfile in a fresh environment and ran the offline suite. The clean archive ran Local AI Studio through its normal launcher and the existing local Ollama service. The other live artifacts in the table come from their individual milestone runs. [Audit details](portfolio-release-audit.json).

## Interview notes

- **Model output and authority.** Compare Retail Lens and Clearflow. The SQL assistant uses a read-only SQLite connection and an authorizer. The pipeline accepts a bounded extraction plan, validates rows and commits an atomic snapshot. Show a refused write or quarantined batch before describing the success path.
- **Retrieval and protocol evidence.** Reference Desk stores hybrid search state in SQLite, checks source IDs and allows one recovery search. Support Council passes versioned handoffs through actual MCP tools and resources. The captures let you inspect evidence at each step.
- **Execution and persistence.** Repair Bench and Assembly run generated code in the verified native container runtime. The Docker Agent demonstrates a separate deployment concern: running trusted app code in Compose, checking readiness and retaining audit data across container recreation.
- **Interactive latency.** Relay reports recognition, model and speech timing independently. The browser evidence uses a synthetic microphone and completes real playback. The measured laptop runs show the cost of CPU inference without implying the same timing on other machines.
