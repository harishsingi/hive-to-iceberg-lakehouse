"""Tests for src.quality: valid/quarantine split, duplicates, metrics."""

import pytest

from src.exceptions import DataQualityError
from src.quality import screen_rows
from tests.test_schema import valid_row


def test_all_valid_rows_pass_through():
    result = screen_rows([valid_row(txn_id="1"), valid_row(txn_id="2")])
    assert len(result.valid_rows) == 2
    assert result.quarantined == []
    assert result.metrics.rows_in == 2
    assert result.metrics.rows_valid == 2
    assert result.metrics.rows_quarantined == 0
    assert result.metrics.rows_written == 2


def test_bad_qty_row_is_quarantined_not_dropped_silently():
    result = screen_rows([valid_row(txn_id="1"), valid_row(txn_id="2", qty="0")])
    assert len(result.valid_rows) == 1
    assert len(result.quarantined) == 1
    assert result.quarantined[0].row["txn_id"] == "2"
    assert result.quarantined[0].reasons
    assert result.metrics.rows_quarantined == 1


def test_duplicate_txn_id_quarantined_first_kept():
    rows = [valid_row(txn_id="9"), valid_row(txn_id="9", part="filter")]
    result = screen_rows(rows)
    assert len(result.valid_rows) == 1
    assert result.valid_rows[0]["part"] == "battery"
    assert len(result.quarantined) == 1
    assert any("duplicate txn_id" in r for r in result.quarantined[0].reasons)


def test_quarantine_reasons_counted():
    rows = [
        valid_row(txn_id="1"),
        valid_row(txn_id="2", qty="0"),
        valid_row(txn_id="3", qty="-1"),
        valid_row(txn_id="4", txn_date="2024-02-30"),
    ]
    result = screen_rows(rows)
    assert result.metrics.rows_quarantined == 3
    assert sum(result.metrics.quarantine_reasons.values()) == 3


def test_all_rows_bad_raises():
    with pytest.raises(DataQualityError):
        screen_rows([valid_row(txn_id="1", qty="0")])


def test_empty_input_is_not_an_error():
    result = screen_rows([])
    assert result.metrics.rows_in == 0
    assert result.valid_rows == []


def test_metrics_serialise():
    result = screen_rows([valid_row(txn_id="1"), valid_row(txn_id="2", qty="0")])
    data = result.metrics.to_dict()
    assert data["rows_in"] == 2
    assert data["rows_valid"] == 1
    assert data["rows_quarantined"] == 1
    assert data["rows_written"] == 1
    assert isinstance(data["quarantine_reasons"], dict)
