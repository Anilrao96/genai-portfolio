import pytest
from fastapi.testclient import TestClient

from projects.p03_agentic_rag.app import create_app
from projects.p03_agentic_rag.index import RagIndex
from test_rag_assistant import FixtureModel
from test_rag_index import DOCS, FixtureEmbeddings


class Catalog:
    async def models(self):
        return [{"name": "fixture-chat", "capabilities": ["completion"]},
                {"name": "fixture-embedding", "capabilities": ["embedding"]}]


@pytest.fixture
def api(tmp_path):
    app = create_app(RagIndex(tmp_path / "library.sqlite3"), FixtureEmbeddings(), lambda model: FixtureModel(), Catalog())
    with TestClient(app, base_url="http://localhost") as client:
        yield client


def test_ingestion_is_persistent_idempotent_and_queryable(api):
    assert api.post("/api/documents", json=DOCS[0]).json()["added_documents"] == 1
    assert api.post("/api/documents", json=DOCS[0]).json()["unchanged_documents"] == 1
    assert api.get("/api/library").json()["document_count"] == 1
    assert api.get("/api/documents/returns-note").json()["text"] == DOCS[0]["text"]
    answer = api.post("/api/ask", json={"question": "What is the return window?", "model": "fixture-chat"})
    assert answer.status_code == 200
    assert answer.json()["status"] == "answered"
    assert answer.json()["citations"][0]["document_id"] == "returns-note"


def test_embedding_models_are_not_offered_as_chat_choices(api):
    assert [model["name"] for model in api.get("/api/models").json()["models"]] == ["fixture-chat"]
    assert api.post("/api/ask", json={"question": "A question", "model": "fixture-embedding"}).status_code == 422


@pytest.mark.parametrize("document", [
    {"id": "../outside", "title": "A source", "text": "x" * 50},
    {"id": "source", "title": "A source", "text": "short"},
    {"id": "source", "title": "A source", "text": "x" * 50, "path": "private.txt"},
])
def test_unsupported_source_inputs_are_rejected(api, document):
    assert api.post("/api/documents", json=document).status_code == 422
    assert api.get("/api/library").json()["document_count"] == 0


def test_conflicts_do_not_overwrite_the_source(api):
    api.post("/api/documents", json=DOCS[0])
    response = api.post("/api/documents", json={**DOCS[0], "text": "A conflicting replacement that must not change the existing source."})
    assert response.status_code == 409
    assert api.get("/api/documents/returns-note").json()["text"] == DOCS[0]["text"]


def test_local_http_boundaries_and_source_limits(api):
    assert api.get("/health", headers={"host": "evil.example"}).status_code == 400
    assert api.post("/api/library/demo", headers={"origin": "https://evil.example"}).status_code == 403
    assert api.post("/api/documents", content=b"x" * 64001).status_code == 413
    assert api.post("/api/ask", json={"question": "x" * 1201, "model": "fixture-chat"}).status_code == 422
    assert api.get("/").status_code == 200
    assert api.get("/static/app.js").status_code == 200
