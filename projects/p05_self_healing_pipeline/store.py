"""Immutable batch sources and snapshots, with atomic promotion and pointer rollback."""
import hashlib
import json
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


class StoreError(ValueError):
    pass


def runtime_path(value=None):
    path = Path(value) if value else ROOT / ".runtime" / "pipeline" / "audit.sqlite3"
    path = path.resolve()
    if not path.is_relative_to((ROOT / ".runtime").resolve()):
        raise ValueError("Pipeline state must stay inside this portfolio's .runtime directory.")
    return path


def totals(records):
    return {"orders": len(records), "units": sum(r["quantity"] for r in records),
            "revenue_cents": sum(r["quantity"] * r["unit_price_cents"] for r in records)}


class Store:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS batches(id TEXT PRIMARY KEY, input_key TEXT UNIQUE NOT NULL,
                    source TEXT NOT NULL, source_sha TEXT NOT NULL, date_style TEXT NOT NULL,
                    replay_of TEXT, created_at TEXT NOT NULL, base_revision INTEGER NOT NULL, result TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS revisions(id INTEGER PRIMARY KEY AUTOINCREMENT,
                    batch_id TEXT UNIQUE NOT NULL, records TEXT NOT NULL, created_at TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS active(singleton INTEGER PRIMARY KEY CHECK(singleton=1), revision INTEGER NOT NULL);
                INSERT OR IGNORE INTO active VALUES(1,0);
                CREATE TABLE IF NOT EXISTS extractors(signature TEXT PRIMARY KEY, plan TEXT NOT NULL, learned_from TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS events(seq INTEGER PRIMARY KEY AUTOINCREMENT, batch_id TEXT,
                    operation TEXT NOT NULL, detail TEXT NOT NULL, created_at TEXT NOT NULL);
            """)

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=5)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    @staticmethod
    def now():
        return datetime.now(timezone.utc).isoformat()

    @staticmethod
    def _records(db, revision):
        if revision == 0:
            return []
        row = db.execute("SELECT records FROM revisions WHERE id=?", (revision,)).fetchone()
        if not row:
            raise StoreError("Snapshot revision not found.")
        return json.loads(row[0])

    def register(self, source, date_style, model, replay_of=None):
        sha = hashlib.sha256(source.encode("utf-8")).hexdigest()
        key = hashlib.sha256(json.dumps([sha, date_style, replay_of]).encode()).hexdigest()
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT id FROM batches WHERE input_key=?", (key,)).fetchone()
            if row:
                return self._batch(db, row[0]), True
            if db.execute("SELECT COUNT(*) FROM batches").fetchone()[0] >= 500:
                raise StoreError("This local MVP is limited to five hundred saved batches.")
            if replay_of:
                parent = self._batch(db, replay_of)
                if parent["result"]["status"] != "quarantined":
                    raise StoreError("Only a quarantined batch can be replayed with corrected source.")
            revision = db.execute("SELECT revision FROM active WHERE singleton=1").fetchone()[0]
            batch_id = uuid.uuid4().hex
            result = {"batch_id": batch_id, "status": "processing", "model": model, "trace": [], "model_calls": 0}
            db.execute("INSERT INTO batches VALUES(?,?,?,?,?,?,?,?,?)",
                       (batch_id, key, source, sha, date_style, replay_of, self.now(), revision, json.dumps(result)))
            db.execute("INSERT INTO events(batch_id,operation,detail,created_at) VALUES(?,?,?,?)",
                       (batch_id, "replay_received" if replay_of else "received", json.dumps({"source_sha256": sha, "replay_of": replay_of}), self.now()))
            return self._batch(db, batch_id), False

    @staticmethod
    def _batch(db, batch_id):
        row = db.execute("SELECT * FROM batches WHERE id=?", (batch_id,)).fetchone()
        if not row:
            raise StoreError("Batch not found.")
        result = dict(row)
        result["result"] = json.loads(result["result"])
        return result

    def batch(self, batch_id):
        with self.connect() as db:
            batch = self._batch(db, batch_id)
            batch["events"] = [dict(row) for row in db.execute("SELECT seq,operation,detail,created_at FROM events WHERE batch_id=? ORDER BY seq", (batch_id,))]
            for event in batch["events"]:
                event["detail"] = json.loads(event["detail"])
            return batch

    def extractor(self, sig):
        with self.connect() as db:
            row = db.execute("SELECT plan,learned_from FROM extractors WHERE signature=?", (sig,)).fetchone()
            return {"rules": json.loads(row[0]), "learned_from": row[1]} if row else None

    def finish(self, batch_id, result, records=None, rules=None, sig=None):
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            batch = self._batch(db, batch_id)
            if batch["result"]["status"] != "processing":
                raise StoreError("This immutable batch has already finished.")
            active = db.execute("SELECT revision FROM active WHERE singleton=1").fetchone()[0]
            snapshot = self._records(db, active)
            if records is not None:
                if batch["base_revision"] != active:
                    raise StoreError("Active snapshot changed while the repair was prepared; replay against the new state.")
                existing = {r["order_id"] for r in snapshot}
                if existing.intersection(r["order_id"] for r in records):
                    raise StoreError("An order ID already exists in the active snapshot; overwriting is forbidden.")
                if len(snapshot) + len(records) > 1000:
                    raise StoreError("Active snapshot is limited to one thousand orders.")
                snapshot = sorted(snapshot + records, key=lambda r: r["order_id"])
                cursor = db.execute("INSERT INTO revisions(batch_id,records,created_at) VALUES(?,?,?)", (batch_id, json.dumps(snapshot), self.now()))
                active = cursor.lastrowid
                db.execute("UPDATE active SET revision=? WHERE singleton=1", (active,))
                if result["plan_origin"] != "cached":
                    db.execute("INSERT INTO extractors VALUES(?,?,?) ON CONFLICT(signature) DO UPDATE SET plan=excluded.plan,learned_from=excluded.learned_from",
                               (sig, json.dumps(rules), batch_id))
                result["committed_revision"] = active
            result.update({"active_revision_at_finish": active, "snapshot_totals_at_finish": totals(snapshot)})
            db.execute("UPDATE batches SET result=? WHERE id=?", (json.dumps(result), batch_id))
            for event in result["trace"]:
                db.execute("INSERT INTO events(batch_id,operation,detail,created_at) VALUES(?,?,?,?)",
                           (batch_id, event["step"], json.dumps(event), self.now()))
            db.execute("INSERT INTO events(batch_id,operation,detail,created_at) VALUES(?,?,?,?)",
                       (batch_id, result["status"], json.dumps({"active_revision": active}), self.now()))
        return result

    def snapshot(self):
        with self.connect() as db:
            active = db.execute("SELECT revision FROM active WHERE singleton=1").fetchone()[0]
            records = self._records(db, active)
            revisions = [{"revision": 0, "batch_id": None, "orders": 0}]
            for row in db.execute("SELECT id,batch_id,records FROM revisions ORDER BY id DESC LIMIT 30"):
                revisions.append({"revision": row[0], "batch_id": row[1], "orders": len(json.loads(row[2]))})
            return {"active_revision": active, "records": records, "totals": totals(records), "revisions": revisions}

    def rollback(self, target, expected):
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            active = db.execute("SELECT revision FROM active WHERE singleton=1").fetchone()[0]
            if active != expected:
                raise StoreError("Active revision changed. Refresh before selecting a snapshot.")
            records = self._records(db, target)
            db.execute("UPDATE active SET revision=? WHERE singleton=1", (target,))
            db.execute("INSERT INTO events(batch_id,operation,detail,created_at) VALUES(NULL,?,?,?)",
                       ("rollback", json.dumps({"from_revision": active, "to_revision": target}), self.now()))
            return {"active_revision": target, "totals": totals(records), "preserved_all_snapshots": True}

    def history(self):
        with self.connect() as db:
            batches = []
            for row in db.execute("SELECT id,source_sha,replay_of,created_at,result FROM batches ORDER BY rowid DESC LIMIT 30"):
                r = json.loads(row[4])
                batches.append({"id": row[0], "source_sha256": row[1], "replay_of": row[2], "created_at": row[3],
                                "status": r["status"], "model_calls": r["model_calls"], "plan_origin": r.get("plan_origin"),
                                "committed_revision": r.get("committed_revision")})
            events = [dict(row) for row in db.execute("SELECT seq,batch_id,operation,detail,created_at FROM events ORDER BY seq DESC LIMIT 100")]
            for event in events:
                event["detail"] = json.loads(event["detail"])
            return {"batches": batches, "events": events}
