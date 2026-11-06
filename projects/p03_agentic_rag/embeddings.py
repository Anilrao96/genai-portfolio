import math
import os

from portfolio_core.ollama import ModelServiceError, OllamaClient


def unit_vector(values):
    if (not isinstance(values, list) or not 2 <= len(values) <= 4096
            or any(type(v) not in (int, float) or not math.isfinite(v) for v in values)):
        raise ModelServiceError("The embedding service returned an invalid vector.")
    norm = math.sqrt(sum(v * v for v in values))
    if not math.isfinite(norm) or norm < 1e-12:
        raise ModelServiceError("The embedding service returned an empty vector.")
    return [v / norm for v in values]


class LocalEmbeddings:
    def __init__(self, model=None, client=None):
        self.model = model or os.getenv("RAG_EMBED_MODEL", "nomic-embed-text:v1.5")
        self.client = client or OllamaClient(os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11435"))

    async def _embed(self, texts):
        result = await self.client._request("POST", "/api/embed", {
            "model": self.model, "input": texts, "truncate": False,
            "keep_alive": "5m", "options": {"num_gpu": 0},
        })
        vectors = result.get("embeddings")
        if not isinstance(vectors, list) or len(vectors) != len(texts):
            raise ModelServiceError("The embedding service returned the wrong number of vectors.")
        normalized = [unit_vector(vector) for vector in vectors]
        if len({len(vector) for vector in normalized}) != 1:
            raise ModelServiceError("Embedding dimensions are inconsistent.")
        return normalized

    async def embed_documents(self, texts):
        output = []
        for offset in range(0, len(texts), 16):
            output.extend(await self._embed(["search_document: " + text for text in texts[offset:offset + 16]]))
        return output

    async def embed_query(self, query):
        return (await self._embed(["search_query: " + query]))[0]
