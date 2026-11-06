"""A bounded, persistent hybrid index; all SQL is application-owned and parameterized."""
import asyncio
import hashlib
import json
import re
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

from .embeddings import unit_vector

MAX_DOCUMENTS = 40
MAX_CHUNKS = 300
STOPWORDS = set("a an and are as at be by can do does for from had has have how i in is it its may of on or our should that the their there these this to was we what when where which who why will with would you your".split())


class IndexError(Exception):
    def __init__(self, kind, message):
        super().__init__(message)
        self.kind = kind


def split_text(text, size=1000, overlap=120):
    text = text.replace("\r\n", "\n").replace("\r", "\n").strip()
    if not 20 <= size or not 0 <= overlap < size // 2:
        raise ValueError("Invalid chunking configuration.")
    chunks, start = [], 0
    while start < len(text):
        end = min(start + size, len(text))
        if end < len(text):
            boundary = text.rfind(" ", start + size // 2, end)
            if boundary > start:
                end = boundary
        content = text[start:end].strip()
        if content:
            chunks.append(content)
        if end == len(text):
            break
        start = max(start + 1, end - overlap)
    return chunks


def lexical_query(query):
    tokens = list(dict.fromkeys(word.casefold() for word in re.findall(r"[^\W_]{2,32}", query)))
    tokens = [word for word in tokens if word not in STOPWORDS][:12]
    return " OR ".join('"' + word + '"' for word in tokens)


class RagIndex:
    def __init__(self, path):
        self.path = Path(path).resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with closing(self._connect()) as connection, connection:
            connection.executescript("""
                CREATE TABLE IF NOT EXISTS metadata(key TEXT PRIMARY KEY, value TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS documents(
                    id TEXT PRIMARY KEY, title TEXT NOT NULL, text TEXT NOT NULL,
                    sha256 TEXT NOT NULL, created_at TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS chunks(
                    id TEXT PRIMARY KEY, document_id TEXT NOT NULL REFERENCES documents(id),
                    ordinal INTEGER NOT NULL, content TEXT NOT NULL, vector TEXT NOT NULL);
                CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(
                    chunk_id UNINDEXED, content, tokenize='unicode61');
            """)

    def _connect(self):
        connection = sqlite3.connect(self.path, timeout=2)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        return connection

    def catalog(self):
        with closing(self._connect()) as connection:
            metadata = dict(connection.execute("SELECT key,value FROM metadata").fetchall())
            documents = [dict(row) for row in connection.execute("""SELECT d.id,d.title,d.sha256,d.created_at,
                COUNT(c.id) AS chunks FROM documents d LEFT JOIN chunks c ON c.document_id=d.id
                GROUP BY d.id ORDER BY d.title""")]
        return {"documents": documents, "document_count": len(documents),
                "chunk_count": sum(doc["chunks"] for doc in documents),
                "embedding_model": metadata.get("embedding_model"),
                "dimension": int(metadata["dimension"]) if metadata.get("dimension") else None,
                "max_documents": MAX_DOCUMENTS, "max_chunks": MAX_CHUNKS}

    def document(self, document_id):
        with closing(self._connect()) as connection:
            row = connection.execute("SELECT id,title,text,sha256 FROM documents WHERE id=?", (document_id,)).fetchone()
        if row is None:
            raise IndexError("missing", "That document is not in this library.")
        return dict(row)

    async def ingest(self, documents, embedder):
        pending = []
        seen = set()
        for doc in documents:
            document_id, title, text = doc["id"], doc["title"].strip(), doc["text"].replace("\r\n", "\n").replace("\r", "\n").strip()
            if (not re.fullmatch(r"[a-z0-9][a-z0-9_-]{2,39}", document_id) or not 3 <= len(title) <= 100
                    or not 40 <= len(text) <= 12000 or document_id in seen):
                raise IndexError("invalid", "Check the unique document ID, title and text limits.")
            seen.add(document_id)
            digest = hashlib.sha256(text.encode()).hexdigest()
            try:
                old = self.document(document_id)
            except IndexError:
                old = None
            if old:
                if old["sha256"] == digest and old["title"] == title:
                    continue
                raise IndexError("conflict", "That document ID already exists. Choose a new ID; existing sources are preserved.")
            pieces = split_text(text)
            pending.append({"id": document_id, "title": title, "text": text, "sha256": digest, "pieces": pieces})
        if not pending:
            return {"added_documents": 0, "added_chunks": 0, "unchanged_documents": len(documents)}
        current = self.catalog()
        count = sum(len(doc["pieces"]) for doc in pending)
        if current["document_count"] + len(pending) > MAX_DOCUMENTS or current["chunk_count"] + count > MAX_CHUNKS:
            raise IndexError("capacity", "The demo library reached its document or chunk limit.")
        if current["embedding_model"] and current["embedding_model"] != embedder.model:
            raise IndexError("model", "This index uses a different embedding model. Use its original model or a new index.")
        inputs = [doc["title"] + "\n" + chunk for doc in pending for chunk in doc["pieces"]]
        vectors = await embedder.embed_documents(inputs)
        if len(vectors) != count:
            raise IndexError("vectors", "The embedding count does not match the chunks.")
        vectors = [unit_vector(vector) for vector in vectors]
        dimension = len(vectors[0])
        if any(len(vector) != dimension for vector in vectors) or (current["dimension"] and current["dimension"] != dimension):
            raise IndexError("vectors", "The embedding dimension does not match the index.")

        def save():
            try:
                with closing(self._connect()) as connection, connection:
                    connection.execute("BEGIN IMMEDIATE")
                    meta = dict(connection.execute("SELECT key,value FROM metadata").fetchall())
                    if meta and (meta.get("embedding_model") != embedder.model or int(meta["dimension"]) != dimension):
                        raise IndexError("model", "The index embedding configuration changed during ingestion.")
                    document_count = connection.execute("SELECT COUNT(*) FROM documents").fetchone()[0]
                    chunk_count = connection.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]
                    if document_count + len(pending) > MAX_DOCUMENTS or chunk_count + count > MAX_CHUNKS:
                        raise IndexError("capacity", "The library capacity changed during ingestion.")
                    position = 0
                    for doc in pending:
                        connection.execute("INSERT INTO documents VALUES(?,?,?,?,?)", (
                            doc["id"], doc["title"], doc["text"], doc["sha256"], datetime.now(timezone.utc).isoformat()))
                        for ordinal, content in enumerate(doc["pieces"], 1):
                            chunk_id = f"{doc['id']}-{doc['sha256'][:8]}-{ordinal}"
                            connection.execute("INSERT INTO chunks VALUES(?,?,?,?,?)", (
                                chunk_id, doc["id"], ordinal, content, json.dumps(vectors[position], separators=(",", ":"))))
                            connection.execute("INSERT INTO chunks_fts(chunk_id,content) VALUES(?,?)", (chunk_id, doc["title"] + "\n" + content))
                            position += 1
                    connection.execute("INSERT OR REPLACE INTO metadata VALUES('embedding_model',?)", (embedder.model,))
                    connection.execute("INSERT OR REPLACE INTO metadata VALUES('dimension',?)", (str(dimension),))
            except sqlite3.IntegrityError as exc:
                raise IndexError("conflict", "A source with that ID was added concurrently. Existing sources were preserved.") from exc
        await asyncio.to_thread(save)
        return {"added_documents": len(pending), "added_chunks": count, "unchanged_documents": len(documents) - len(pending)}

    def search(self, query, vector, model, k=2):
        if not 1 <= k <= 4 or not isinstance(query, str) or not 1 <= len(query) <= 1200:
            raise IndexError("invalid", "Search query or result limit is invalid.")
        query_vector = unit_vector(vector)
        with closing(self._connect()) as connection:
            meta = dict(connection.execute("SELECT key,value FROM metadata").fetchall())
            if not meta:
                return []
            if meta["embedding_model"] != model or int(meta["dimension"]) != len(query_vector):
                raise IndexError("model", "Search embedding configuration does not match the index.")
            rows = connection.execute("""SELECT c.id,c.document_id,c.content,c.vector,d.title
                FROM chunks c JOIN documents d ON d.id=c.document_id""").fetchall()
            query_text = lexical_query(query)
            lexical = connection.execute("SELECT chunk_id FROM chunks_fts WHERE chunks_fts MATCH ? ORDER BY rank LIMIT 24", (query_text,)).fetchall() if query_text else []
        candidates = {}
        for row in rows:
            stored = json.loads(row["vector"])
            if len(stored) != len(query_vector):
                raise IndexError("vectors", "Stored vector dimensions are inconsistent.")
            similarity = sum(left * right for left, right in zip(query_vector, stored))
            candidates[row["id"]] = {key: row[key] for key in ("id", "document_id", "content", "title")}
            candidates[row["id"]].update(vector_similarity=round(similarity, 6), score=0.0, lexical_rank=None)
        dense = sorted(candidates.values(), key=lambda item: (-item["vector_similarity"], item["id"]))[:24]
        for rank, item in enumerate(dense, 1):
            item["score"] += 1 / (60 + rank)
        for rank, row in enumerate(lexical, 1):
            item = candidates[row["chunk_id"]]
            item["lexical_rank"] = rank
            item["score"] += 1 / (60 + rank)
        ranked = sorted(candidates.values(), key=lambda item: (-item["score"], item["id"]))[:k]
        return [{**item, "score": round(item["score"], 7)} for item in ranked]
