import asyncio

import pytest
from pydantic import ValidationError

from projects.p03_agentic_rag.assistant import AnswerDraft, Assessment, Claim, RagAssistant
from projects.p03_agentic_rag.index import RagIndex
from test_rag_index import DOCS, FixtureEmbeddings


class FixtureModel:
    """Scripted decisions exercise orchestration; these are not live model results."""
    def __init__(self, decisions=None, invalid_quote=False, unknown_id=False, inline_citation=False):
        self.decisions = list(decisions or [(True, "")])
        self.invalid_quote = invalid_quote
        self.unknown_id = unknown_id
        self.inline_citation = inline_citation
        self.grade_calls = 0
        self.answer_calls = 0

    async def grade(self, question, query, chunks):
        self.grade_calls += 1
        sufficient, rewrite = self.decisions.pop(0)
        return Assessment(sufficient=sufficient, relevant_chunk_ids=[chunks[0]["id"]] if sufficient else [],
                          rewritten_query=rewrite, reason="Fixture assessment"), {"input_tokens": 10, "output_tokens": 5}

    async def answer(self, question, chunks):
        self.answer_calls += 1
        source = chunks[0]
        quote = "An invented passage that is not in the source." if self.invalid_quote else source["content"].split(". ")[0] + "."
        text = "A fixture answer [invented-citation]." if self.inline_citation else "A fixture answer supported by a passage."
        return AnswerDraft(abstain=False, reason="Fixture answer", claims=[Claim(text=text,
            chunk_id="invented-source" if self.unknown_id else source["id"], quote=quote)]), {"input_tokens": 12, "output_tokens": 7}


@pytest.fixture
def state(tmp_path):
    index = RagIndex(tmp_path / "library.sqlite3")
    embedder = FixtureEmbeddings()
    asyncio.run(index.ingest(DOCS, embedder))
    return index, embedder


def test_supported_answer_has_only_actual_retrieved_source_ids_and_quotes(state):
    index, embedder = state
    result = asyncio.run(RagAssistant(index, embedder, FixtureModel()).ask("What is the return window?"))
    assert result["status"] == "answered"
    assert result["retrieval_attempts"] == 1
    assert result["model_call_count"] == 2
    assert result["usage"] == {"input_tokens": 22, "output_tokens": 12}
    citation = result["citations"][0]
    assert citation["quote"] in citation["content"]
    assert f"[{citation['chunk_id']}]" in result["answer"]


def test_weak_initial_retrieval_can_be_rewritten_once(state):
    index, embedder = state
    model = FixtureModel([(False, "return window"), (True, "")])
    result = asyncio.run(RagAssistant(index, embedder, model).ask("What is the return window?", "incident paging"))
    assert result["status"] == "answered"
    assert result["recovery_used"] is True
    assert result["retrieval_attempts"] == 2
    assert result["model_call_count"] == 3
    assert [event["input"]["query"] for event in result["trace"] if event["tool"] == "retrieve"] == ["incident paging", "return window"]


def test_two_insufficient_searches_abstain_without_answer_generation(state):
    index, embedder = state
    model = FixtureModel([(False, "unsupported discount"), (False, "try indefinitely")])
    result = asyncio.run(RagAssistant(index, embedder, model).ask("What is the member discount?"))
    assert result["status"] == "abstained"
    assert result["retrieval_attempts"] == 2
    assert model.answer_calls == 0
    assert result["citations"] == []


def test_repeated_query_does_not_create_a_retry_loop(state):
    index, embedder = state
    model = FixtureModel([(False, "same question")])
    result = asyncio.run(RagAssistant(index, embedder, model).ask("same question"))
    assert result["retrieval_attempts"] == 1
    assert result["status"] == "abstained"


@pytest.mark.parametrize("kwargs", [{"invalid_quote": True}, {"unknown_id": True}, {"inline_citation": True}])
def test_unverified_citations_fail_closed(state, kwargs):
    index, embedder = state
    result = asyncio.run(RagAssistant(index, embedder, FixtureModel(**kwargs)).ask("What is the return window?"))
    assert result["status"] == "abstained"
    assert result["citations"] == []
    assert result["trace"][-1]["result"]["valid"] is False


def test_empty_library_does_not_call_embedding_or_answer_models(tmp_path):
    index = RagIndex(tmp_path / "empty.sqlite3")
    embedder, model = FixtureEmbeddings(), FixtureModel()
    result = asyncio.run(RagAssistant(index, embedder, model).ask("A question"))
    assert result["status"] == "abstained"
    assert embedder.query_calls == model.grade_calls == model.answer_calls == 0


def test_grade_cannot_select_a_source_that_was_not_retrieved(state):
    class InvalidGrade(FixtureModel):
        async def grade(self, question, query, chunks):
            return Assessment(sufficient=True, relevant_chunk_ids=["not-retrieved"], rewritten_query="",
                              reason="Invalid fixture ID"), {}
    index, embedder = state
    model = InvalidGrade()
    result = asyncio.run(RagAssistant(index, embedder, model).ask("Return window"))
    assert result["status"] == "abstained"
    assert model.answer_calls == 0


def test_invalid_decision_contracts_are_rejected():
    with pytest.raises(ValidationError):
        AnswerDraft(abstain=False, reason="Missing claims", claims=[])


def test_mistyped_numeric_literal_uses_the_verified_quote_instead(tmp_path):
    class MistypedTime(FixtureModel):
        async def answer(self, question, chunks):
            return AnswerDraft(abstain=False, reason="Fixture with a mistyped time", claims=[Claim(
                text="Collection is available from 10:00 to 14:0:00 UTC.", chunk_id=chunks[0]["id"],
                quote="Collection is available from 10:00 to 14:00 UTC.")]), {}
    index = RagIndex(tmp_path / "library.sqlite3")
    embedder = FixtureEmbeddings()
    asyncio.run(index.ingest([{"id": "collection-note", "title": "Collection hours",
        "text": "Collection is available from 10:00 to 14:00 UTC. A collection code is required."}], embedder))
    result = asyncio.run(RagAssistant(index, embedder, MistypedTime()).ask("Collection hours?"))
    assert result["status"] == "answered"
    assert result["answer_mode"] == "source_quote_fallback"
    assert "14:0:00" not in result["answer"]
    assert "14:00" in result["answer"]
    assert result["trace"][-1]["result"]["numeric_quote_fallbacks"] == 1
