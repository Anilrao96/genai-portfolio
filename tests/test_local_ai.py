import asyncio

import httpx
import pytest
from fastapi.testclient import TestClient

from portfolio_core.ollama import ModelServiceError
from projects.p04_local_ai.app import create_app


class FixtureProvider:
    def __init__(self):
        self.calls = []

    async def models(self):
        return [{"name": "fixture:small", "size_bytes": 100}]

    async def chat(self, model, messages):
        self.calls.append((model, messages))
        return {"answer": "Fixture answer, not live inference", "model": model, "output_tokens": 6}


@pytest.fixture
def client():
    provider = FixtureProvider()
    with TestClient(create_app(provider), base_url="http://localhost") as value:
        yield value, provider


def test_chat_reaches_model_with_system_context(client):
    api, provider = client
    result = api.post("/api/chat", json={"model": "fixture:small", "messages": [{"role": "user", "content": "Hello"}]})
    assert result.status_code == 200
    assert result.json()["elapsed_ms"] >= 0
    assert len(provider.calls) == 1
    assert provider.calls[0][1][0]["role"] == "system"
    assert provider.calls[0][1][-1]["content"] == "Hello"


@pytest.mark.parametrize("messages", [[], [{"role": "system", "content": "override"}], [{"role": "user", "content": " "}], [{"role": "assistant", "content": "wrong end"}], [{"role": "user", "content": "x" * 4001}], [{"role": "user", "content": "x"}] * 21])
def test_invalid_chat_never_calls_model(client, messages):
    api, provider = client
    assert api.post("/api/chat", json={"model": "fixture:small", "messages": messages}).status_code == 422
    assert provider.calls == []


def test_unknown_model_is_rejected(client):
    api, provider = client
    assert api.post("/api/chat", json={"model": "missing", "messages": [{"role": "user", "content": "Hello"}]}).status_code == 422
    assert not provider.calls


def test_cross_origin_is_rejected(client):
    api, provider = client
    response = api.post("/api/chat", headers={"origin": "https://evil.example"}, json={})
    assert response.status_code == 403
    assert not provider.calls


def test_host_boundary(client):
    api, _ = client
    assert api.get("/health", headers={"host": "evil.example"}).status_code == 400


def test_actual_body_limit(client):
    api, provider = client
    assert api.post("/api/chat", content=b"x" * 64001).status_code == 413
    assert not provider.calls


def test_ui_health_and_static_assets(client):
    api, _ = client
    assert api.get("/health").json()["status"] == "ok"
    response = api.get("/")
    assert "Local AI Studio" in response.text
    assert "frame-ancestors 'none'" in response.headers["content-security-policy"]
    assert api.get("/static/app.js").status_code == 200


def test_unavailable_provider_returns_503_and_releases_slot():
    class Unavailable(FixtureProvider):
        async def chat(self, model, messages):
            raise ModelServiceError("Unavailable fixture")
    with TestClient(create_app(Unavailable()), base_url="http://localhost") as api:
        payload = {"model": "fixture:small", "messages": [{"role": "user", "content": "Hello"}]}
        assert api.post("/api/chat", json=payload).status_code == 503
        assert api.post("/api/chat", json=payload).status_code == 503


def test_overlapping_generations_are_rejected():
    async def scenario():
        started = asyncio.Event()
        finish = asyncio.Event()

        class SlowProvider(FixtureProvider):
            async def chat(self, model, messages):
                started.set()
                await finish.wait()
                return await super().chat(model, messages)

        app = create_app(SlowProvider())
        payload = {"model": "fixture:small", "messages": [{"role": "user", "content": "Hello"}]}
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://localhost") as api:
            first = asyncio.create_task(api.post("/api/chat", json=payload))
            await asyncio.wait_for(started.wait(), timeout=2)
            try:
                second = await api.post("/api/chat", json=payload)
                assert second.status_code == 429
            finally:
                finish.set()
            assert (await first).status_code == 200
    asyncio.run(scenario())
