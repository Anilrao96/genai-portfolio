"""Reuse the existing Agent Eval Lab to score captured real SQL app outcomes.

This replays recorded responses, makes no new model calls and does not benchmark latency.
"""
import argparse
import asyncio
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.dont_write_bytecode = True  # Keep the separate evaluation repository unchanged.


async def main(args):
    lab = args.eval_lab_root.resolve()
    if not (lab / "agent_eval" / "models.py").is_file():
        raise ValueError("Clone Agent Eval Lab and provide its directory with --eval-lab-root.")
    sys.path.insert(0, str(lab))
    from agent_eval.dataset import load_dataset
    from agent_eval.models import Prediction, ToolEvent
    from agent_eval.report import write_artifacts
    from agent_eval.runner import RunConfig, run_suite

    source = args.capture.read_bytes()
    evidence = json.loads(source)
    records = {case["question"]: case["response"] for case in evidence["cases"]}
    if len(records) != len(evidence["cases"]):
        raise ValueError("Capture contains duplicate questions.")

    class RecordedSqlAdapter:
        name = "recorded-sql-live-trace-replay-v1"

        async def predict(self, item):
            response = records[item.prompt]
            trace = [ToolEvent(name=event["tool"], arguments=event["input"], output=event.get("result"),
                               error=json.dumps(event["error"]) if event.get("error") else None)
                     for event in response.get("trace", [])]
            answer = json.dumps({"status": response.get("status"),
                                 "rows": (response.get("result") or {}).get("rows", [])})
            usage = response.get("usage") or {}
            return Prediction(answer=answer, trace=trace, input_tokens=usage.get("input_tokens"),
                              output_tokens=usage.get("output_tokens"), cost_usd=None)

    cases, fingerprint = load_dataset(ROOT / "projects/p07_sql_assistant/data/eval_cases.jsonl")
    run = await run_suite(cases, fingerprint, RecordedSqlAdapter(), RunConfig(concurrency=1, timeout_s=5),
                          provenance={"mode": "recorded_live_trace_replay", "model": evidence["model"],
                                      "capture_sha256": hashlib.sha256(source).hexdigest(),
                                      "fresh_model_calls": False,
                                      "latency_note": "Replay overhead only; actual model timings are in the source capture.",
                                      "evaluates": "Structured SQL results and actual tool paths; not summary faithfulness or broad model quality."})
    write_artifacts(run, args.out)
    report = args.out / "report.html"
    rendered = report.read_text(encoding="utf-8")
    rendered = rendered.replace("LIVE ADAPTER —", "RECORDED LIVE TRACE REPLAY — No new model calls. Timings below are replay overhead, not inference latency.")
    rendered = rendered.replace("P95 LATENCY", "P95 REPLAY OVERHEAD").replace("Wall time including retry backoff", "Not a model performance measurement")
    report.write_text(rendered, encoding="utf-8")
    summary = run["summary"]
    print(json.dumps({"mode": "recorded_live_trace_replay", "passed": summary["passed"],
                      "count": summary["count"], "errors": summary["errors"]}))
    return 0 if summary["passed"] == summary["count"] and summary["errors"] == 0 else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--eval-lab-root", type=Path, default=ROOT.parent / "agent-eval-lab")
    parser.add_argument("--capture", type=Path, default=ROOT / "docs/sql-assistant-live.json")
    parser.add_argument("--out", type=Path, default=ROOT / "docs/sql-assistant-eval")
    arguments = parser.parse_args()
    try:
        sys.exit(asyncio.run(main(arguments)))
    except (ValueError, KeyError, OSError) as error:
        print(f"Evaluation setup failed: {type(error).__name__}", file=sys.stderr)
        sys.exit(2)
