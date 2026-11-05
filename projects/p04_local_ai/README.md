# 04 — Local AI Studio

A loopback-only FastAPI application with a browser conversation interface and real Ollama inference. No paid API, account, frontend build step or mandatory GPU is required.

From the portfolio root, run `scripts/Setup.ps1`, then `scripts/Start-Ollama.ps1`, pull a model on port 11435, and run `scripts/Start-LocalAI.ps1`. See the root README for exact commands. Open <http://127.0.0.1:8104> and select an installed model. API contracts are at `/docs`.

## Architecture

Browser → FastAPI request validation → one-generation concurrency slot → shared async Ollama HTTP adapter → local model → answer, timing and provider token counts → browser.

- Models are discovered from `/api/tags`; inference uses `/api/chat` with `stream=false` and a 512-token output budget.
- CPU inference (`num_gpu=0`) is the default because the initial automatic CUDA path timed out on this machine. A direct CPU probe produced the expected answer. `LOCAL_AI_NUM_GPU` can override this for later hardware experiments; no GPU performance claim is made.
- Up to 20 history messages / 12,000 input characters; individual messages up to 4,000 characters. Ollama uses a 4,096-token context, so character limits cannot guarantee every message fits. Context truncation is a documented limitation.
- One active generation at a time; excess requests get HTTP 429. The upstream read timeout is 120 seconds, not a total-generation deadline.
- The browser holds history in memory only; refresh starts a new chat. The server has no database and does not log prompt content. Ollama maintains its own runtime/cache behavior.
- Responses use text nodes, avoiding execution of model-generated HTML. Host and same-origin checks reduce accidental local exposure. There is no authentication: keep this service bound to loopback.
- Health is process liveness; model readiness is shown separately. Unavailable services, unknown models, malformed answers and input limits have explicit error paths.

## Verification and limitations

`scripts/Test.ps1` exercises HTTP model contracts with a mock transport and API routes with an injected fixture provider. These tests do not prove live model quality. See `docs/session-log.md` for actual live verification.

Initial MVP uses complete responses rather than token streaming. No file tools, execution tools, retrieval or internet access are available. Model answers may be wrong. CPU inference can take many seconds and is not a latency benchmark for hosted services. Streaming, cancellation and persistent user-controlled conversations are follow-up improvements.

Official API references: [chat](https://docs.ollama.com/api/chat), [model listing](https://docs.ollama.com/api/tags), [FastAPI](https://fastapi.tiangolo.com/tutorial/first-steps/).
