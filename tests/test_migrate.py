"""Tests for src.migrate: end-to-end curation, quarantine, idempotency."""

import csv
import json

import pytest

from src.exceptions import DataQualityError, InputError, SchemaValidationError
from src.migrate import migrate, read_raw
from src.generate_data import generate_rows, write_raw
from src.config import GeneratorConfig


def _raw_dir(tmp_path, rows=20, **cfg_kwargs):
    raw = tmp_path / "raw"
    write_raw(generate_rows(GeneratorConfig(rows=rows, **cfg_kwargs)), raw)
    return raw


def _read_csv(path):
    with path.open(newline="") as handle:
        return list(csv.DictReader(handle))


def test_happy_path_writes_curated_snapshot_and_metrics(tmp_path):
    summary = migrate(_raw_dir(tmp_path), tmp_path / "curated")
    assert summary["skipped"] is False
    curated = _read_csv(tmp_path / "curated" / "curated.csv")
    assert len(curated) == 20
    snap = json.loads((tmp_path / "curated" / "snapshot.json").read_text())
    assert snap["snapshot_id"] == summary["snapshot_id"]
    assert snap["rows"] == 20
    assert snap["parent_snapshot_id"] is None
    assert snap["metrics"]["rows_in"] == 20
    assert snap["metrics"]["rows_quarantined"] == 0
    assert (tmp_path / "curated" / "snapshots.jsonl").is_file()


def test_idempotent_rerun_skips_rewrite(tmp_path):
    raw = _raw_dir(tmp_path)
    out = tmp_path / "curated"
    first = migrate(raw, out)
    second = migrate(raw, out)
    assert second["snapshot_id"] == first["snapshot_id"]
    assert second["skipped"] is True
    assert len((out / "snapshots.jsonl").read_text().splitlines()) == 1


def test_changed_input_creates_new_snapshot_with_parent(tmp_path):
    raw = _raw_dir(tmp_path, rows=20)
    out = tmp_path / "curated"
    first = migrate(raw, out)
    _raw_dir(tmp_path, rows=21)  # regenerate same dir with one more row
    second = migrate(raw, out)
    assert second["skipped"] is False
    assert second["snapshot_id"] != first["snapshot_id"]
    snap = json.loads((out / "snapshot.json").read_text())
    assert snap["parent_snapshot_id"] == first["snapshot_id"]
    assert len((out / "snapshots.jsonl").read_text().splitlines()) == 2


def test_bad_rows_quarantined_run_continues(tmp_path):
    raw = _raw_dir(tmp_path, rows=10)
    rows = _read_csv(raw / "transactions.csv")
    rows.append({"txn_id": "999", "part": "battery", "dealer_region": "SE",
                 "qty": "0", "txn_date": "2024-05-01"})
    rows.append({"txn_id": "5", "part": "filter", "dealer_region": "NE",
                 "qty": "4", "txn_date": "2024-05-01"})  # duplicate txn_id 5
    with (raw / "transactions.csv").open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    summary = migrate(raw, tmp_path / "curated")
    assert summary["metrics"]["rows_in"] == 12
    assert summary["metrics"]["rows_quarantined"] == 2
    assert len(_read_csv(tmp_path / "curated" / "curated.csv")) == 10
    quarantine = _read_csv(tmp_path / "curated" / "quarantine.csv")
    assert len(quarantine) == 2
    assert all(q["dq_reason"] for q in quarantine)


def test_missing_input_raises(tmp_path):
    with pytest.raises(InputError):
        migrate(tmp_path / "nope", tmp_path / "curated")


def test_empty_input_raises(tmp_path):
    raw = tmp_path / "raw"
    raw.mkdir()
    (raw / "transactions.csv").write_text(
        "txn_id,part,dealer_region,qty,txn_date\n", encoding="utf-8"
    )
    with pytest.raises(InputError):
        migrate(raw, tmp_path / "curated")


def test_missing_column_raises_schema_error(tmp_path):
    raw = tmp_path / "raw"
    raw.mkdir()
    (raw / "transactions.csv").write_text(
        "txn_id,part,qty,txn_date\n1,battery,3,2024-01-01\n", encoding="utf-8"
    )
    with pytest.raises(SchemaValidationError):
        read_raw(raw)


def test_all_rows_bad_raises_data_quality_error(tmp_path):
    raw = tmp_path / "raw"
    raw.mkdir()
    (raw / "transactions.csv").write_text(
        "txn_id,part,dealer_region,qty,txn_date\n1,battery,SE,0,2024-01-01\n",
        encoding="utf-8",
    )
    with pytest.raises(DataQualityError):
        migrate(raw, tmp_path / "curated")
