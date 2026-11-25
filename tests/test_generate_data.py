"""Tests for src.generate_data: determinism, config validation, output."""

import csv

import pytest

from src.config import GeneratorConfig
from src.generate_data import generate_rows, write_raw


def test_row_count_and_columns():
    rows = generate_rows(GeneratorConfig(rows=25))
    assert len(rows) == 25
    assert set(rows[0]) == {"txn_id", "part", "dealer_region", "qty", "txn_date"}


def test_same_seed_same_rows():
    a = generate_rows(GeneratorConfig(rows=50, seed=7))
    b = generate_rows(GeneratorConfig(rows=50, seed=7))
    assert a == b


def test_different_seed_different_rows():
    a = generate_rows(GeneratorConfig(rows=50, seed=7))
    b = generate_rows(GeneratorConfig(rows=50, seed=8))
    assert a != b


def test_values_within_configured_pools():
    cfg = GeneratorConfig(rows=200, parts=("x", "y"), regions=("N", "S"),
                          min_qty=2, max_qty=5)
    rows = generate_rows(cfg)
    assert {r["part"] for r in rows} <= {"x", "y"}
    assert {r["dealer_region"] for r in rows} <= {"N", "S"}
    assert all(2 <= r["qty"] <= 5 for r in rows)
    # Dates start at 2024-01-01 and span 700 days, so they reach into 2025.
    assert all("2024-01-01" <= r["txn_date"] <= "2025-12-01" for r in rows)


def test_txn_ids_unique_and_sequential():
    rows = generate_rows(GeneratorConfig(rows=10))
    assert [r["txn_id"] for r in rows] == list(range(10))


def test_invalid_rows_rejected():
    with pytest.raises(ValueError):
        GeneratorConfig(rows=0)
    with pytest.raises(ValueError):
        GeneratorConfig(rows=-3)
    with pytest.raises(ValueError):
        GeneratorConfig(min_qty=0)
    with pytest.raises(ValueError):
        GeneratorConfig(min_qty=5, max_qty=2)
    with pytest.raises(ValueError):
        GeneratorConfig(parts=())


def test_write_raw_round_trip(tmp_path):
    rows = generate_rows(GeneratorConfig(rows=10))
    path = write_raw(rows, tmp_path / "raw")
    assert path.name == "transactions.csv"
    with path.open(newline="") as handle:
        back = list(csv.DictReader(handle))
    assert len(back) == 10
    assert back[0]["txn_id"] == "0"
