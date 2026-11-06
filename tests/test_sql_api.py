import pytest
from fastapi.testclient import TestClient

from projects.p07_sql_assistant.app import create_app
from projects.p07_sql_assistant.assistant import ModelError, QueryPlan
from projects.p07_sql_assistant.database import ReadOnlyDatabase, ensure_demo_database


class Catalog:
    async def models(self):
        return [{"name": "fixture:small"}]


class Model:
    async def plan(self, question, row_limit, repair=""):
        return QueryPlan(decision="query", sql="SELECT COUNT(*) AS orders FROM orders", reason="Fixture"), {}

    async def summarize(self, question, sql, result):
        return "Fixture summary of 12 orders", {}


@pytest.fixture
def api(tmp_path):
    path = tmp_path / "fictional.sqlite3"
    ensure_demo_database(path)
    app = create_app(ReadOnlyDatabase(path), lambda model: Model(), Catalog())
    with TestClient(app, base_url="http://localhost") as client:
        yield client


def test_natural_language_api_and_catalog(api):
    response = api.post("/api/ask", json={"question": "How many orders?", "model": "fixture:small"})
    assert response.status_code == 200
    assert response.json()["result"]["rows"] == [[12]]
    catalog = api.get("/api/catalog").json()
    assert catalog["read_only"] is True
    assert catalog["tables"] == [{"name": "customers", "row_count": 6}, {"name": "orders", "row_count": 12}]
    assert "Cedar Studio" not in catalog["schema"]


def test_direct_query_endpoint_uses_same_database_guard(api):
    response = api.post("/api/query", json={"sql": "DELETE FROM orders"})
    assert response.status_code == 403
    assert response.json()["detail"]["kind"] == "forbidden"
    assert api.post("/api/query", json={"sql": "SELECT COUNT(*) FROM orders"}).json()["rows"] == [[12]]


@pytest.mark.parametrize("payload", [
    {"question": " ", "model": "fixture:small"},
    {"question": "x" * 1201, "model": "fixture:small"},
    {"question": "How many?", "model": "fixture:small", "row_limit": 51},
    {"question": "How many?", "model": "fixture:small", "database": "private.sqlite3"},
    {"question": "How many?", "model": "missing"},
])
def test_invalid_request_is_rejected(api, payload):
    assert api.post("/api/ask", json=payload).status_code == 422


def test_browser_boundaries_and_actual_body_cap(api):
    assert api.get("/health", headers={"host": "evil.example"}).status_code == 400
    assert api.post("/api/query", headers={"origin": "https://evil.example"}, json={"sql": "SELECT 1"}).status_code == 403
    assert api.post("/api/query", content=b"x" * 16001).status_code == 413
    assert api.get("/").status_code == 200
    assert api.get("/static/app.js").status_code == 200


def test_model_failure_does_not_leave_generation_slot_locked(tmp_path):
    class FailingModel(Model):
        async def plan(self, *args):
            raise ModelError("Fixture unavailable")
    path = tmp_path / "fictional.sqlite3"
    ensure_demo_database(path)
    app = create_app(ReadOnlyDatabase(path), lambda model: FailingModel(), Catalog())
    with TestClient(app, base_url="http://localhost") as client:
        payload = {"question": "How many orders?", "model": "fixture:small"}
        assert client.post("/api/ask", json=payload).status_code == 503
        assert client.post("/api/ask", json=payload).status_code == 503
