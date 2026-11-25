"""Tests for src.aggregate: monthly gold aggregation."""

import csv

import pytest

from src.aggregate import aggregate_rows, build_gold
from src.exceptions import InputError


def _row(part, region, date, qty, txn_id="1"):
    return {"txn_id": txn_id, "part": part, "dealer_region": region,
            "qty": str(qty), "txn_date": date}


def test_groups_by_part_region_month():
    rows = [
        _row("battery", "SE", "2024-01-05", 2, "1"),
        _row("battery", "SE", "2024-01-20", 4, "2"),
        _row("battery", "SE", "2024-02-01", 10, "3"),
        _row("filter", "SE", "2024-01-05", 1, "4"),
    ]
    gold = aggregate_rows(rows)
    assert len(gold) == 3
    jan = next(g for g in gold if g["month"] == "2024-01" and g["part"] == "battery")
    assert jan["total_qty"] == 6
    assert jan["txn_count"] == 2
    assert jan["avg_qty"] == 3.0
    feb = next(g for g in gold if g["month"] == "2024-02")
    assert feb["total_qty"] == 10


def test_output_sorted_deterministically():
    rows = [_row("pump", "W", "2024-03-01", 1, "1"),
            _row("battery", "SE", "2024-01-01", 1, "2")]
    gold = aggregate_rows(rows)
    assert [(g["month"], g["part"]) for g in gold] == [
        ("2024-01", "battery"), ("2024-03", "pump"),
    ]


def test_empty_rows_produce_empty_gold():
    assert aggregate_rows([]) == []


def test_build_gold_writes_file(tmp_path):
    curated = tmp_path / "curated"
    curated.mkdir()
    with (curated / "curated.csv").open("w", newline="") as handle:
        writer = csv.DictWriter(
            handle, fieldnames=["txn_id", "part", "dealer_region", "qty", "txn_date"])
        writer.writeheader()
        writer.writerow(_row("battery", "SE", "2024-01-05", 2, "1"))
        writer.writerow(_row("battery", "SE", "2024-01-06", 4, "2"))
    out = build_gold(curated, tmp_path / "gold")
    assert out.name == "monthly_demand.csv"
    with out.open(newline="") as handle:
        gold = list(csv.DictReader(handle))
    assert len(gold) == 1
    assert gold[0]["total_qty"] == "6"
    assert gold[0]["txn_count"] == "2"


def test_build_gold_missing_input_raises(tmp_path):
    with pytest.raises(InputError):
        build_gold(tmp_path / "nope", tmp_path / "gold")
