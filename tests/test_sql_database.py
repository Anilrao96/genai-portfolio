import hashlib
import sqlite3

import pytest

from projects.p07_sql_assistant.database import QueryError, ReadOnlyDatabase, ensure_demo_database


@pytest.fixture
def database(tmp_path):
    path = tmp_path / "fictional.sqlite3"
    ensure_demo_database(path)
    return ReadOnlyDatabase(path)


def fingerprint(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_aggregate_and_join_use_actual_fictional_rows(database):
    assert database.execute("SELECT COUNT(*) AS orders FROM orders")["rows"] == [[12]]
    result = database.execute("""SELECT c.region, SUM(o.total_cents)/100.0 AS revenue_usd
        FROM orders o JOIN customers c ON c.id=o.customer_id
        WHERE o.status='completed' GROUP BY c.region ORDER BY revenue_usd DESC""")
    assert result["rows"] == [["South", 510.0], ["North", 460.0], ["East", 390.0], ["West", 70.0]]
    assert result["columns"] == ["region", "revenue_usd"]


@pytest.mark.parametrize("sql", [
    "DELETE FROM orders", "UPDATE orders SET total_cents=0", "DROP TABLE orders",
    "INSERT INTO customers VALUES(99,'Injected','North','startup')",
    "CREATE TEMP TABLE leak(x)", "PRAGMA query_only=OFF", "PRAGMA database_list",
    "ATTACH DATABASE ':memory:' AS extra", "DETACH DATABASE main", "BEGIN",
    "SELECT load_extension('untrusted')", "SELECT randomblob(1000000000)",
    "SELECT sqlite_version()", "SELECT * FROM sqlite_schema",
    "SELECT * FROM pragma_table_info('orders')", "EXPLAIN DELETE FROM orders",
    "WITH RECURSIVE seq(n) AS (SELECT 1 UNION ALL SELECT n+1 FROM seq) SELECT n FROM seq",
])
def test_forbidden_operations_never_change_database(database, sql):
    before = fingerprint(database.path)
    with pytest.raises(QueryError) as error:
        database.execute(sql)
    assert error.value.kind == "forbidden"
    assert fingerprint(database.path) == before
    assert database.execute("SELECT COUNT(*) FROM orders")["rows"] == [[12]]


def test_multiple_statements_cannot_smuggle_a_write(database):
    before = fingerprint(database.path)
    with pytest.raises(QueryError, match="one statement"):
        database.execute("SELECT COUNT(*) FROM orders; DELETE FROM orders;")
    assert fingerprint(database.path) == before


def test_cross_join_is_interrupted_by_actual_vm_budget(database):
    constrained = ReadOnlyDatabase(database.path, max_vm_steps=2000)
    sql = "SELECT COUNT(*) FROM orders a, orders b, orders c, orders d, orders e, orders f"
    with pytest.raises(QueryError) as error:
        constrained.execute(sql)
    assert error.value.kind == "budget"


def test_row_cap_detects_partial_results(database):
    result = database.execute("SELECT id FROM orders ORDER BY id", row_limit=3)
    assert result["rows"] == [[1001], [1002], [1003]]
    assert result["row_count"] == 3
    assert result["truncated"] is True


def test_nonrecursive_cte_is_supported(database):
    assert database.execute("WITH n AS (SELECT COUNT(*) AS total FROM orders) SELECT total FROM n")["rows"] == [[12]]


def test_seeding_does_not_replace_existing_data(database):
    before = fingerprint(database.path)
    ensure_demo_database(database.path)
    assert fingerprint(database.path) == before


def test_invalid_column_is_a_repairable_error(database):
    with pytest.raises(QueryError) as error:
        database.execute("SELECT nonexistent_amount FROM orders")
    assert error.value.kind == "invalid"
    assert "no such column" in str(error.value)


def test_large_values_are_bounded_and_nonfinite_values_are_json_safe(database):
    assert database.execute("SELECT 1e999 AS value")["rows"] == [["inf"]]
    with pytest.raises(QueryError):
        database.execute("SELECT '" + "x" * 6000 + "'")


def test_missing_database_is_not_created(tmp_path):
    path = tmp_path / "missing.sqlite3"
    with pytest.raises(QueryError) as error:
        ReadOnlyDatabase(path).execute("SELECT 1")
    assert error.value.kind == "unavailable"
    assert not path.exists()


def test_long_cells_are_truncated_without_modifying_stored_data(database):
    with sqlite3.connect(database.path) as connection:
        connection.execute("UPDATE customers SET name=? WHERE id=1", ("x" * 3000,))
    before = fingerprint(database.path)
    result = database.execute("SELECT name FROM customers WHERE id=1")
    assert result["cell_values_truncated"] is True
    assert len(result["rows"][0][0]) == 1001
    assert fingerprint(database.path) == before


def test_result_payload_budget_can_stop_before_row_limit(database):
    import json
    with sqlite3.connect(database.path) as connection:
        connection.executemany("INSERT INTO customers VALUES(?,?,'North','startup')",
                               [(number, "x" * 1000) for number in range(100, 130)])
    result = database.execute("SELECT name FROM customers WHERE id>=100 ORDER BY id", row_limit=50)
    assert result["truncated"] is True
    assert result["row_count"] < 30
    assert sum(len(json.dumps(row, ensure_ascii=False)) for row in result["rows"]) <= 12000
