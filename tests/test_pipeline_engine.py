import asyncio
from pathlib import Path

import pytest

from portfolio_core.ollama import ModelServiceError
from projects.p05_self_healing_pipeline.contract import ALIASES, Proposal, parse_csv, signature
from projects.p05_self_healing_pipeline.engine import Pipeline
from projects.p05_self_healing_pipeline.store import Store, StoreError, runtime_path
from test_pipeline_contract import rules_for

DATA=Path(__file__).resolve().parents[1]/"projects/p05_self_healing_pipeline/data"


def sample(name):return (DATA/f"{name}.csv").read_text()


class Planner:
    def __init__(self,wrong=0,unavailable=False,hook=None):self.calls=0;self.wrong=wrong;self.unavailable=unavailable;self.hook=hook
    async def propose(self,context):
        self.calls+=1
        if self.hook:self.hook()
        if self.unavailable:raise ModelServiceError("Fixture model is unavailable.")
        rules=rules_for(context["headers"],context["source_date_style"])
        if self.wrong:
            rules[2]=rules[2].model_copy(update={"transform":"trim"});self.wrong-=1
        return Proposal(action="repair",rules=rules,note="Offline fixture extraction proposal; no inference."),{}


def run(store,planner,source,style="month_first",parent=None):
    return asyncio.run(Pipeline(store,planner).ingest(source,style,"fixture",parent))


def test_actual_sqlite_commit_learned_plan_and_idempotence(tmp_path):
    store=Store(tmp_path/"audit.sqlite3");planner=Planner()
    first=run(store,planner,sample("baseline"))
    assert first["status"]=="committed" and first["model_calls"]==0
    healed=run(store,planner,sample("drifted"))
    assert healed["status"]=="committed" and healed["model_calls"]==1 and healed["before"]["valid_rows"]==0 and healed["after"]["valid_rows"]==2
    snapshot=Store(store.path).snapshot()
    assert snapshot["totals"]=={"orders":4,"units":8,"revenue_cents":252485}
    replay=run(store,planner,sample("drifted"))
    assert replay["idempotent_replay"] and replay["model_calls_this_request"]==0 and planner.calls==1
    cached=run(Store(store.path),planner,sample("drifted").replace("ORD-200","ORD-400"))
    assert cached["plan_origin"]=="cached" and cached["model_calls"]==0
    assert cached["extractor_learned_from"]==healed["batch_id"]
    sig=signature(parse_csv(sample("drifted"))[0],"month_first")
    assert store.extractor(sig)["learned_from"]==healed["batch_id"]


def test_quarantine_is_atomic_and_corrected_replay_retains_original(tmp_path):
    store=Store(tmp_path/"audit.sqlite3");planner=Planner()
    run(store,planner,sample("baseline"))
    before=store.snapshot()
    bad=sample("drifted").replace("3.0","0.0")
    quarantined=run(store,planner,bad)
    assert quarantined["status"]=="quarantined" and quarantined["model_calls"]==2
    assert quarantined["after"]["valid_rows"]==1 and store.snapshot()==before
    original=store.batch(quarantined["batch_id"])
    fixed=run(store,planner,bad.replace(",0.0,",",3.0,"),parent=quarantined["batch_id"])
    assert fixed["status"]=="committed"
    assert store.batch(fixed["batch_id"])["replay_of"]==quarantined["batch_id"]
    assert store.batch(quarantined["batch_id"])["source_sha"]==original["source_sha"]
    assert store.batch(quarantined["batch_id"])["source"]==bad


def test_one_repair_retry_and_bounded_rejection(tmp_path):
    store=Store(tmp_path/"audit.sqlite3")
    result=run(store,Planner(wrong=1),sample("drifted"))
    assert result["status"]=="committed" and result["model_calls"]==2
    assert any(e["step"]=="reject_proposal" for e in result["trace"])


def test_rollback_preserves_snapshots_and_stale_changes_are_rejected(tmp_path):
    store=Store(tmp_path/"audit.sqlite3");planner=Planner()
    one=run(store,planner,sample("baseline"));two=run(store,planner,sample("drifted"))
    store.rollback(one["committed_revision"],two["committed_revision"])
    assert store.snapshot()["totals"]["orders"]==2 and len(store.snapshot()["revisions"])==3
    with pytest.raises(StoreError,match="changed"):store.rollback(0,two["committed_revision"])
    store.rollback(two["committed_revision"],one["committed_revision"])
    assert store.snapshot()["totals"]["orders"]==4
    assert store.history()["events"][0]["operation"]=="rollback"


def test_rollback_during_model_work_refuses_stale_commit(tmp_path):
    store=Store(tmp_path/"audit.sqlite3")
    first=run(store,Planner(),sample("baseline"))
    def rollback():store.rollback(0,first["committed_revision"])
    result=run(store,Planner(hook=rollback),sample("drifted"))
    assert result["status"]=="quarantined" and "changed" in result["error"]
    assert store.snapshot()["totals"]["orders"]==0


def test_source_boundaries_and_unavailable_model_preserve_state(tmp_path):
    store=Store(tmp_path/"audit.sqlite3")
    unknown=run(store,Planner(),sample("drifted").replace("Buyer","Unreviewed column"))
    assert unknown["status"]=="quarantined" and unknown["model_calls"]==0
    failed=run(store,Planner(unavailable=True),sample("drifted"))
    assert failed["status"]=="quarantined" and failed["model_calls"]==1 and "unavailable" in failed["error"]
    assert store.batch(failed["batch_id"])["source"]==sample("drifted") and store.snapshot()["active_revision"]==0
    with pytest.raises(ValueError):runtime_path("D:/elsewhere/audit.sqlite3")


def test_existing_order_ids_cannot_be_overwritten(tmp_path):
    store=Store(tmp_path/"audit.sqlite3")
    run(store,Planner(),sample("baseline"))
    result=run(store,Planner(),sample("baseline").replace("12.50","13.00"))
    assert result["status"]=="quarantined" and "overwriting" in result["error"]
    assert store.snapshot()["totals"]["revenue_cents"]==6500
