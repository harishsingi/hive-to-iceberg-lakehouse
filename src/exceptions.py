"""Shared exceptions for the hive-to-iceberg-lakehouse package.

Each failure mode gets its own type so callers (CLI entry points, the
Airflow DAG, tests) can distinguish a bad input file from a data-quality
rejection from a missing snapshot instead of catching bare ``Exception``.
"""

from __future__ import annotations


class LakehouseError(Exception):
    """Base class for all errors raised by this package."""


class InputError(LakehouseError):
    """The input file, directory, or CLI argument is missing or unusable."""


class SchemaValidationError(LakehouseError):
    """Input data does not match the expected schema (columns or row shape)."""


class DataQualityError(LakehouseError):
    """A data-quality gate failed (e.g. every row was quarantined)."""


class SnapshotNotFoundError(LakehouseError):
    """A requested snapshot id does not exist in the snapshot log."""
