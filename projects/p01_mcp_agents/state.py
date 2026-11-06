"""Trusted deterministic tools: fixed catalog, integer pricing and transactional handoffs."""
import hashlib
import json
import re
import sqlite3
import uuid
from contextlib import contextmanager
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

ROOT = Path(__file__).resolve().parents[2]
CATALOG = json.loads(Path(__file__).with_name("catalog.json").read_text(encoding="utf-8"))
CATALOG_SHA = hashlib.sha256(json.dumps(CATALOG, sort_keys=True).encode()).hexdigest()
PLAN_IDS = [p["id"] for p in CATALOG["plans"]]


class Requirements(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, str_strip_whitespace=True)
    seats: int = Field(ge=1, le=500)
    budget_cents: int = Field(ge=0, le=10_000_000)
    support_24h: bool
    goal: str = Field(default="Choose the least expensive eligible plan.", min_length=1, max_length=500)


def runtime_path(value: str | None = None) -> Path:
    path = Path(value) if value else ROOT / ".runtime" / "mcp-team" / "state.sqlite3"
    path = path.resolve()
    if not path.is_relative_to((ROOT / ".runtime").resolve()):
        raise ValueError("MCP state must be inside this portfolio's .runtime directory.")
    return path


def quote(plan_id: str, requirements: dict) -> dict:
    plan = next((p for p in CATALOG["plans"] if p["id"] == plan_id), None)
    if plan is None:
        raise ValueError("Unknown catalog plan.")
    total = plan["base_cents"] + requirements["seats"] * plan["seat_cents"]
    reasons = []
    if requirements["seats"] > plan["max_seats"]:
        reasons.append("seat_limit")
    if requirements["support_24h"] and not plan["support_24h"]:
        reasons.append("24h_support")
    if total > requirements["budget_cents"]:
        reasons.append("budget")
    return {"plan_id": plan_id, "monthly_cents": total, "monthly_usd": f"{total // 100}.{total % 100:02d}",
            "eligible": not reasons, "reasons": reasons}


def decision(requirements: dict) -> dict:
    quotes = [quote(p, requirements) for p in PLAN_IDS]
    eligible = sorted((q for q in quotes if q["eligible"]), key=lambda q: (q["monthly_cents"], q["plan_id"]))
    return {"quotes": quotes, "recommended_plan": eligible[0]["plan_id"] if eligible else None,
            "rule": "Least monthly cost among plans meeting every constraint; plan ID breaks ties."}


class Store:
    def __init__(self, path: Path):
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.execute("CREATE TABLE IF NOT EXISTS runs (id TEXT PRIMARY KEY, state TEXT NOT NULL)")
            db.execute("CREATE TABLE IF NOT EXISTS events (seq INTEGER PRIMARY KEY AUTOINCREMENT, run_id TEXT NOT NULL, role TEXT NOT NULL, operation TEXT NOT NULL, version INTEGER NOT NULL)")

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=5)
        try:
            with db:
                yield db
        finally:
            db.close()

    def create(self, requirements: dict) -> dict:
        req = Requirements.model_validate(requirements).model_dump()
        run = {"id": uuid.uuid4().hex, "version": 0, "status": "created", "requirements": req,
               "catalog_sha256": CATALOG_SHA, "research": None, "analysis": None, "review": None}
        with self.connect() as db:
            db.execute("INSERT INTO runs VALUES (?,?)", (run["id"], json.dumps(run)))
            db.execute("INSERT INTO events(run_id,role,operation,version) VALUES (?,?,?,?)",
                       (run["id"], "coordinator", "create_decision", 0))
        return run

    def get(self, run_id: str) -> dict:
        if not re.fullmatch(r"[0-9a-f]{32}", run_id):
            raise ValueError("Invalid run ID.")
        with self.connect() as db:
            row = db.execute("SELECT state FROM runs WHERE id=?", (run_id,)).fetchone()
        if not row:
            raise ValueError("Run not found.")
        return json.loads(row[0])

    def publish(self, run_id: str, role: str, expected_version: int, payload: dict) -> dict:
        stages = {"researcher": (0, "research", "researched"), "analyst": (1, "analysis", "analyzed"),
                  "reviewer": (2, "review", "completed" if payload.get("approved") else "needs_review")}
        if role not in stages:
            raise ValueError("This role cannot publish a handoff.")
        required, field, status = stages[role]
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT state FROM runs WHERE id=?", (run_id,)).fetchone()
            if not row:
                raise ValueError("Run not found.")
            run = json.loads(row[0])
            if type(expected_version) is not int or run["version"] != expected_version or expected_version != required:
                raise ValueError("Stale or out-of-order handoff; expected version does not match this stage.")
            if run["catalog_sha256"] != CATALOG_SHA:
                raise ValueError("Catalog changed. Start a new decision.")
            note = payload.get("note", "")
            if not isinstance(note, str) or not 1 <= len(note.strip()) <= 600:
                raise ValueError("A handoff note of 1–600 characters is required.")
            if payload.get("note_source", "model") not in {"model", "tool_fallback"}:
                raise ValueError("Unknown note source.")
            if role == "researcher":
                if sorted(payload.get("plan_ids", [])) != sorted(PLAN_IDS):
                    raise ValueError("Research must cover every catalog plan exactly once.")
            if role == "analyst":
                canonical = decision(run["requirements"])
                if payload.get("recommended_plan") != canonical["recommended_plan"]:
                    raise ValueError("Recommendation violates the independently computed selection rule.")
                payload = {**payload, **canonical}
            if role == "reviewer" and type(payload.get("approved")) is not bool:
                raise ValueError("Review approval must be boolean.")
            run.update({field: payload, "version": required + 1, "status": status})
            db.execute("UPDATE runs SET state=? WHERE id=?", (json.dumps(run), run_id))
            db.execute("INSERT INTO events(run_id,role,operation,version) VALUES (?,?,?,?)",
                       (run_id, role, "publish_" + field, run["version"]))
        return run

    def verify(self, run_id: str) -> dict:
        run = self.get(run_id)
        canonical = decision(run["requirements"])
        valid = (run["version"] >= 2 and run["catalog_sha256"] == CATALOG_SHA
                 and all(run["analysis"].get(k) == v for k, v in canonical.items()))
        return {"valid": valid, **canonical, "version": run["version"]}

    def history(self) -> list[dict]:
        with self.connect() as db:
            return [json.loads(row[0]) for row in db.execute("SELECT state FROM runs ORDER BY rowid DESC LIMIT 20")]

    def events(self, run_id: str) -> list[dict]:
        with self.connect() as db:
            return [dict(zip(("seq", "role", "operation", "version"), row)) for row in
                    db.execute("SELECT seq,role,operation,version FROM events WHERE run_id=? ORDER BY seq", (run_id,))]
