"""Actual local-model HTTP cases plus negative calls over real MCP stdio."""
import argparse
import asyncio
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from projects.p01_mcp_agents.state import Store, runtime_path
from projects.p01_mcp_agents.team import Budget, connect_role


async def failures(path, run_id):
    store, budget = Store(path), Budget()
    before = store.get(run_id)
    checks = []
    async with connect_role("analyst", path, run_id, budget) as client:
        result = await client.client.call_tool("publish_review", {"expected_version": 2, "approved": True, "note": "role escalation probe"})
        checks.append({"case": "analyst_cannot_publish_review", "is_error": result.is_error,
                       "response": [c.text for c in result.content if hasattr(c, "text")]})
        result = await client.client.call_tool("publish_analysis", {"expected_version": 1, "recommended_plan": "team", "note": "stale replay probe"})
        checks.append({"case": "stale_handoff_rejected", "is_error": result.is_error,
                       "response": [c.text for c in result.content if hasattr(c, "text")]})
        try:
            await client.client.read_resource("council://runs/" + "0" * 32)
            denied = False
        except Exception:
            denied = True
        checks.append({"case": "other_run_resource_rejected", "is_error": denied})
    unchanged = store.get(run_id) == before
    assert unchanged and all(c["is_error"] for c in checks), checks
    return {"checks": checks, "state_unchanged": unchanged, "discovery": budget.trace}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8101")
    parser.add_argument("--model", default="qwen3:4b")
    parser.add_argument("--state-path", required=True, help="Dedicated fictional QA state under .runtime")
    args = parser.parse_args()
    state_path = runtime_path(args.state_path)
    cases = []
    with httpx.Client(base_url=args.base_url, timeout=260, trust_env=False) as client:
        assert client.get("/health").json()["protocol"] == "role-scoped-v1"
        for case_id, budget, expected in [("eligible_team", 30000, "team"), ("no_eligible_plan", 1000, None)]:
            response = client.post("/api/decide", json={"seats": 12, "budget_cents": budget, "support_24h": True,
                                   "goal": "Choose the least expensive eligible plan.", "model": args.model})
            response.raise_for_status()
            data = response.json()
            run = data.get("run") or {}
            passed = (not data["error"] and run.get("status") == "completed"
                      and run.get("analysis", {}).get("recommended_plan") == expected
                      and run.get("version") == 3
                      and data["counts"]["model_calls"] <= 4 and data["counts"]["tool_calls"] <= 12)
            passed = passed and all(not re.search(r"[\d$€£¥%]", run[k]["note"]) for k in ("research", "analysis", "review"))
            cases.append({"id": case_id, "expected_plan": expected, "passed": passed, "response": data})
            print(case_id, "PASS" if passed else "FAIL", data["duration_ms"], "ms", flush=True)
        # Read from another process connection, not the HTTP response, to demonstrate persistence.
        persisted = Store(state_path).get(cases[0]["response"]["run"]["id"])
        assert persisted == cases[0]["response"]["run"]
        failure_data = asyncio.run(failures(state_path, persisted["id"]))
    output = {"captured_at": datetime.now(timezone.utc).isoformat(), "mode": "actual local model + actual MCP stdio",
              "model": args.model, "inference": "CPU; LOCAL_AI_NUM_GPU=0", "cases": cases,
              "separate_connection_persistence": True, "protocol_failures": failure_data}
    (ROOT / "docs" / "mcp-live.json").write_text(json.dumps(output, indent=2), encoding="utf-8", newline="\n")
    assert all(case["passed"] for case in cases), "Inspect docs/mcp-live.json; failed runs were preserved."


if __name__ == "__main__":
    main()
