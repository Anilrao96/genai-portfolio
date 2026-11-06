import asyncio

import pytest
from pydantic import ValidationError

from projects.p07_sql_assistant.assistant import ModelError, QueryPlan, SqlAssistant
from projects.p07_sql_assistant.database import ReadOnlyDatabase, ensure_demo_database


class FixtureModel:
    """Scripted transport fixture, not a live model or a quality benchmark."""
    def __init__(self, plans, *, summary_fails=False):
        self.plans = list(plans)
        self.repairs = []
        self.summaries = []
        self.summary_fails = summary_fails

    async def plan(self, question, row_limit, repair=""):
        self.repairs.append(repair)
        return self.plans.pop(0), {"input_tokens": 10, "output_tokens": 5}

    async def summarize(self, question, sql, result):
        self.summaries.append(result)
        if self.summary_fails:
            raise ModelError("Fixture summary failed")
        return f"Fixture result: {result['rows']}", {"input_tokens": 12, "output_tokens": 6}


@pytest.fixture
def database(tmp_path):
    path = tmp_path / "fictional.sqlite3"
    ensure_demo_database(path)
    return ReadOnlyDatabase(path)


def plan(sql):
    return QueryPlan(decision="query", sql=sql, reason="Fixture plan")


def test_answer_uses_actual_result_and_records_actual_tool_call(database):
    model = FixtureModel([plan("SELECT COUNT(*) AS orders FROM orders")])
    result = asyncio.run(SqlAssistant(database, model).ask("How many orders?"))
    assert result["status"] == "answered"
    assert result["result"]["rows"] == [[12]]
    assert model.summaries[0]["rows"] == [[12]]
    assert result["trace"][0]["result"]["rows"] == [[12]]
    assert result["usage"] == {"input_tokens": 22, "output_tokens": 11}


def test_invalid_sql_has_one_bounded_repair(database):
    model = FixtureModel([plan("SELECT missing FROM orders"), plan("SELECT COUNT(*) FROM orders")])
    result = asyncio.run(SqlAssistant(database, model).ask("How many orders?"))
    assert result["status"] == "answered"
    assert len(result["trace"]) == 2
    assert result["trace"][0]["error"]["kind"] == "invalid"
    assert "no such column" in model.repairs[1]


def test_repeated_invalid_sql_does_not_loop(database):
    model = FixtureModel([plan("SELECT missing FROM orders"), plan("SELECT absent FROM orders")])
    result = asyncio.run(SqlAssistant(database, model).ask("An unclear metric"))
    assert result["status"] == "failed"
    assert len(result["trace"]) == 2
    assert not model.summaries


def test_model_generated_write_is_rejected_without_repair(database):
    model = FixtureModel([plan("DELETE FROM orders")])
    # A compromised model returns a write even for an ordinary read request.
    result = asyncio.run(SqlAssistant(database, model).ask("Show all orders"))
    assert result["status"] == "refused"
    assert result["trace"][0]["error"]["kind"] == "forbidden"
    assert len(model.repairs) == 1
    assert not model.summaries
    assert database.execute("SELECT COUNT(*) FROM orders")["rows"] == [[12]]


@pytest.mark.parametrize("decision,status", [("clarify", "clarification"), ("refuse", "refused")])
def test_nonquery_decisions_execute_nothing(database, decision, status):
    model = FixtureModel([QueryPlan(decision=decision, sql="", reason="A fixture explanation")])
    result = asyncio.run(SqlAssistant(database, model).ask("A question"))
    assert result["status"] == status
    assert result["trace"] == []
    assert result["result"] is None
    assert not model.summaries


def test_failed_summary_preserves_rows_and_marks_usage_unknown(database):
    model = FixtureModel([plan("SELECT COUNT(*) FROM orders")], summary_fails=True)
    result = asyncio.run(SqlAssistant(database, model).ask("How many orders?"))
    assert result["result"]["rows"] == [[12]]
    assert result["summary_source"] == "result_count_fallback"
    assert result["usage"]["input_tokens"] is None


@pytest.mark.parametrize("question,status", [("Delete all orders", "refused"), ("What is our profit?", "clarification"), ("Show average margin", "clarification")])
def test_known_unsupported_or_mutating_requests_do_not_call_model(database, question, status):
    model = FixtureModel([])
    result = asyncio.run(SqlAssistant(database, model).ask(question))
    assert result["status"] == status
    assert result["model_call_count"] == 0
    assert result["summary_source"] == "dataset_policy"
    assert model.repairs == []


@pytest.mark.parametrize("decision,sql", [("query", ""), ("refuse", "DELETE FROM orders"), ("clarify", "SELECT 1")])
def test_structured_decision_cannot_disagree_with_sql(decision, sql):
    with pytest.raises(ValidationError):
        QueryPlan(decision=decision, sql=sql, reason="Fixture")
