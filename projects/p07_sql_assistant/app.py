import asyncio
import os
from functools import lru_cache
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field
from starlette.middleware.trustedhost import TrustedHostMiddleware

from portfolio_core.ollama import ModelServiceError, OllamaClient, chat_models
from .assistant import DOMAIN, LangChainSqlModel, ModelError, SqlAssistant
from .database import QueryError, ReadOnlyDatabase, SCHEMA, ensure_demo_database

ROOT = Path(__file__).resolve().parents[2]
STATIC = Path(__file__).parent / "static"


class AskRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    question: str = Field(min_length=1, max_length=1200)
    model: str = Field(min_length=1, max_length=120, pattern=r"^[a-zA-Z0-9][a-zA-Z0-9._:/-]*$")
    row_limit: int = Field(default=25, ge=1, le=50)


class QueryRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    sql: str = Field(min_length=1, max_length=6000)
    row_limit: int = Field(default=25, ge=1, le=50)


def create_app(database=None, model_factory=None, catalog=None):
    if database is None:
        path = ROOT / ".runtime" / "sql-assistant" / "fictional-retail.sqlite3"
        ensure_demo_database(path)
        database = ReadOnlyDatabase(path)
    app = FastAPI(title="Retail Lens — SQL Assistant", version="0.1.0")
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=["127.0.0.1", "localhost", "[::1]"])
    catalog = catalog or OllamaClient(os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11435"))
    factory = model_factory or LangChainSqlModel
    slot = asyncio.Semaphore(1)

    @lru_cache(maxsize=4)
    def assistant_for(model):
        return SqlAssistant(database, factory(model))

    @app.middleware("http")
    async def boundaries(request: Request, call_next):
        if request.method == "POST":
            origin = request.headers.get("origin")
            if origin and origin != str(request.base_url).rstrip("/"):
                return JSONResponse({"detail": "Cross-origin requests are not allowed."}, status_code=403)
            chunks, size = [], 0
            async for chunk in request.stream():
                size += len(chunk)
                if size > 16000:
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
        return {"status": "ok", "service": "sql-assistant"}

    @app.get("/api/catalog")
    async def get_catalog():
        return {"dataset": "Northstar Retail — fictional", "schema": SCHEMA, "definitions": DOMAIN,
                "tables": [{"name": name, "row_count": database.execute(f'SELECT COUNT(*) FROM "{name}"')["rows"][0][0]}
                           for name in ("customers", "orders")],
                "max_rows": 50, "read_only": True,
                "default_model": os.getenv("SQL_DEFAULT_MODEL", "qwen3:4b")}

    @app.get("/api/models")
    async def models():
        try:
            return {"models": chat_models(await catalog.models())}
        except ModelServiceError as exc:
            raise HTTPException(503, str(exc)) from exc

    @app.post("/api/ask")
    async def ask(body: AskRequest):
        try:
            await asyncio.wait_for(slot.acquire(), timeout=0.05)
        except TimeoutError as exc:
            raise HTTPException(429, "A question is already being answered. Try again shortly.") from exc
        try:
            async with asyncio.timeout(150):
                available = chat_models(await catalog.models())
                if body.model not in {model["name"] for model in available}:
                    raise HTTPException(422, "Select an installed local model.")
                result = await assistant_for(body.model).ask(body.question, body.row_limit)
                result["model"] = body.model
                return result
        except (ModelError, ModelServiceError) as exc:
            raise HTTPException(503, str(exc)) from exc
        except TimeoutError as exc:
            raise HTTPException(504, "The answer exceeded its time budget. Try a simpler question.") from exc
        finally:
            slot.release()

    @app.post("/api/query")
    async def query(body: QueryRequest):
        try:
            return await asyncio.to_thread(database.execute, body.sql, body.row_limit)
        except QueryError as exc:
            code = 403 if exc.kind == "forbidden" else 503 if exc.kind == "unavailable" else 422
            raise HTTPException(code, {"kind": exc.kind, "message": str(exc)}) from exc

    @app.get("/", include_in_schema=False)
    async def index():
        return FileResponse(STATIC / "index.html")

    app.mount("/static", StaticFiles(directory=STATIC), name="static")
    return app


app = create_app()
