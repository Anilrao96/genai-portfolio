import pytest

from projects.p05_self_healing_pipeline.contract import ALIASES, InputError, Rule, baseline, detect, extract, parse_csv, validate_plan


def rules_for(headers, style="month_first"):
    transforms={"order_id":"trim","customer":"trim","quantity":"integral_decimal","unit_price":"currency_usd","currency":"uppercase_usd","ordered_on":"us_date" if style=="month_first" else "year_slash_date"}
    return [Rule(source=next(h for h in headers if h in names),target=target,transform=transforms[target]) for target,names in ALIASES.items()]


HEADERS=list(ALIASES)
ROW={"order_id":"ORD-0001","customer":" Aster ","quantity":"2","unit_price":"12.50","currency":"USD","ordered_on":"2026-11-01"}


def test_baseline_and_exact_currency_date_repairs():
    records,issues=extract([ROW],baseline(HEADERS))
    assert not issues and records[0]["unit_price_cents"]==1250 and records[0]["customer"]=="Aster"
    row={**ROW,"quantity":"3.0","unit_price":"$1,200.00","currency":"usd","ordered_on":"03/04/2026"}
    rules=rules_for(HEADERS)
    validate_plan(rules,HEADERS,"month_first")
    records,issues=extract([row],rules)
    assert not issues and records[0]["quantity"]==3 and records[0]["unit_price_cents"]==120000
    assert records[0]["ordered_on"]=="2026-03-04"
    with pytest.raises(InputError,match="declared month-first"):
        validate_plan(rules,HEADERS,"year_first")


@pytest.mark.parametrize("field,value",[("quantity","1.2"),("quantity","0"),("quantity","10001"),("quantity","1e2"),("quantity","٣"),("unit_price","1.234"),("unit_price","NaN"),("unit_price","-1.00"),("unit_price","€1.00"),("unit_price","$1,20.00"),("currency","EUR"),("ordered_on","02/30/2026"),("ordered_on","11/01/2040"),("order_id","../../file"),("customer","\n"),("customer","a"*81),("customer","Aster\x7f")])
def test_no_value_invention_rounding_or_currency_conversion(field,value):
    row={**ROW,"quantity":"2.0","unit_price":"$12.50","currency":"usd","ordered_on":"11/01/2026",field:value}
    records,issues=extract([row],rules_for(HEADERS))
    assert not records and issues


@pytest.mark.parametrize("csv",["", "a,a\n1,2", "a,b\n1", 'a\n"unterminated', "a\n"+"x"*201, "a\n"+"1\n"*201, "a\n\x00"])
def test_malformed_or_unbounded_csv_is_rejected(csv):
    with pytest.raises(InputError):parse_csv(csv)


def test_plan_cannot_drop_swap_or_execute():
    rules=rules_for(HEADERS)
    for bad in [rules[:-1], [rules[0]]*6, [r.model_copy(update={"source":"customer"}) if r.target=="order_id" else r for r in rules]]:
        with pytest.raises(InputError):validate_plan(bad,HEADERS,"month_first")
    with pytest.raises(ValueError):Rule(source="quantity",target="quantity",transform="eval")
    with pytest.raises(ValueError):Rule(source="quantity",target="quantity",transform="integer",code="import os")
    with pytest.raises(InputError):validate_plan([r.model_copy(update={"transform":"trim"}) if r.target=="quantity" else r for r in rules],HEADERS,"month_first")


def test_duplicate_rows_and_schema_drift_are_visible():
    records,issues=extract([ROW,ROW],baseline(HEADERS))
    assert len(records)==1 and issues[0]["code"]=="duplicate"
    report=detect(["new_column"],[{"new_column":"x"}])
    assert report["valid_rows"]==0 and report["missing_columns"]==sorted(HEADERS)
