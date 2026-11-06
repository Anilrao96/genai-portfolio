"""Live RAG verification against a separate, fictional-only QA library."""
import argparse
import json
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "docs/rag-live.json"
PICKUP = {"id": "pickup-hours", "title": "Fictional pickup depot hours",
          "text": "In this fictional Northstar pickup depot, collection is available on Saturdays from 10:00 to 14:00 UTC. Customers must show a pickup code before receiving a parcel. This note describes demonstration opening hours only."}
ALLOWED = {document["id"] for document in json.loads((ROOT / "projects/p03_agentic_rag/data/demo.json").read_text())["documents"]} | {PICKUP["id"]}


def checked_sources(response):
    for event in response.get("trace", []):
        if event["tool"] == "retrieve":
            if any(chunk["document_id"] not in ALLOWED for chunk in event["result"]["chunks"]):
                raise ValueError("Unexpected sources in QA capture. Use a separate fictional-only QA index.")
    for citation in response.get("citations", []):
        if citation["document_id"] not in ALLOWED:
            raise ValueError("Unexpected citation source in QA capture.")


def supported(response, document_id, numbers=()):
    citations = response.get("citations", [])
    return (response.get("status") == "answered" and citations
            and document_id in {citation["document_id"] for citation in citations}
            and all(" ".join(citation["quote"].split()) in " ".join(citation["content"].split()) for citation in citations)
            and all(re.search(r"\b" + str(number) + r"\b", response["answer"]) for number in numbers))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default="qwen3:4b")
    args = parser.parse_args()
    evidence = {"verified_at": datetime.now(timezone.utc).isoformat(), "kind": "live_local_agentic_rag",
                "model": args.model, "inference_mode": "cpu", "cases": []}
    cases = [
        ("returns", "How long do customers have to return unused products?", "", lambda response: supported(response, "returns-policy", (30,))),
        ("shipping", "How long does standard delivery take after dispatch?", "", lambda response: supported(response, "shipping-guide", (3, 5))),
        ("outside-library", "What discount do platinum members receive?", "", lambda response: response.get("status") == "abstained" and not response.get("citations")),
        ("recovery", "How long do customers have to return unused products?", "severity-one paging incident timeline",
         lambda response: supported(response, "returns-policy", (30,)) and response.get("recovery_used") is True and response.get("retrieval_attempts") == 2),
        ("new-document", "When can a customer collect a parcel on Saturday, and what must they show?", "",
         lambda response: supported(response, "pickup-hours", (10, 14)) and "code" in response["answer"].casefold()),
    ]
    with httpx.Client(base_url="http://127.0.0.1:8103", timeout=260, trust_env=False) as client:
        if client.get("/health").raise_for_status().json().get("retrieval_protocol") != "source-alias-v2":
            raise ValueError("Restart the RAG service before verifying its current protocol.")
        catalog = client.get("/api/library").raise_for_status().json()
        if any(document["id"] not in ALLOWED for document in catalog["documents"]):
            raise ValueError("QA library contains unrelated sources; no capture was written.")
        evidence["seed"] = client.post("/api/library/demo").raise_for_status().json()
        evidence["new_document_ingestion"] = client.post("/api/documents", json=PICKUP).raise_for_status().json()
        evidence["catalog"] = client.get("/api/library").raise_for_status().json()
        evidence["idempotent_seed"] = client.post("/api/library/demo").raise_for_status().json()
        for case_id, question, initial_query, check in cases:
            started = time.perf_counter()
            response = client.post("/api/ask", json={"question": question, "initial_query": initial_query, "model": args.model})
            body = response.json()
            checked_sources(body)
            passed = bool(response.status_code == 200 and check(body))
            evidence["cases"].append({"id": case_id, "question": question, "initial_query": initial_query,
                "passed": passed, "http_status": response.status_code,
                "wall_ms": round((time.perf_counter() - started) * 1000, 1), "response": body})
            OUTPUT.write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")
            print(f"{case_id}: {'PASS' if passed else 'FAIL'} ({evidence['cases'][-1]['wall_ms']} ms)", flush=True)
        final = client.get("/api/library").raise_for_status().json()
        evidence["library_unchanged_by_questions"] = final == evidence["catalog"]
    evidence["passed"] = all(case["passed"] for case in evidence["cases"]) and evidence["library_unchanged_by_questions"] and evidence["idempotent_seed"]["added_documents"] == 0
    OUTPUT.write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"passed": evidence["passed"], "case_count": len(cases), "documents": evidence["catalog"]["document_count"]}), flush=True)
    return 0 if evidence["passed"] else 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (httpx.HTTPError, ValueError) as error:
        print(f"Live RAG probe failed: {type(error).__name__}. No unrelated source content was printed.", file=sys.stderr)
        sys.exit(2)
