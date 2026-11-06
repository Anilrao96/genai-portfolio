import asyncio
import json
import math

import httpx
import pytest

from portfolio_core.ollama import ModelServiceError, OllamaClient
from projects.p03_agentic_rag.embeddings import LocalEmbeddings, unit_vector


def test_actual_embedding_contract_and_nomic_task_prefixes():
    inputs = []
    def handler(request):
        assert request.url.path == "/api/embed"
        payload = json.loads(request.content)
        assert payload["truncate"] is False
        assert payload["options"]["num_gpu"] == 0
        inputs.extend(payload["input"])
        return httpx.Response(200, json={"embeddings": [[3, 4] for _ in payload["input"]]})
    embedder = LocalEmbeddings(client=OllamaClient("http://localhost", httpx.MockTransport(handler)))
    async def scenario():
        vectors = await embedder.embed_documents(["A source", "Another source"])
        query = await embedder.embed_query("A question")
        return vectors, query
    vectors, query = asyncio.run(scenario())
    assert inputs == ["search_document: A source", "search_document: Another source", "search_query: A question"]
    assert vectors == [[0.6, 0.8], [0.6, 0.8]]
    assert math.isclose(sum(value * value for value in query), 1)


@pytest.mark.parametrize("vector", [[], [1], [0, 0], [True, 1], [float("nan"), 1], [float("inf"), 1], ["x", 1]])
def test_malformed_provider_vectors_are_rejected(vector):
    with pytest.raises(ModelServiceError):
        unit_vector(vector)


def test_wrong_batch_count_is_not_silently_indexed():
    client = OllamaClient("http://localhost", httpx.MockTransport(lambda request: httpx.Response(200, json={"embeddings": []})))
    with pytest.raises(ModelServiceError, match="wrong number"):
        asyncio.run(LocalEmbeddings(client=client).embed_documents(["One source"]))
