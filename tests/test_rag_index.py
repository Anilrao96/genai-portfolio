import asyncio
import hashlib

import pytest

from portfolio_core.ollama import ModelServiceError
from projects.p03_agentic_rag.index import IndexError, RagIndex, lexical_query, split_text

DOCS = [
    {"id": "returns-note", "title": "Returns policy", "text": "Unused products may be returned within 30 calendar days of delivery. A receipt is required for every return."},
    {"id": "shipping-note", "title": "Shipping guide", "text": "Standard shipping takes 3 to 5 business days after dispatch. Express shipping takes 1 to 2 business days."},
]


class FixtureEmbeddings:
    """Deterministic lexical feature fixture; not a real embedding model."""
    model = "fixture-embeddings-v1"

    def __init__(self):
        self.document_calls = 0
        self.query_calls = 0

    @staticmethod
    def vector(text):
        text = text.casefold()
        return [0.01 + text.count("return"), 0.01 + text.count("shipping"), 0.01 + text.count("incident")]

    async def embed_documents(self, texts):
        self.document_calls += 1
        return [self.vector(text) for text in texts]

    async def embed_query(self, query):
        self.query_calls += 1
        return self.vector(query)


@pytest.fixture
def seeded(tmp_path):
    index = RagIndex(tmp_path / "library.sqlite3")
    embedder = FixtureEmbeddings()
    asyncio.run(index.ingest(DOCS, embedder))
    return index, embedder


def test_real_index_persists_documents_vectors_and_full_text(seeded):
    index, embedder = seeded
    reopened = RagIndex(index.path)
    assert reopened.catalog()["document_count"] == 2
    assert reopened.catalog()["dimension"] == 3
    result = reopened.search("unused return products", embedder.vector("return"), embedder.model)
    assert result[0]["document_id"] == "returns-note"
    assert result[0]["lexical_rank"] == 1
    assert "30 calendar days" in result[0]["content"]
    assert reopened.document("returns-note")["text"] == DOCS[0]["text"]


def test_repeated_ingestion_is_idempotent_without_new_embeddings(seeded):
    index, embedder = seeded
    before = hashlib.sha256(index.path.read_bytes()).hexdigest()
    result = asyncio.run(index.ingest(DOCS, embedder))
    assert result == {"added_documents": 0, "added_chunks": 0, "unchanged_documents": 2}
    assert embedder.document_calls == 1
    assert hashlib.sha256(index.path.read_bytes()).hexdigest() == before


def test_duplicate_id_does_not_replace_an_existing_source(seeded):
    index, embedder = seeded
    with pytest.raises(IndexError) as error:
        asyncio.run(index.ingest([{**DOCS[0], "text": "A different source that must never replace the original document."}], embedder))
    assert error.value.kind == "conflict"
    assert index.document("returns-note")["text"] == DOCS[0]["text"]
    assert embedder.document_calls == 1


def test_failed_embeddings_leave_no_partial_index(tmp_path):
    class Unavailable(FixtureEmbeddings):
        async def embed_documents(self, texts):
            raise ModelServiceError("Fixture unavailable")
    index = RagIndex(tmp_path / "library.sqlite3")
    with pytest.raises(ModelServiceError):
        asyncio.run(index.ingest(DOCS, Unavailable()))
    assert index.catalog()["document_count"] == 0
    assert index.catalog()["chunk_count"] == 0
    assert index.catalog()["embedding_model"] is None


def test_model_and_dimension_changes_are_rejected(seeded):
    index, embedder = seeded
    with pytest.raises(IndexError) as error:
        index.search("returns", [1, 0], embedder.model)
    assert error.value.kind == "model"
    other = FixtureEmbeddings()
    other.model = "another-model"
    with pytest.raises(IndexError) as error:
        asyncio.run(index.ingest([{"id": "third-note", "title": "Third note", "text": "A third reference document with enough text for indexing."}], other))
    assert error.value.kind == "model"
    assert other.document_calls == 0


def test_fts_punctuation_is_data_and_cannot_execute_sql(seeded):
    index, embedder = seeded
    result = index.search('return" OR 1=1; DROP TABLE documents; --', embedder.vector("return"), embedder.model)
    assert result
    assert index.catalog()["document_count"] == 2
    assert '"' in lexical_query('return" OR 1=1; DROP TABLE documents; --')
    assert ";" not in lexical_query("DROP; SELECT")


def test_capacity_is_checked_before_embedding(seeded, monkeypatch):
    index, embedder = seeded
    monkeypatch.setattr("projects.p03_agentic_rag.index.MAX_DOCUMENTS", 2)
    with pytest.raises(IndexError) as error:
        asyncio.run(index.ingest([{"id": "third-note", "title": "Third note", "text": "Another document that exceeds this fixture's corpus capacity."}], embedder))
    assert error.value.kind == "capacity"
    assert embedder.document_calls == 1


def test_chunking_covers_long_text_with_bounded_overlap():
    text = "a" * 1000
    chunks = split_text(text, size=100, overlap=10)
    assert len(chunks) == 11
    assert all(0 < len(chunk) <= 100 for chunk in chunks)
    assert sum(len(chunk) for chunk in chunks) == 1100
    assert split_text("A first line.\r\nA second line.") == ["A first line.\nA second line."]


def test_missing_source_has_explicit_error(seeded):
    index, _ = seeded
    with pytest.raises(IndexError) as error:
        index.document("absent")
    assert error.value.kind == "missing"
