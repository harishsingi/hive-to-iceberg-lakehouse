"""Bronze-to-silver curation: validate, quarantine, and snapshot raw data.

Reads ``transactions.csv`` from the raw directory, screens every row
(see :mod:`src.quality`), writes the valid rows to the curated directory,
writes rejected rows to ``quarantine.csv`` with a ``dq_reason`` column,
and records a snapshot manifest (see :mod:`src.snapshots`).

Idempotency: the snapshot id is a content hash of the valid rows. When a
run reproduces the id of the current snapshot, the curated files are
already correct and the write is skipped, so re-running a stage is safe.
"""

from __future__ import annotations

import argparse
import csv
import logging
from pathlib import Path

from .config import load_config
from .exceptions import InputError, SchemaValidationError
from .logging_config import setup_logging
from .quality import screen_rows
from .schema import TRANSACTION_FIELDS, validate_header
from .snapshots import compute_snapshot_id, latest_snapshot, new_snapshot, record_snapshot

logger = logging.getLogger(__name__)

RAW_FILENAME = "transactions.csv"
CURATED_FILENAME = "curated.csv"
QUARANTINE_FILENAME = "quarantine.csv"
QUARANTINE_FIELDS = list(TRANSACTION_FIELDS) + ["dq_reason"]


def read_raw(input_dir: Path) -> list[dict[str, str]]:
    """Read and header-check the raw CSV; raises :class:`InputError`."""
    path = input_dir / RAW_FILENAME
    if not path.is_file():
        raise InputError(f"raw input not found: {path} (run generate_data first)")
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        header_problems = validate_header(reader.fieldnames)
        missing = [p for p in header_problems if p.startswith("missing required")]
        if missing:
            raise SchemaValidationError(
                f"invalid header in {path}: {'; '.join(missing)}"
            )
        for problem in header_problems:
            logger.warning("%s: %s", path, problem)
        rows = [dict(row) for row in reader]
    if not rows:
        raise InputError(f"no input rows in {path}")
    return rows


def write_curated(rows: list[dict[str, str]], output_dir: Path) -> Path:
    """Write valid rows to ``output_dir/curated.csv``; return its path."""
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / CURATED_FILENAME
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(TRANSACTION_FIELDS))
        writer.writeheader()
        writer.writerows(rows)
    return path


def write_quarantine(quarantined: list, output_dir: Path) -> Path | None:
    """Write rejected rows with reasons; ``None`` when nothing was rejected."""
    if not quarantined:
        return None
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / QUARANTINE_FILENAME
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=QUARANTINE_FIELDS)
        writer.writeheader()
        for item in quarantined:
            row = {f: item.row.get(f, "") for f in TRANSACTION_FIELDS}
            row["dq_reason"] = "; ".join(item.reasons)
            writer.writerow(row)
    return path


def migrate(input_dir: Path, output_dir: Path) -> dict[str, object]:
    """Run one curation pass; return a summary dict (also logged).

    The summary reports ``snapshot_id``, ``skipped`` (True when the run
    was idempotent and nothing was rewritten), and the row metrics.
    """
    rows = read_raw(input_dir)
    result = screen_rows(rows)
    metrics = result.metrics
    logger.info(
        "screened %d rows: %d valid, %d quarantined",
        metrics.rows_in, metrics.rows_valid, metrics.rows_quarantined,
    )
    for reason, count in metrics.quarantine_reasons.most_common():
        logger.info("  quarantined: %s x%d", reason, count)

    snapshot_id = compute_snapshot_id(result.valid_rows)
    current = latest_snapshot(output_dir)
    if current is not None and current.snapshot_id == snapshot_id:
        logger.info(
            "snapshot %s already current; skipping rewrite (idempotent re-run)",
            snapshot_id,
        )
        return {"snapshot_id": snapshot_id, "skipped": True,
                "metrics": metrics.to_dict()}

    curated_path = write_curated(result.valid_rows, output_dir)
    quarantine_path = write_quarantine(result.quarantined, output_dir)
    snapshot = new_snapshot(
        result.valid_rows,
        metrics,
        parent_snapshot_id=current.snapshot_id if current else None,
    )
    record_snapshot(output_dir, snapshot)
    logger.info(
        "wrote %d curated rows to %s; snapshot %s (parent %s)",
        len(result.valid_rows), curated_path, snapshot.snapshot_id,
        snapshot.parent_snapshot_id,
    )
    if quarantine_path is not None:
        logger.info("wrote %d quarantined rows to %s",
                    len(result.quarantined), quarantine_path)
    return {"snapshot_id": snapshot.snapshot_id, "skipped": False,
            "metrics": metrics.to_dict()}


def main(argv: list[str] | None = None) -> dict[str, object]:
    """CLI entry point: ``python -m src.migrate [--input DIR] [--output DIR]``."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=str, default=None,
                        help="raw input directory (default: configured raw_dir)")
    parser.add_argument("--output", type=str, default=None,
                        help="curated output directory (default: configured curated_dir)")
    parser.add_argument("--config", type=str, default=None,
                        help="YAML config file (default: config.yaml if present)")
    parser.add_argument("--log-level", type=str, default=None,
                        help="log level, e.g. DEBUG (default: from config)")
    args = parser.parse_args(argv)

    cfg = load_config(args.config)
    setup_logging(args.log_level or cfg.log_level)
    input_dir = Path(args.input) if args.input else cfg.paths.raw_dir
    output_dir = Path(args.output) if args.output else cfg.paths.curated_dir
    summary = migrate(input_dir, output_dir)
    logger.info("snapshot %s", summary["snapshot_id"])
    return summary


if __name__ == "__main__":
    main()
