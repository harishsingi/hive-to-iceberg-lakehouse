"""Schema definition and row-level validation for transaction records.

The schema is the contract between the raw landing zone and the curated
(Iceberg-style) table. Validation is pure and side-effect free: it returns
a list of human-readable problems per row, and never raises for bad data,
so callers can quarantine bad rows instead of aborting the whole run.
"""

from __future__ import annotations

import datetime
import re
from typing import Any, Iterable

from .exceptions import SchemaValidationError

# Canonical column order for the transactions table. Keep this list as the
# single source of truth; writers and readers both derive from it.
TRANSACTION_FIELDS: tuple[str, ...] = (
    "txn_id",
    "part",
    "dealer_region",
    "qty",
    "txn_date",
)

REQUIRED_FIELDS: tuple[str, ...] = TRANSACTION_FIELDS

# txn_date must be a plain ISO calendar date, e.g. "2024-03-15".
ISO_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def validate_header(fieldnames: Iterable[str] | None) -> list[str]:
    """Check a CSV header against the expected schema.

    Returns a list of problems (empty when the header is fine). A missing
    file header (``None``) and any missing required column are problems;
    extra columns are tolerated and reported, not rejected, so an upstream
    additive schema change does not break the pipeline.
    """
    problems: list[str] = []
    if fieldnames is None:
        return ["missing header row"]
    present = set(fieldnames)
    for field in REQUIRED_FIELDS:
        if field not in present:
            problems.append(f"missing required column: {field}")
    for field in present - set(REQUIRED_FIELDS):
        problems.append(f"unexpected column (ignored): {field}")
    return problems


def validate_row(row: dict[str, Any], line_no: int | None = None) -> list[str]:
    """Validate one transaction row; return a list of problems (empty = valid).

    Rules:
    - every required field present and non-blank;
    - ``txn_id`` non-empty (uniqueness is checked separately, see
      :mod:`src.quality`, because it needs the whole file);
    - ``qty`` an integer greater than zero;
    - ``txn_date`` a real ISO calendar date (``2024-02-30`` is rejected).
    ``line_no`` is only used to make messages traceable; it is not validated.
    """
    problems: list[str] = []
    where = f"line {line_no}: " if line_no is not None else ""
    for field in REQUIRED_FIELDS:
        value = row.get(field)
        if value is None or str(value).strip() == "":
            problems.append(f"{where}missing or blank value for {field!r}")
    if problems:
        return problems

    qty_raw = str(row["qty"]).strip()
    try:
        qty = int(qty_raw)
    except ValueError:
        problems.append(f"{where}qty {qty_raw!r} is not an integer")
    else:
        if qty <= 0:
            problems.append(f"{where}qty must be positive, got {qty}")

    date_raw = str(row["txn_date"]).strip()
    if not ISO_DATE_RE.match(date_raw):
        problems.append(f"{where}txn_date {date_raw!r} is not YYYY-MM-DD")
    else:
        try:
            datetime.date.fromisoformat(date_raw)
        except ValueError:
            problems.append(f"{where}txn_date {date_raw!r} is not a real date")
    return problems


def parse_date(value: str) -> datetime.date:
    """Parse an ISO date string, raising :class:`SchemaValidationError`."""
    if not ISO_DATE_RE.match(value.strip()):
        raise SchemaValidationError(f"txn_date {value!r} is not YYYY-MM-DD")
    try:
        return datetime.date.fromisoformat(value.strip())
    except ValueError as exc:
        raise SchemaValidationError(f"txn_date {value!r} is not a real date") from exc
