import asyncio
import json
import os
from functools import lru_cache
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field
from starlette.middleware.trustedhost import TrustedHostMiddleware

from portfolio_core.ollama import ModelServiceError, OllamaClient, chat_models
from .assistant import RagAssistant, RagModel
from .embeddings import LocalEmbeddings
from .index import IndexError, RagIndex

ROOT = Path(__file__).resolve().parents[2]
STATIC = Path(__file__).parent / "static"
DEMO = Path(__file__).parent / "data" / "demo.json"


class NewDocument(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    id: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]{2,39}$")
    title: str = Field(min_length=3, max_length=100)
    text: str = Field(min_length=40, max_length=12000)


class AskRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    question: str = Field(min_length=1, max_length=1200)
    model: str = Field(min_length=1, max_length=120, pattern=r"^[a-zA-Z0-9][a-zA-Z0-9._:/-]*$")
    initial_query: str = Field(default="", max_length=400)


def create_app(index=None, embedder=None, model_factory=None, catalog=None):
    if index is None:
        path = Path(os.getenv("RAG_INDEX_PATH", str(ROOT / ".runtime" / "rag" / "library.sqlite3"))).resolve()
        if not path.is_relative_to((ROOT / ".runtime").resolve()):
            raise ValueError("RAG index must stay inside the portfolio runtime directory.")
        index = RagIndex(path)
    embedder = embedder or LocalEmbeddings()
    catalog = catalog or OllamaClient(os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11435"))
    model_factory = model_factory or RagModel
    slot = asyncio.Semaphore(1)
    app = FastAPI(title="Reference Desk — Agentic RAG", version="0.1.0")
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=["127.0.0.1", "localhost", "[::1]"])

    @lru_cache(maxsize=4)
    def assistant_for(model):
        return RagAssistant(index, embedder, model_factory(model))

    @app.middleware("http")
    async def boundaries(request: Request, call_next):
        if request.method == "POST":
            origin = request.headers.get("origin")
            if origin and origin != str(request.base_url).rstrip("/"):
                return JSONResponse({"detail": "Cross-origin requests are not allowed."}, status_code=403)
            chunks, size = [], 0
            async for chunk in request.stream():
                size += len(chunk)
                if size > 64000:
                    return JSONResponse({"detail": "Request is too large."}, status_code=413)
                chunks.append(chunk)
            request._body = b"".join(chunks)
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Content-Security-Policy"] = "default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; frame-ancestors 'none'"
        return response

    @app.exception_handler(IndexError)
    async def index_error(request, error):
        code = {"invalid": 422, "missing": 404, "conflict": 409, "capacity": 409, "model": 409}.get(error.kind, 503)
        return JSONResponse({"detail": str(error)}, status_code=code)

    @app.exception_handler(ModelServiceError)
    async def model_error(request, error):
        return JSONResponse({"detail": str(error)}, status_code=503)

    async def acquire():
        try:
            await asyncio.wait_for(slot.acquire(), timeout=0.05)
        except TimeoutError as exc:
            raise HTTPException(429, "The library is busy with another request. Try again shortly.") from exc

    @app.get("/health")
    async def health():
        return {"status": "ok", "service": "agentic-rag", "retrieval_protocol": "source-alias-v2"}

    @app.get("/api/library")
    async def library():
        return {**index.catalog(), "configured_embedding_model": embedder.model, "default_model": "qwen3:4b"}

    @app.get("/api/models")
    async def models():
        return {"models": chat_models(await catalog.models())}

    @app.get("/api/documents/{document_id}")
    async def document(document_id: str):
        return index.document(document_id)

    @app.post("/api/library/demo")
    async def seed():
        await acquire()
        try:
            async with asyncio.timeout(180):
                return await index.ingest(json.loads(DEMO.read_text(encoding="utf-8"))["documents"], embedder)
        except TimeoutError as exc:
            raise HTTPException(504, "Sample indexing exceeded its time budget. You can retry safely.") from exc
        finally:
            slot.release()

    @app.post("/api/documents")
    async def add(body: NewDocument):
        await acquire()
        try:
            async with asyncio.timeout(180):
                return await index.ingest([body.model_dump()], embedder)
        except TimeoutError as exc:
            raise HTTPException(504, "Indexing exceeded its time budget. You can retry safely.") from exc
        finally:
            slot.release()

    @app.post("/api/ask")
    async def ask(body: AskRequest):
        await acquire()
        try:
            async with asyncio.timeout(240):
                models = chat_models(await catalog.models())
                if body.model not in {model["name"] for model in models}:
                    raise HTTPException(422, "Select an installed chat model.")
                result = await assistant_for(body.model).ask(body.question, body.initial_query)
                result.update(model=body.model, embedding_model=embedder.model)
                return result
        except TimeoutError as exc:
            raise HTTPException(504, "The bounded retrieval/answer time budget was exceeded. Try a narrower question.") from exc
        finally:
            slot.release()

    @app.get("/", include_in_schema=False)
    async def home():
        return FileResponse(STATIC / "index.html")

    app.mount("/static", StaticFiles(directory=STATIC), name="static")
    return app


app = create_app()
