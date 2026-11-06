import asyncio
import json
import os
import re
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import Field
from starlette.middleware.trustedhost import TrustedHostMiddleware

from portfolio_core.ollama import ModelServiceError, OllamaClient, chat_models
from .state import CATALOG, Requirements, Store, runtime_path
from .team import Council, LocalRoles

STATIC = Path(__file__).with_name("static")


class DecisionRequest(Requirements):
    model: str = Field(min_length=1, max_length=120, pattern=r"^[a-zA-Z0-9][a-zA-Z0-9._:/-]*$")


def create_app(store=None, roles_factory=None, catalog=None):
    store = store or Store(runtime_path(os.getenv("MCP_STATE_PATH")))
    factory = roles_factory or LocalRoles
    catalog = catalog or OllamaClient(os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11435"))
    app = FastAPI(title="Support Council — MCP agents", version="1.0.0")
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=["127.0.0.1", "localhost", "[::1]"])
    slot = asyncio.Semaphore(1)

    @app.middleware("http")
    async def boundaries(request: Request, call_next):
        if request.method == "POST":
            origin = request.headers.get("origin")
            if origin and origin != str(request.base_url).rstrip("/"):
                return JSONResponse({"detail": "Cross-origin requests are not allowed."}, status_code=403)
            chunks, size = [], 0
            async for chunk in request.stream():
                size += len(chunk)
                if size > 8000:
                    return JSONResponse({"detail": "Request is too large."}, status_code=413)
                chunks.append(chunk)
            request._body = b"".join(chunks)
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Content-Security-Policy"] = "default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; frame-ancestors 'none'"
        response.headers["Referrer-Policy"] = "no-referrer"
        return response

    @app.get("/health")
    async def health():
        return {"status": "ok", "service": "mcp-council", "protocol": "role-scoped-v1"}

    @app.get("/api/catalog")
    async def get_catalog():
        return {**CATALOG, "default_model": "qwen3:4b"}

    @app.get("/api/models")
    async def models():
        try:
            return {"models": chat_models(await catalog.models())}
        except ModelServiceError as exc:
            raise HTTPException(503, str(exc)) from exc

    @app.get("/api/runs")
    async def history():
        return {"runs": await asyncio.to_thread(store.history)}

    @app.get("/api/runs/{run_id}")
    async def run_details(run_id: str):
        if not re.fullmatch(r"[0-9a-f]{32}", run_id):
            raise HTTPException(404, "Run not found.")
        try:
            run = await asyncio.to_thread(store.get, run_id)
        except ValueError as exc:
            raise HTTPException(404, "Run not found.") from exc
        trace_path = store.path.parent / "traces" / f"{run_id}.json"
        result = json.loads(trace_path.read_text(encoding="utf-8")) if trace_path.exists() else {"run": run, "trace": []}
        return {**result, "events": store.events(run_id)}

    @app.post("/api/decide")
    async def decide(body: DecisionRequest):
        try:
            await asyncio.wait_for(slot.acquire(), timeout=0.05)
        except TimeoutError as exc:
            raise HTTPException(429, "A team is already working. Try again shortly.") from exc
        try:
            if body.model not in {m["name"] for m in chat_models(await catalog.models())}:
                raise HTTPException(422, "Select an installed chat model.")
            req = Requirements.model_validate(body.model_dump(exclude={"model"}))
            result = await Council(store, factory(body.model)).run(req)
            return {**result, "model": body.model}
        except ModelServiceError as exc:
            raise HTTPException(503, str(exc)) from exc
        finally:
            slot.release()

    @app.get("/", include_in_schema=False)
    async def index():
        return FileResponse(STATIC / "index.html")

    app.mount("/static", StaticFiles(directory=STATIC), name="static")
    return app


app = create_app()
