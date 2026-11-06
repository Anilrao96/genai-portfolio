from fastapi.testclient import TestClient

from projects.p01_mcp_agents.app import create_app
from projects.p01_mcp_agents.state import Store


class Catalog:
    async def models(self):
        return [{"name": "qwen3:4b", "capabilities": ["completion"]},
                {"name": "embed", "capabilities": ["embedding"]}]


def client(tmp_path):
    return TestClient(create_app(Store(tmp_path / "api.sqlite3"), catalog=Catalog()), base_url="http://127.0.0.1")


def test_catalog_models_health_and_missing_run(tmp_path):
    api = client(tmp_path)
    assert api.get("/health").json()["protocol"] == "role-scoped-v1"
    assert len(api.get("/api/catalog").json()["plans"]) == 3
    assert api.get("/api/models").json()["models"] == [{"name": "qwen3:4b", "capabilities": ["completion"]}]
    assert api.get("/api/runs").json() == {"runs": []}
    assert api.get("/api/runs/not-an-id").status_code == 404
    assert api.get("/api/runs/" + "0" * 32).status_code == 404


def test_http_boundaries_and_invalid_model(tmp_path):
    api = client(tmp_path)
    payload = dict(seats=12, budget_cents=30000, support_24h=True, model="embed")
    assert api.post("/api/decide", json=payload).status_code == 422
    assert api.post("/api/decide", json=payload, headers={"Origin": "https://other.example"}).status_code == 403
    assert api.post("/api/decide", content="x" * 8001).status_code == 413
    assert api.get("/", headers={"Host": "other.example"}).status_code == 400
    for change in ({"seats": 501}, {"budget_cents": -1}, {"support_24h": "yes"}, {"extra": 1}):
        assert api.post("/api/decide", json={**payload, **change}).status_code == 422
    assert "frame-ancestors 'none'" in api.get("/").headers["content-security-policy"]
