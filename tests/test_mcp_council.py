import asyncio
import json

import pytest

from projects.p01_mcp_agents.state import PLAN_IDS, Requirements, Store, decision, runtime_path
from projects.p01_mcp_agents.team import Budget, Council, CouncilError, connect_role, handoff


def requirements(**overrides):
    return Requirements(seats=12, budget_cents=30000, support_24h=True, **overrides)


def test_quotes_and_no_fit():
    answer = decision(requirements().model_dump())
    assert answer["recommended_plan"] == "team"
    assert [q["monthly_cents"] for q in answer["quotes"]] == [14400, 23600, 31400]
    assert answer["quotes"][0]["reasons"] == ["24h_support"]
    assert decision(Requirements(seats=12, budget_cents=100, support_24h=True).model_dump())["recommended_plan"] is None
    assert decision(Requirements(seats=30, budget_cents=100000, support_24h=False).model_dump())["quotes"][0]["reasons"] == ["seat_limit"]


@pytest.mark.parametrize("bad", [{"seats": True}, {"seats": 0}, {"budget_cents": 1.2}, {"support_24h": "true"}, {"other": 1}, {"goal": "x" * 501}])
def test_requirements_are_strict(bad):
    with pytest.raises(ValueError):
        Requirements.model_validate({"seats": 12, "budget_cents": 30000, "support_24h": True, **bad})


def test_runtime_path_is_scoped():
    with pytest.raises(ValueError):
        runtime_path("D:/outside/state.sqlite3")


def test_state_rejects_incomplete_research_stale_and_wrong_choice(tmp_path):
    store = Store(tmp_path / "state.sqlite3")
    run = store.create(requirements().model_dump())
    with pytest.raises(ValueError, match="every catalog"):
        store.publish(run["id"], "researcher", 0, {"plan_ids": ["basic"], "note": "incomplete"})
    assert store.get(run["id"])["version"] == 0
    store.publish(run["id"], "researcher", 0, {"plan_ids": PLAN_IDS, "note": "all covered"})
    with pytest.raises(ValueError, match="Stale"):
        store.publish(run["id"], "researcher", 0, {"plan_ids": PLAN_IDS, "note": "replay"})
    with pytest.raises(ValueError, match="selection rule"):
        store.publish(run["id"], "analyst", 1, {"recommended_plan": "basic", "note": "cheap but ineligible"})
    assert Store(store.path).get(run["id"])["version"] == 1
    assert len(store.events(run["id"])) == 2


class FixtureRoles:
    def __init__(self, wrong=0, approve=True, failure=False):
        self.wrong, self.approve, self.failure = wrong, approve, failure

    async def act(self, role, context):
        if self.failure:
            raise RuntimeError("fixture provider failed")
        output = {"note": "Offline fixture role; no inference."}
        if role == "analyst":
            output["recommended_plan"] = "basic" if self.wrong else decision(context["state"]["requirements"])["recommended_plan"]
            self.wrong = max(0, self.wrong - 1)
        if role == "reviewer":
            output["approved"] = self.approve
        return output, {}


def test_actual_stdio_protocol_and_role_denials(tmp_path):
    async def scenario():
        store = Store(tmp_path / "state.sqlite3")
        budget = Budget()
        async with connect_role("coordinator", store.path, None, budget) as client:
            run = await client.call("create_decision", **requirements().model_dump())
        async with connect_role("researcher", store.path, run["id"], budget) as client:
            state = await client.read(run["id"])
            assert state["version"] == 0
            assert len((await client.call("list_plans"))["plans"]) == 3
            denied = await client.client.call_tool("publish_review", {"expected_version": 0, "approved": True, "note": "bad"})
            assert denied.is_error
            with pytest.raises(Exception):
                await client.client.read_resource("council://runs/" + "0" * 32)
            await client.call("publish_research", expected_version=0, plan_ids=PLAN_IDS, note="covered")
            with pytest.raises(CouncilError, match="Stale"):
                await client.call("publish_research", expected_version=0, plan_ids=PLAN_IDS, note="replayed")
        assert Store(store.path).get(run["id"])["version"] == 1
        discoveries = [t for t in budget.trace if t["kind"] == "discovery"]
        assert all(t["protocol_version"] for t in discoveries)
        assert "council://runs/{run_id}" in discoveries[1]["resource_templates"]
    asyncio.run(scenario())


@pytest.mark.parametrize("wrong,approve,status,models", [(0, True, "completed", 3), (1, True, "completed", 4), (0, False, "needs_review", 3), (2, True, "researched", 3)])
def test_fixture_roles_use_actual_mcp_and_bounded_handoffs(tmp_path, wrong, approve, status, models):
    store = Store(tmp_path / "state.sqlite3")
    result = asyncio.run(Council(store, FixtureRoles(wrong, approve)).run(requirements()))
    assert result["run"]["status"] == status, result
    assert result["counts"]["model_calls"] == models
    assert result["counts"]["tool_calls"] <= 12
    assert (result["error"] is None) == (wrong < 2)
    expected_versions = [0, 1, 2] if wrong < 2 else [0, 1]
    assert [t["version"] for t in result["trace"] if t["kind"] == "resource"] == expected_versions
    saved = json.loads((store.path.parent / "traces" / (result["run"]["id"] + ".json")).read_text())
    assert saved["counts"] == result["counts"]
    assert store.get(result["run"]["id"])["status"] == status


def test_model_failure_preserves_unfinished_run(tmp_path):
    store = Store(tmp_path / "state.sqlite3")
    result = asyncio.run(Council(store, FixtureRoles(failure=True)).run(requirements()))
    assert result["error"] and result["run"]["status"] == "created"
    assert result["counts"]["model_calls"] == 1


@pytest.mark.parametrize("kind,limit", [("tool", 12), ("model", 4), ("resource", 3)])
def test_budget_rejects_extra_step(kind, limit):
    budget = Budget()
    for _ in range(limit):
        budget.take(kind)
    with pytest.raises(CouncilError, match="exhausted"):
        budget.take(kind)


@pytest.mark.parametrize("role,output,context", [
    ("researcher", {"note": "Team costs $1800 per seat."}, {}),
    ("analyst", {"note": "Budget is $30k.", "recommended_plan": "team"}, {"quotes": decision(requirements().model_dump())["quotes"]}),
    ("reviewer", {"note": "24h requirement passed.", "approved": True}, {"verification": {"valid": True}}),
])
def test_numeric_model_notes_are_labeled_tool_fallback(role, output, context):
    result = handoff(role, output, context)
    assert result["note_source"] == "tool_fallback"
    assert result["note"] != output["note"]
    assert all(not char.isdigit() for char in result["note"])
    if "recommended_plan" in output:
        assert result["recommended_plan"] == output["recommended_plan"]


def test_qualitative_note_stays_model_authored():
    assert handoff("researcher", {"note": "Basic lacks around-the-clock support."}, {})["note_source"] == "model"
