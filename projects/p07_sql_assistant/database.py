"""SQLite enforces read-only access independently of the generated SQL."""
import json
import math
import sqlite3
import time
from pathlib import Path

DATA = Path(__file__).parent / "data"
SCHEMA = (DATA / "schema.sql").read_text(encoding="utf-8")
COLUMNS = {
    "customers": {"id", "name", "region", "segment"},
    "orders": {"id", "customer_id", "ordered_at", "status", "total_cents"},
}
FUNCTIONS = {
    "abs", "avg", "coalesce", "count", "date", "dense_rank", "ifnull", "length",
    "lower", "max", "min", "nullif", "rank", "round", "row_number", "strftime",
    "substr", "substring", "sum", "total", "trim", "upper",
}


class QueryError(Exception):
    def __init__(self, kind: str, message: str):
        super().__init__(message)
        self.kind = kind


def ensure_demo_database(path: Path):
    """Seed our own fictional database once, without replacing existing data."""
    path = Path(path)
    if path.exists():
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    try:
        connection.executescript(SCHEMA + (DATA / "seed.sql").read_text(encoding="utf-8"))
        connection.commit()
    finally:
        connection.close()


class ReadOnlyDatabase:
    def __init__(self, path: Path, *, max_vm_steps=100000, timeout_seconds=0.5):
        self.path = Path(path).resolve()
        self.max_vm_steps = max_vm_steps
        self.timeout_seconds = timeout_seconds

    def execute(self, sql: str, row_limit: int = 50):
        if not isinstance(sql, str) or not sql.strip() or len(sql) > 6000:
            raise QueryError("invalid", "SQL must contain 1–6,000 characters.")
        if not isinstance(row_limit, int) or not 1 <= row_limit <= 50:
            raise QueryError("invalid", "Choose a row limit between 1 and 50.")
        started = time.perf_counter()
        try:
            connection = sqlite3.connect(self.path.as_uri() + "?mode=ro", uri=True, timeout=0.25)
        except sqlite3.Error as exc:
            raise QueryError("unavailable", "The fictional sample database is unavailable.") from exc
        denied = False
        exhausted = False
        steps = 0
        deadline = time.monotonic() + self.timeout_seconds

        def authorize(action, first, second, database, source):
            nonlocal denied
            if action == sqlite3.SQLITE_SELECT:
                return sqlite3.SQLITE_OK
            # SQLite reports a NULL database name for a column-free COUNT(*) read.
            # This connection has only main; ATTACH, temp writes and PRAGMA are denied.
            main_read = database == "main" or (database is None and second == "")
            if action == sqlite3.SQLITE_READ and main_read and first in COLUMNS:
                if second == "" or second in COLUMNS[first]:
                    return sqlite3.SQLITE_OK
            if action == sqlite3.SQLITE_FUNCTION and (second or "").lower() in FUNCTIONS:
                return sqlite3.SQLITE_OK
            denied = True
            return sqlite3.SQLITE_DENY

        def progress():
            nonlocal steps, exhausted
            steps += 1000
            exhausted = steps >= self.max_vm_steps or time.monotonic() >= deadline
            return int(exhausted)

        try:
            connection.execute("PRAGMA query_only=ON")
            connection.execute("PRAGMA trusted_schema=OFF")
            if hasattr(connection, "enable_load_extension"):
                connection.enable_load_extension(False)
            for category, limit in (
                (sqlite3.SQLITE_LIMIT_SQL_LENGTH, 8000), (sqlite3.SQLITE_LIMIT_LENGTH, 16384),
                (sqlite3.SQLITE_LIMIT_COLUMN, 16), (sqlite3.SQLITE_LIMIT_EXPR_DEPTH, 30),
                (sqlite3.SQLITE_LIMIT_COMPOUND_SELECT, 8), (sqlite3.SQLITE_LIMIT_ATTACHED, 0),
                (sqlite3.SQLITE_LIMIT_VDBE_OP, 50000),
            ):
                connection.setlimit(category, limit)
            connection.set_authorizer(authorize)
            connection.set_progress_handler(progress, 1000)
            cursor = connection.execute(sql)
            if cursor.description is None:
                raise QueryError("forbidden", "Only approved read-only result queries are allowed.")
            columns = [item[0][:120] for item in cursor.description]
            raw_rows = cursor.fetchmany(row_limit + 1)
            rows = []
            result_chars = 0
            cells_truncated = False
            truncated = len(raw_rows) > row_limit
            for raw in raw_rows[:row_limit]:
                row = []
                for value in raw:
                    if isinstance(value, bytes):
                        value = f"[binary value: {len(value)} bytes]"
                        cells_truncated = True
                    elif isinstance(value, float) and not math.isfinite(value):
                        value = str(value)
                    elif isinstance(value, str) and len(value) > 1000:
                        value = value[:1000] + "…"
                        cells_truncated = True
                    row.append(value)
                size = len(json.dumps(row, ensure_ascii=False, allow_nan=False))
                if result_chars + size > 12000:
                    truncated = True
                    break
                rows.append(row)
                result_chars += size
            return {"columns": columns, "rows": rows, "row_count": len(rows),
                    "truncated": truncated, "cell_values_truncated": cells_truncated,
                    "query_ms": round((time.perf_counter() - started) * 1000, 2)}
        except (sqlite3.Error, MemoryError) as exc:
            if denied:
                raise QueryError("forbidden", "Only approved read-only queries and functions are allowed.") from exc
            if exhausted or isinstance(exc, MemoryError):
                raise QueryError("budget", "Query exceeded its computation budget. Ask a narrower question.") from exc
            raise QueryError("invalid", str(exc)[:180]) from exc
        finally:
            connection.close()
