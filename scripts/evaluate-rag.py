"""Score captured RAG outcomes with the existing Agent Eval Lab; no fresh inference."""
import argparse
import asyncio
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.dont_write_bytecode = True


def request_key(case):
    return case["question"] + "\nInitial search query: " + (case.get("initial_query") or "<use question>")


async def main(args):
    lab = args.eval_lab_root.resolve()
    if not (lab / "agent_eval/models.py").is_file():
        raise ValueError("Provide the existing Agent Eval Lab checkout with --eval-lab-root.")
    sys.path.insert(0, str(lab))
    from agent_eval.dataset import load_dataset
    from agent_eval.models import Prediction, ToolEvent
    from agent_eval.report import write_artifacts
    from agent_eval.runner import RunConfig, run_suite

    source = args.capture.read_bytes()
    evidence = json.loads(source)
    records = {request_key(case): case["response"] for case in evidence["cases"]}
    if len(records) != len(evidence["cases"]):
        raise ValueError("Duplicate input envelopes in capture.")

    class RecordedRagAdapter:
        name = "recorded-rag-live-trace-replay-v1"

        async def predict(self, item):
            response = records[item.prompt]
            answer = json.dumps({"status": response.get("status"),
                                 "sources": sorted({source["document_id"] for source in response.get("citations", [])}),
                                 "recovery_used": response.get("recovery_used", False), "answer": response.get("answer", "")})
            trace = [ToolEvent(name=event["tool"], arguments=event["input"], output=event.get("result"))
                     for event in response.get("trace", [])]
            usage = response.get("usage") or {}
            return Prediction(answer=answer, trace=trace, input_tokens=usage.get("input_tokens"),
                              output_tokens=usage.get("output_tokens"), cost_usd=None)

    cases, fingerprint = load_dataset(ROOT / "projects/p03_agentic_rag/data/eval_cases.jsonl")
    run = await run_suite(cases, fingerprint, RecordedRagAdapter(), RunConfig(concurrency=1, timeout_s=5),
        provenance={"mode": "recorded_live_trace_replay", "model": evidence["model"],
                    "capture_sha256": hashlib.sha256(source).hexdigest(), "fresh_model_calls": False,
                    "latency_note": "Replay overhead only; see capture for actual inference timings.",
                    "evaluates": "Outcome/source contracts and actual retrieval/grade/validation paths, not semantic entailment."})
    write_artifacts(run, args.out)
    report = args.out / "report.html"
    rendered = report.read_text(encoding="utf-8").replace("LIVE ADAPTER —", "RECORDED LIVE TRACE REPLAY — No new model calls. Timings below are replay overhead, not inference latency.")
    rendered = rendered.replace("P95 LATENCY", "P95 REPLAY OVERHEAD").replace("Wall time including retry backoff", "Not a model performance measurement")
    report.write_text(rendered, encoding="utf-8")
    summary = run["summary"]
    print(json.dumps({"mode": "recorded_live_trace_replay", "passed": summary["passed"], "count": summary["count"], "errors": summary["errors"]}))
    return 0 if summary["passed"] == summary["count"] and summary["errors"] == 0 else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--eval-lab-root", type=Path, default=ROOT.parent / "agent-eval-lab")
    parser.add_argument("--capture", type=Path, default=ROOT / "docs/rag-live.json")
    parser.add_argument("--out", type=Path, default=ROOT / "docs/rag-eval")
    args = parser.parse_args()
    try:
        sys.exit(asyncio.run(main(args)))
    except (ValueError, KeyError, OSError) as error:
        print(f"Evaluation setup failed: {type(error).__name__}", file=sys.stderr)
        sys.exit(2)
