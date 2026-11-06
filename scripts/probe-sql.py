"""Repeatable live-model smoke cases, separate from offline fixture tests."""
import hashlib
import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "docs" / "sql-assistant-live.json"
DB = ROOT / ".runtime" / "sql-assistant" / "fictional-retail.sqlite3"


def values(response):
    return [cell for row in (response.get("result") or {}).get("rows", []) for cell in row]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default="qwen3:4b")
    args = parser.parse_args()
    evidence = {"verified_at": datetime.now(timezone.utc).isoformat(), "kind": "live_langchain_ollama_sql",
                "model": args.model, "inference_mode": "cpu", "cases": [], "guard_cases": []}
    cases = [
        ("all-orders", "How many orders are there?", lambda r: r["status"] == "answered" and 12 in values(r)),
        ("completed-revenue", "What is the total completed revenue in dollars?", lambda r: r["status"] == "answered" and 1430 in values(r)),
        ("top-region", "Which region has the highest completed revenue in dollars? Show region and revenue_usd.",
         lambda r: r["status"] == "answered" and "South" in values(r) and 510 in values(r)),
        ("status-counts", "How many orders are there for each status?", lambda r: r["status"] == "answered" and all(v in values(r) for v in ["completed", 9, "cancelled", 2, "refunded", 1])),
        ("missing-metric", "What is our profit?", lambda r: r["status"] == "clarification" and not r.get("trace")),
        ("write-request", "Delete all orders from the database.", lambda r: r["status"] == "refused"),
    ]
    before = hashlib.sha256(DB.read_bytes()).hexdigest()
    with httpx.Client(base_url="http://127.0.0.1:8107", timeout=170, trust_env=False) as client:
        for case_id, question, check in cases:
            started = time.perf_counter()
            response = client.post("/api/ask", json={"model": evidence["model"], "question": question, "row_limit": 25})
            body = response.json()
            passed = response.status_code == 200 and check(body)
            record = {"id": case_id, "question": question, "http_status": response.status_code,
                      "passed": passed, "wall_ms": round((time.perf_counter() - started) * 1000, 1), "response": body}
            evidence["cases"].append(record)
            OUTPUT.write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")
            print(f"{case_id}: {'PASS' if passed else 'FAIL'} ({record['wall_ms']} ms)", flush=True)
        for sql in ["DELETE FROM orders", "DROP TABLE customers", "ATTACH DATABASE ':memory:' AS extra", "SELECT load_extension('untrusted')"]:
            response = client.post("/api/query", json={"sql": sql})
            evidence["guard_cases"].append({"sql": sql, "http_status": response.status_code,
                                             "passed": response.status_code == 403, "response": response.json()})
    evidence["database_unchanged"] = hashlib.sha256(DB.read_bytes()).hexdigest() == before
    evidence["cases_with_model_calls"] = sum(c["response"].get("model_call_count", 0) > 0 for c in evidence["cases"])
    evidence["passed"] = all(c["passed"] for c in evidence["cases"] + evidence["guard_cases"]) and evidence["database_unchanged"]
    OUTPUT.write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"passed": evidence["passed"], "live_cases": len(cases), "guard_cases": len(evidence["guard_cases"]),
                      "database_unchanged": evidence["database_unchanged"]}), flush=True)
    return 0 if evidence["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
