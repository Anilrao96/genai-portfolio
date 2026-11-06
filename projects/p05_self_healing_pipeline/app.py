import asyncio
import os
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field
from starlette.middleware.trustedhost import TrustedHostMiddleware

from portfolio_core.ollama import ModelServiceError, OllamaClient, chat_models
from .contract import ALIASES, TRANSFORMS
from .engine import Pipeline, RepairPlanner
from .store import Store, StoreError, runtime_path

STATIC = Path(__file__).with_name("static")
DATA = Path(__file__).with_name("data")


class IngestRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    csv_text: str = Field(min_length=1, max_length=32000)
    date_style: Literal["month_first", "year_first"] = "month_first"
    model: str = Field(default="qwen3:4b", min_length=1, max_length=120, pattern=r"^[a-zA-Z0-9][a-zA-Z0-9._:/-]*$")


class RollbackRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    target_revision: int = Field(ge=0)
    expected_active_revision: int = Field(ge=0)


def create_app(store=None, planner_factory=None, catalog=None):
    store = store or Store(runtime_path(os.getenv("PIPELINE_STATE_PATH")))
    factory = planner_factory or RepairPlanner
    catalog = catalog or OllamaClient(os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11435"))
    slot = asyncio.Semaphore(1)
    app = FastAPI(title="Clearflow — Self-healing data pipeline", version="1.0.0")
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=["127.0.0.1", "localhost", "[::1]"])

    @app.middleware("http")
    async def boundaries(request: Request, call_next):
        if request.method == "POST":
            origin = request.headers.get("origin")
            if origin and origin != str(request.base_url).rstrip("/"):
                return JSONResponse({"detail": "Cross-origin requests are not allowed."}, status_code=403)
            chunks, size = [], 0
            async for chunk in request.stream():
                size += len(chunk)
                if size > 65000:
                    return JSONResponse({"detail": "Request is too large."}, status_code=413)
                chunks.append(chunk)
            request._body = b"".join(chunks)
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Cache-Control"] = "no-store"
        response.headers["Content-Security-Policy"] = "default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; frame-ancestors 'none'"
        response.headers["Referrer-Policy"] = "no-referrer"
        return response

    @app.exception_handler(StoreError)
    async def store_error(request, error):
        return JSONResponse({"detail": str(error)}, status_code=404 if str(error).endswith("not found.") else 409)

    @app.get("/health")
    async def health():
        return {"status": "ok", "service": "self-healing-pipeline", "contract": "orders-v1"}

    @app.get("/api/config")
    async def config():
        return {"aliases": ALIASES, "transforms": TRANSFORMS, "default_model": "qwen3:4b",
                "samples": {name: (DATA / f"{name}.csv").read_text(encoding="utf-8") for name in ("baseline", "drifted", "quarantine")}}

    @app.get("/api/models")
    async def models():
        try:
            return {"models": chat_models(await catalog.models())}
        except ModelServiceError as exc:
            raise HTTPException(503, str(exc)) from exc

    @app.get("/api/snapshot")
    async def snapshot():
        return await asyncio.to_thread(store.snapshot)

    @app.get("/api/history")
    async def history():
        return await asyncio.to_thread(store.history)

    @app.get("/api/batches/{batch_id}")
    async def batch(batch_id: str):
        if len(batch_id) != 32 or any(c not in "0123456789abcdef" for c in batch_id):
            raise HTTPException(404, "Batch not found.")
        return await asyncio.to_thread(store.batch, batch_id)

    async def ingest(body, replay_of=None):
        try:
            await asyncio.wait_for(slot.acquire(), timeout=0.05)
        except TimeoutError as exc:
            raise HTTPException(429, "Another batch is being processed. Try again shortly.") from exc
        try:
            return await Pipeline(store, factory(body.model)).ingest(body.csv_text, body.date_style, body.model, replay_of)
        finally:
            slot.release()

    @app.post("/api/ingest")
    async def new_batch(body: IngestRequest):
        return await ingest(body)

    @app.post("/api/batches/{batch_id}/replay")
    async def replay(batch_id: str, body: IngestRequest):
        return await ingest(body, batch_id)

    @app.post("/api/rollback")
    async def rollback(body: RollbackRequest):
        return await asyncio.to_thread(store.rollback, body.target_revision, body.expected_active_revision)

    @app.get("/", include_in_schema=False)
    async def index():
        return FileResponse(STATIC / "index.html")

    app.mount("/static", StaticFiles(directory=STATIC), name="static")
    return app


app = create_app()
