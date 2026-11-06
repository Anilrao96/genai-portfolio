import asyncio
import os
import time
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field, model_validator
from starlette.middleware.trustedhost import TrustedHostMiddleware

from portfolio_core.ollama import ModelServiceError, OllamaClient, chat_models

STATIC = Path(__file__).parent / "static"
SYSTEM_PROMPT = "You are a helpful local assistant. Be concise and honest about uncertainty. Never claim you ran tools or accessed files; you have no tools."


class Message(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=4000)


class ChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    model: str = Field(min_length=1, max_length=120, pattern=r"^[a-zA-Z0-9][a-zA-Z0-9._:/-]*$")
    messages: list[Message] = Field(min_length=1, max_length=20)

    @model_validator(mode="after")
    def check_history(self):
        if self.messages[-1].role != "user":
            raise ValueError("The last message must be from the user.")
        if sum(len(m.content) for m in self.messages) > 12000:
            raise ValueError("Conversation is too long. Start a new chat.")
        return self


def create_app(provider=None):
    app = FastAPI(title="Local AI Studio", version="0.1.0")
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=["127.0.0.1", "localhost", "[::1]"])
    app.state.provider = provider or OllamaClient(
        os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11435"),
        num_gpu=int(os.getenv("LOCAL_AI_NUM_GPU", "0")),
    )
    app.state.generation_slot = asyncio.Semaphore(1)

    @app.middleware("http")
    async def local_boundaries(request: Request, call_next):
        if request.method == "POST":
            origin = request.headers.get("origin")
            if origin and origin != str(request.base_url).rstrip("/"):
                return JSONResponse({"detail": "Cross-origin requests are not allowed."}, status_code=403)
            # Enforce the limit on actual bytes, including chunked requests.
            chunks = []
            size = 0
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

    @app.get("/health")
    async def health():
        return {"status": "ok", "service": "local-ai"}

    @app.get("/api/models")
    async def models():
        try:
            return {"models": chat_models(await app.state.provider.models())}
        except ModelServiceError as exc:
            raise HTTPException(503, str(exc)) from exc

    @app.post("/api/chat")
    async def chat(body: ChatRequest):
        try:
            await asyncio.wait_for(app.state.generation_slot.acquire(), timeout=0.05)
        except TimeoutError as exc:
            raise HTTPException(429, "A response is already being generated. Try again shortly.") from exc
        start = time.perf_counter()
        try:
            available = chat_models(await app.state.provider.models())
            if body.model not in {item["name"] for item in available}:
                raise HTTPException(422, "Select a model installed on this Ollama instance.")
            messages = [{"role": "system", "content": SYSTEM_PROMPT}] + [m.model_dump() for m in body.messages]
            result = await app.state.provider.chat(body.model, messages)
            result["elapsed_ms"] = round((time.perf_counter() - start) * 1000, 1)
            return result
        except ModelServiceError as exc:
            raise HTTPException(503, str(exc)) from exc
        finally:
            app.state.generation_slot.release()

    @app.get("/", include_in_schema=False)
    async def index():
        return FileResponse(STATIC / "index.html")

    app.mount("/static", StaticFiles(directory=STATIC), name="static")
    return app


app = create_app()
