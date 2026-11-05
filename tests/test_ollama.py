import asyncio
import json

import httpx
import pytest

from portfolio_core.ollama import ModelServiceError, OllamaClient


def run(awaitable):
    return asyncio.run(awaitable)


def test_actual_chat_contract_and_usage():
    def handler(request):
        assert request.url.path == "/api/chat"
        payload = json.loads(request.content)
        assert payload["stream"] is False
        assert payload["options"]["num_predict"] == 512
        assert payload["messages"] == [{"role": "user", "content": "Hello"}]
        return httpx.Response(200, json={"message": {"content": "Hi"}, "done": True, "model": "fixture", "eval_count": 2})
    client = OllamaClient("http://127.0.0.1:11435", httpx.MockTransport(handler))
    result = run(client.chat("fixture", [{"role": "user", "content": "Hello"}]))
    assert result["answer"] == "Hi"
    assert result["output_tokens"] == 2
    assert result["input_tokens"] is None


@pytest.mark.parametrize("body", [{}, {"message": {"content": ""}, "done": True}, {"message": {"content": "partial"}, "done": False}, {"error": "internal secret"}])
def test_incomplete_or_failed_model_output_is_not_success(body):
    client = OllamaClient("http://localhost:11435", httpx.MockTransport(lambda r: httpx.Response(200, json=body)))
    with pytest.raises(ModelServiceError):
        run(client.chat("fixture", []))


@pytest.mark.parametrize("url", ["https://example.com", "http://127.0.0.1.evil.example", "http://user:secret@localhost", "http://localhost/api", "http://localhost?key=x"])
def test_model_endpoint_stays_local(url):
    with pytest.raises(ValueError):
        OllamaClient(url)


def test_provider_error_does_not_leak_response_body():
    client = OllamaClient("http://localhost", httpx.MockTransport(lambda r: httpx.Response(500, text="private provider details")))
    with pytest.raises(ModelServiceError, match="rejected") as error:
        run(client.models())
    assert "private" not in str(error.value)


def test_cpu_fallback_is_sent_explicitly():
    def handler(request):
        assert json.loads(request.content)["options"]["num_gpu"] == 0
        return httpx.Response(200, json={"message": {"content": "42"}, "done": True})
    client = OllamaClient("http://localhost", httpx.MockTransport(handler), num_gpu=0)
    assert run(client.chat("fixture", []))["answer"] == "42"


def test_unreachable_provider_has_actionable_error():
    def handler(request):
        raise httpx.ConnectError("socket failed", request=request)
    client = OllamaClient("http://localhost", httpx.MockTransport(handler))
    with pytest.raises(ModelServiceError, match="Start-Ollama"):
        run(client.models())
