"""Replay captured MCP selection/path contracts through the existing Agent Eval Lab."""
import argparse
import asyncio
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.dont_write_bytecode = True


async def main(args):
    lab = args.eval_lab_root.resolve()
    if not (lab / "agent_eval/models.py").is_file():
        raise ValueError("Provide the existing Agent Eval Lab checkout.")
    sys.path.insert(0, str(lab))
    from agent_eval.dataset import load_dataset
    from agent_eval.models import Prediction, ToolEvent
    from agent_eval.report import write_artifacts
    from agent_eval.runner import RunConfig, run_suite

    source = args.capture.read_bytes()
    evidence = json.loads(source)
    records = {case["id"]: case["response"] for case in evidence["cases"]}
    if len(records) != len(evidence["cases"]):
        raise ValueError("Duplicate capture case IDs.")

    class RecordedCouncil:
        name = "recorded-mcp-live-trace-replay-v1"

        async def predict(self, item):
            response = records[item.prompt]
            run = response["run"]
            answer = json.dumps({"status": run["status"], "recommended_plan": run["analysis"]["recommended_plan"],
                                 "version": run["version"], "approved": run["review"]["approved"]})
            trace = [ToolEvent(name=e["name"], arguments=e["arguments"], output=e.get("result"), error=e.get("error"))
                     for e in response["trace"] if e["kind"] == "tool"]
            model_usage = [e["usage"] for e in response["trace"] if e["kind"] == "model"]
            return Prediction(answer=answer, trace=trace,
                              input_tokens=sum(u.get("input_tokens") or 0 for u in model_usage),
                              output_tokens=sum(u.get("output_tokens") or 0 for u in model_usage), cost_usd=None)

    cases, fingerprint = load_dataset(ROOT / "projects/p01_mcp_agents/eval_cases.jsonl")
    run = await run_suite(cases, fingerprint, RecordedCouncil(), RunConfig(concurrency=1, timeout_s=5),
        provenance={"mode": "recorded_live_trace_replay", "model": evidence["model"],
                    "capture_sha256": hashlib.sha256(source).hexdigest(), "fresh_model_calls": False,
                    "latency_note": "Replay overhead only; actual CPU/MCP timing is in the capture.",
                    "evaluates": "Selection, state and ordered actual MCP tools; not semantic accuracy of model notes."})
    write_artifacts(run, args.out)
    report = args.out / "report.html"
    text = report.read_text(encoding="utf-8").replace("LIVE ADAPTER —", "RECORDED LIVE TRACE REPLAY — No new model calls; timing below is replay overhead.")
    text = text.replace("P95 LATENCY", "P95 REPLAY OVERHEAD").replace("Wall time including retry backoff", "Not an inference performance measurement")
    report.write_text(text, encoding="utf-8")
    summary = run["summary"]
    print(json.dumps({"mode": "recorded_live_trace_replay", "passed": summary["passed"], "count": summary["count"], "errors": summary["errors"]}))
    return 0 if summary["passed"] == summary["count"] and not summary["errors"] else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--eval-lab-root", type=Path, default=ROOT.parent / "agent-eval-lab")
    parser.add_argument("--capture", type=Path, default=ROOT / "docs/mcp-live.json")
    parser.add_argument("--out", type=Path, default=ROOT / "docs/mcp-eval")
    args = parser.parse_args()
    try:
        sys.exit(asyncio.run(main(args)))
    except (ValueError, KeyError, OSError) as error:
        print(f"Evaluation setup failed: {type(error).__name__}", file=sys.stderr)
        sys.exit(2)
