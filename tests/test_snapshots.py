"""Tests for src.snapshots: ids, manifests, log, resolution."""

import pytest

from src.exceptions import InputError, SnapshotNotFoundError
from src.quality import RunMetrics
from src.snapshots import (
    compute_snapshot_id,
    latest_snapshot,
    new_snapshot,
    read_snapshot_log,
    record_snapshot,
    resolve_snapshot,
)


def _metrics(n):
    m = RunMetrics(rows_in=n, rows_valid=n)
    return m


def test_snapshot_id_is_content_based_not_row_count():
    rows_a = [{"txn_id": "1", "qty": "2"}, {"txn_id": "2", "qty": "3"}]
    rows_b = [{"txn_id": "1", "qty": "9"}, {"txn_id": "2", "qty": "3"}]
    assert compute_snapshot_id(rows_a) != compute_snapshot_id(rows_b)
    assert compute_snapshot_id(rows_a) == compute_snapshot_id(list(reversed(rows_a)))


def test_record_and_resolve_latest(tmp_path):
    snap = new_snapshot([{"txn_id": "1"}], _metrics(1), parent_snapshot_id=None)
    record_snapshot(tmp_path, snap)
    assert latest_snapshot(tmp_path).snapshot_id == snap.snapshot_id
    assert resolve_snapshot(tmp_path, "latest").snapshot_id == snap.snapshot_id
    assert resolve_snapshot(tmp_path, snap.snapshot_id).snapshot_id == snap.snapshot_id


def test_parent_chain_and_log_order(tmp_path):
    first = new_snapshot([{"txn_id": "1"}], _metrics(1), None)
    record_snapshot(tmp_path, first)
    second = new_snapshot(
        [{"txn_id": "1"}, {"txn_id": "2"}], _metrics(2),
        parent_snapshot_id=first.snapshot_id,
    )
    record_snapshot(tmp_path, second)
    log = read_snapshot_log(tmp_path)
    assert [s.snapshot_id for s in log] == [first.snapshot_id, second.snapshot_id]
    assert log[1].parent_snapshot_id == first.snapshot_id
    assert latest_snapshot(tmp_path).snapshot_id == second.snapshot_id


def test_idempotent_record_does_not_duplicate_log(tmp_path):
    snap = new_snapshot([{"txn_id": "1"}], _metrics(1), None)
    record_snapshot(tmp_path, snap)
    record_snapshot(tmp_path, snap)
    assert len(read_snapshot_log(tmp_path)) == 1


def test_unknown_snapshot_id_raises(tmp_path):
    snap = new_snapshot([{"txn_id": "1"}], _metrics(1), None)
    record_snapshot(tmp_path, snap)
    with pytest.raises(SnapshotNotFoundError):
        resolve_snapshot(tmp_path, "deadbeefdeadbeef")


def test_no_snapshot_at_all_raises_input_error(tmp_path):
    assert latest_snapshot(tmp_path) is None
    assert read_snapshot_log(tmp_path) == []
    with pytest.raises(InputError):
        resolve_snapshot(tmp_path, "latest")


def test_corrupt_manifest_raises_input_error(tmp_path):
    (tmp_path / "snapshot.json").write_text("{not json", encoding="utf-8")
    with pytest.raises(InputError):
        latest_snapshot(tmp_path)
