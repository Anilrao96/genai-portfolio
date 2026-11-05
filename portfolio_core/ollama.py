"""Small async adapter for the documented Ollama HTTP API."""
from urllib.parse import urlsplit

import httpx


class ModelServiceError(Exception):
    """A provider failure with a safe user-facing message."""


class OllamaClient:
    def __init__(self, base_url: str, transport=None, num_gpu: int | None = None):
        parsed = urlsplit(base_url)
        if (parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}
                or parsed.username or parsed.password or parsed.path not in {"", "/"}
                or parsed.query or parsed.fragment):
            raise ValueError("Ollama must use a plain loopback HTTP endpoint.")
        self.base_url = base_url.rstrip("/")
        self.transport = transport
        self.num_gpu = num_gpu

    async def _request(self, method: str, path: str, payload=None):
        try:
            async with httpx.AsyncClient(base_url=self.base_url, transport=self.transport,
                                        timeout=httpx.Timeout(120, connect=5), trust_env=False) as client:
                response = await client.request(method, path, json=payload)
                response.raise_for_status()
                result = response.json()
                if not isinstance(result, dict) or result.get("error"):
                    raise ModelServiceError("Ollama returned an invalid response.")
                return result
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404:
                raise ModelServiceError("Model unavailable. Pull the selected model on the portfolio Ollama instance.") from exc
            raise ModelServiceError("Ollama rejected the request. Check its local log.") from exc
        except (httpx.RequestError, ValueError) as exc:
            raise ModelServiceError("Ollama is unavailable or timed out. Start scripts/Start-Ollama.ps1 and try again.") from exc

    async def models(self):
        result = await self._request("GET", "/api/tags")
        models = result.get("models")
        if not isinstance(models, list) or any(not isinstance(m, dict) or not isinstance(m.get("name"), str) for m in models):
            raise ModelServiceError("Ollama returned an invalid model list.")
        return [{"name": m["name"], "size_bytes": m.get("size"), "details": m.get("details", {})} for m in models]

    async def chat(self, model: str, messages: list[dict]):
        options = {"temperature": 0.4, "num_predict": 512, "num_ctx": 4096}
        if self.num_gpu is not None:
            options["num_gpu"] = self.num_gpu
        result = await self._request("POST", "/api/chat", {
            "model": model, "messages": messages, "stream": False,
            "keep_alive": "5m", "options": options,
        })
        message = result.get("message")
        if not isinstance(message, dict) or not isinstance(message.get("content"), str) or not message["content"].strip() or result.get("done") is not True:
            raise ModelServiceError("Ollama returned an incomplete or empty answer.")
        return {"answer": message["content"], "model": result.get("model", model),
                "input_tokens": result.get("prompt_eval_count"), "output_tokens": result.get("eval_count"),
                "generation_duration_ns": result.get("eval_duration")}
