"""Tests for src.schema: header and row validation."""

import pytest

from src.schema import TRANSACTION_FIELDS, parse_date, validate_header, validate_row
from src.exceptions import SchemaValidationError


def valid_row(**overrides):
    row = {
        "txn_id": "7",
        "part": "battery",
        "dealer_region": "SE",
        "qty": "3",
        "txn_date": "2024-03-15",
    }
    row.update(overrides)
    return row


def test_valid_row_has_no_problems():
    assert validate_row(valid_row()) == []


def test_missing_field_reported():
    row = valid_row()
    del row["qty"]
    problems = validate_row(row)
    assert any("qty" in p for p in problems)


def test_blank_field_reported():
    assert validate_row(valid_row(part="   "))


def test_non_integer_qty_rejected():
    problems = validate_row(valid_row(qty="three"))
    assert any("not an integer" in p for p in problems)


def test_zero_and_negative_qty_rejected():
    assert validate_row(valid_row(qty="0"))
    assert validate_row(valid_row(qty="-5"))


def test_bad_date_format_rejected():
    assert validate_row(valid_row(txn_date="03/15/2024"))


def test_impossible_date_rejected():
    # 2024-02-30 matches the format but is not a real calendar date.
    assert validate_row(valid_row(txn_date="2024-02-30"))


def test_header_missing_column():
    problems = validate_header(["txn_id", "part"])
    assert any("dealer_region" in p for p in problems)
    assert any("qty" in p for p in problems)


def test_header_none_is_a_problem():
    assert validate_header(None) == ["missing header row"]


def test_header_extra_column_tolerated_but_reported():
    problems = validate_header(list(TRANSACTION_FIELDS) + ["extra_col"])
    assert any("unexpected column" in p for p in problems)


def test_parse_date_ok_and_bad():
    assert str(parse_date("2024-01-31")) == "2024-01-31"
    with pytest.raises(SchemaValidationError):
        parse_date("2024-02-30")
    with pytest.raises(SchemaValidationError):
        parse_date("not-a-date")
