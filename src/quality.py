"""Data-quality screening: split rows into valid and quarantined sets.

A row is quarantined, never silently dropped and never allowed to fail the
whole run: the caller writes quarantined rows (with a ``dq_reason`` column)
to a quarantine file for inspection, and the counts feed the run metrics
that are logged and stored in the snapshot manifest. Only the degenerate
case, zero valid rows, aborts the run (see :class:`DataQualityError`).
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from typing import Any, Iterable

from .exceptions import DataQualityError
from .schema import validate_row


@dataclass
class RunMetrics:
    """Row counts for one curation run; logged and stored in the snapshot."""

    rows_in: int = 0
    rows_valid: int = 0
    rows_quarantined: int = 0
    quarantine_reasons: Counter = field(default_factory=Counter)

    @property
    def rows_written(self) -> int:
        """Rows that reach the curated table (equals ``rows_valid``)."""
        return self.rows_valid

    def to_dict(self) -> dict[str, Any]:
        return {
            "rows_in": self.rows_in,
            "rows_valid": self.rows_valid,
            "rows_quarantined": self.rows_quarantined,
            "rows_written": self.rows_written,
            "quarantine_reasons": dict(self.quarantine_reasons),
        }


@dataclass
class QuarantinedRow:
    """One rejected row plus the reasons it was rejected."""

    row: dict[str, Any]
    reasons: list[str]
    line_no: int | None = None


@dataclass
class QualityResult:
    """Outcome of screening a batch of rows."""

    valid_rows: list[dict[str, Any]]
    quarantined: list[QuarantinedRow]
    metrics: RunMetrics


def screen_rows(rows: Iterable[dict[str, Any]]) -> QualityResult:
    """Validate rows, enforce unique ``txn_id``, and split valid/quarantined.

    Duplicate ``txn_id`` values (after the first occurrence) are quarantined
    with reason ``duplicate txn_id``; the first occurrence is kept. Raises
    :class:`DataQualityError` when no row survives screening, because
    promoting an empty snapshot would silently publish an empty table.
    """
    valid_rows: list[dict[str, Any]] = []
    quarantined: list[QuarantinedRow] = []
    metrics = RunMetrics()
    seen_ids: set[str] = set()

    for line_no, row in enumerate(rows, start=2):  # line 1 is the CSV header
        metrics.rows_in += 1
        reasons = validate_row(row, line_no=line_no)
        txn_id = str(row.get("txn_id", "")).strip()
        if not reasons and txn_id in seen_ids:
            reasons = [f"line {line_no}: duplicate txn_id {txn_id!r}"]
        if reasons:
            quarantined.append(QuarantinedRow(row=dict(row), reasons=reasons, line_no=line_no))
            metrics.rows_quarantined += 1
            for reason in reasons:
                # Count by reason kind (text after "line N: ") so the
                # breakdown stays stable across files.
                kind = reason.split(": ", 1)[-1]
                metrics.quarantine_reasons[kind] += 1
            continue
        seen_ids.add(txn_id)
        valid_rows.append(dict(row))
        metrics.rows_valid += 1

    if metrics.rows_in > 0 and metrics.rows_valid == 0:
        raise DataQualityError(
            f"all {metrics.rows_in} input rows failed validation; "
            "nothing to curate (see quarantine output)"
        )
    return QualityResult(valid_rows=valid_rows, quarantined=quarantined, metrics=metrics)
