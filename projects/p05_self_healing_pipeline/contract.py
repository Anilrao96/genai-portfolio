"""Finite extraction language. Model output is data, never executable code."""
import csv
import hashlib
import io
import json
import re
from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

ALIASES = {
    "order_id": ["order_id", "Order Number", "order_ref"],
    "customer": ["customer", "Buyer", "customer_name"],
    "quantity": ["quantity", "Units", "qty"],
    "unit_price": ["unit_price", "Price USD", "price_usd"],
    "currency": ["currency", "Currency", "currency_code"],
    "ordered_on": ["ordered_on", "Order Date", "order_date"],
}
TRANSFORMS = {"order_id": ["trim"], "customer": ["trim"], "quantity": ["integer", "integral_decimal"],
              "unit_price": ["decimal_usd", "currency_usd"], "currency": ["usd", "uppercase_usd"],
              "ordered_on": ["iso_date", "year_slash_date", "us_date"]}
BASE = {"order_id": "trim", "customer": "trim", "quantity": "integer", "unit_price": "decimal_usd",
        "currency": "usd", "ordered_on": "iso_date"}
POLICY_VERSION = "orders-v1"


class Rule(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    source: str = Field(min_length=1, max_length=60)
    target: Literal["order_id", "customer", "quantity", "unit_price", "currency", "ordered_on"]
    transform: Literal["trim", "integer", "integral_decimal", "decimal_usd", "currency_usd", "usd", "uppercase_usd", "iso_date", "year_slash_date", "us_date"]


class Proposal(BaseModel):
    model_config = ConfigDict(extra="forbid")
    action: Literal["repair", "abstain"]
    rules: list[Rule] = Field(max_length=6)
    note: str = Field(min_length=1, max_length=400)


class InputError(ValueError):
    pass


def parse_csv(text: str) -> tuple[list[str], list[dict]]:
    if not text or len(text.encode("utf-8")) > 32000 or "\x00" in text:
        raise InputError("CSV must contain 1–32,000 UTF-8 bytes without null characters.")
    try:
        rows = list(csv.reader(io.StringIO(text.lstrip("\ufeff"), newline=""), strict=True))
    except csv.Error as exc:
        raise InputError("Malformed CSV quoting.") from exc
    if not 2 <= len(rows) <= 201:
        raise InputError("CSV needs a header and 1–200 data rows; blank rows are not silently discarded.")
    headers = rows[0]
    if not 1 <= len(headers) <= 10 or any(not h or len(h) > 60 for h in headers) or len(set(headers)) != len(headers):
        raise InputError("Headers must be nonempty, unique, at most sixty characters, with at most ten columns.")
    if any(len(row) != len(headers) for row in rows[1:]):
        raise InputError("Every row must have exactly the header's number of cells.")
    if any(len(cell) > 200 for row in rows[1:] for cell in row):
        raise InputError("Cells are limited to two hundred characters.")
    return headers, [dict(zip(headers, row)) for row in rows[1:]]


def signature(headers: list[str], date_style: str) -> str:
    return hashlib.sha256(json.dumps([POLICY_VERSION, headers, date_style], separators=(",", ":")).encode()).hexdigest()


def baseline(headers: list[str]) -> list[Rule] | None:
    return [Rule(source=k, target=k, transform=BASE[k]) for k in ALIASES] if set(headers) == set(ALIASES) else None


def validate_plan(rules: list[Rule], headers: list[str], date_style: str) -> None:
    if len(rules) != 6 or sorted(r.source for r in rules) != sorted(headers) or {r.target for r in rules} != set(ALIASES):
        raise InputError("Plan must map every source column and every contract field exactly once; dropping columns is forbidden.")
    for rule in rules:
        if rule.source not in ALIASES[rule.target]:
            raise InputError(f"Source alias is not approved for {rule.target}.")
        if rule.transform not in TRANSFORMS[rule.target]:
            raise InputError(f"Transformation is not allowed for {rule.target}.")
        if rule.transform == "us_date" and date_style != "month_first":
            raise InputError("Month-first date repair requires the declared month-first source profile.")
        if rule.transform == "year_slash_date" and date_style != "year_first":
            raise InputError("Year-first date repair requires the declared year-first source profile.")


def _value(raw: str, transform: str):
    text = raw.strip()
    if transform == "trim":
        return text
    if transform in {"integer", "integral_decimal"}:
        pattern = r"\d{1,5}" if transform == "integer" else r"\d{1,5}(?:\.0{1,2})?"
        if not re.fullmatch(pattern, text, flags=re.ASCII):
            raise InputError("Expected a whole quantity without rounding.")
        return int(Decimal(text))
    if transform in {"decimal_usd", "currency_usd"}:
        pattern = r"\d{1,6}(?:\.\d{1,2})?"
        if transform == "currency_usd":
            pattern = r"\$?(?:\d{1,6}|\d{1,3}(?:,\d{3}){1,2})(?:\.\d{1,2})?"
        if not re.fullmatch(pattern, text, flags=re.ASCII):
            raise InputError("Expected an exact USD amount; no rounding, exponents or foreign symbols.")
        return int(Decimal(text.replace("$", "").replace(",", "")) * 100)
    if transform in {"usd", "uppercase_usd"}:
        return text.upper() if transform == "uppercase_usd" else text
    formats = {"iso_date": (r"\d{4}-\d{2}-\d{2}", "%Y-%m-%d"),
               "year_slash_date": (r"\d{4}/\d{2}/\d{2}", "%Y/%m/%d"),
               "us_date": (r"\d{2}/\d{2}/\d{4}", "%m/%d/%Y")}
    if transform not in formats or not re.fullmatch(formats[transform][0], text, flags=re.ASCII):
        raise InputError("Date does not match the selected explicit format.")
    try:
        date = datetime.strptime(text, formats[transform][1]).date()
    except ValueError as exc:
        raise InputError("Date is not a real calendar date.") from exc
    if not 2020 <= date.year <= 2035:
        raise InputError("Order date must be between 2020 and 2035.")
    return date.isoformat()


def extract(rows: list[dict], rules: list[Rule]) -> tuple[list[dict], list[dict]]:
    records, errors, seen = [], [], set()
    for number, row in enumerate(rows, 2):
        record, row_errors = {}, []
        for rule in rules:
            target = "unit_price_cents" if rule.target == "unit_price" else rule.target
            try:
                record[target] = _value(row[rule.source], rule.transform)
            except InputError as exc:
                row_errors.append({"row": number, "field": rule.target, "code": "format", "message": str(exc)})
        for field, valid, message in [
            ("order_id", lambda v: bool(re.fullmatch(r"ORD-[0-9]{4}", v)), "Order ID must be ORD- followed by four digits."),
            ("customer", lambda v: 1 <= len(v) <= 80 and v.isprintable(), "Customer name must be 1–80 printable characters."),
            ("quantity", lambda v: 1 <= v <= 10000, "Quantity must be between one and ten thousand."),
            ("unit_price_cents", lambda v: 1 <= v <= 10_000_000, "Unit price must be positive and at most USD 100,000."),
            ("currency", lambda v: v == "USD", "Currency must be USD; conversion is not an allowed repair."),
        ]:
            if field in record and not valid(record[field]):
                row_errors.append({"row": number, "field": field, "code": "contract", "message": message})
        if "order_id" in record:
            if record["order_id"] in seen:
                row_errors.append({"row": number, "field": "order_id", "code": "duplicate", "message": "Duplicate order ID within the batch."})
            seen.add(record["order_id"])
        if row_errors:
            errors.extend(row_errors)
        else:
            records.append(record)
    return records, errors


def quality(rows: list[dict], records: list[dict], errors: list[dict]) -> dict:
    return {"input_rows": len(rows), "valid_rows": len(records), "invalid_rows": len(rows) - len(records),
            "issues": errors[:100], "issues_truncated": len(errors) > 100}


def detect(headers: list[str], rows: list[dict]) -> dict:
    rules = baseline(headers)
    missing, unexpected = sorted(set(ALIASES) - set(headers)), sorted(set(headers) - set(ALIASES))
    if rules is None:
        records, errors = [], [{"row": 1, "field": "headers", "code": "schema_drift", "message": "Canonical columns changed."}]
    else:
        records, errors = extract(rows, rules)
    return {"missing_columns": missing, "unexpected_columns": unexpected, **quality(rows, records, errors)}
