"""Silver-to-gold aggregation: monthly demand by part and region.

Reads the curated table and writes ``monthly_demand.csv``: one row per
(part, dealer_region, month) with total quantity, transaction count, and
average quantity. The gold table is rebuilt from scratch on every run,
which is the correct behaviour for a small derived aggregate; a production
job would instead do an incremental upsert keyed on the snapshot id.
"""

from __future__ import annotations

import argparse
import csv
import logging
from collections import defaultdict
from pathlib import Path

from .config import load_config
from .exceptions import InputError
from .logging_config import setup_logging
from .schema import parse_date

logger = logging.getLogger(__name__)

CURATED_FILENAME = "curated.csv"
GOLD_FILENAME = "monthly_demand.csv"
GOLD_FIELDS = ("part", "dealer_region", "month", "total_qty", "txn_count", "avg_qty")


def aggregate_rows(rows: list[dict[str, str]]) -> list[dict[str, str | int | float]]:
    """Group curated rows into monthly (part, region) demand totals.

    ``month`` is the ``YYYY-MM`` prefix of ``txn_date``. Output is sorted
    by (month, part, region) so the file is deterministic. ``avg_qty`` is
    rounded to 2 decimals for readability.
    """
    totals: dict[tuple[str, str, str], dict[str, int]] = defaultdict(
        lambda: {"total_qty": 0, "txn_count": 0}
    )
    for row in rows:
        month = parse_date(row["txn_date"]).strftime("%Y-%m")
        key = (row["part"], row["dealer_region"], month)
        totals[key]["total_qty"] += int(row["qty"])
        totals[key]["txn_count"] += 1
    gold: list[dict[str, str | int | float]] = []
    for (part, region, month), agg in totals.items():
        gold.append(
            {
                "part": part,
                "dealer_region": region,
                "month": month,
                "total_qty": agg["total_qty"],
                "txn_count": agg["txn_count"],
                "avg_qty": round(agg["total_qty"] / agg["txn_count"], 2),
            }
        )
    gold.sort(key=lambda g: (g["month"], g["part"], g["dealer_region"]))
    return gold


def build_gold(curated_dir: Path, gold_dir: Path) -> Path:
    """Read the curated table, write the gold aggregate, return its path."""
    path = curated_dir / CURATED_FILENAME
    if not path.is_file():
        raise InputError(f"curated input not found: {path} (run migrate first)")
    with path.open(newline="", encoding="utf-8") as handle:
        rows = [dict(row) for row in csv.DictReader(handle)]
    if not rows:
        raise InputError(f"no curated rows in {path}")
    gold_rows = aggregate_rows(rows)
    gold_dir.mkdir(parents=True, exist_ok=True)
    out_path = gold_dir / GOLD_FILENAME
    with out_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(GOLD_FIELDS))
        writer.writeheader()
        writer.writerows(gold_rows)
    logger.info(
        "aggregated %d curated rows into %d monthly groups at %s",
        len(rows), len(gold_rows), out_path,
    )
    return out_path


def main(argv: list[str] | None = None) -> Path:
    """CLI entry point: ``python -m src.aggregate [--input DIR] [--output DIR]``."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=str, default=None,
                        help="curated input directory (default: configured curated_dir)")
    parser.add_argument("--output", type=str, default=None,
                        help="gold output directory (default: configured gold_dir)")
    parser.add_argument("--config", type=str, default=None,
                        help="YAML config file (default: config.yaml if present)")
    parser.add_argument("--log-level", type=str, default=None,
                        help="log level, e.g. DEBUG (default: from config)")
    args = parser.parse_args(argv)

    cfg = load_config(args.config)
    setup_logging(args.log_level or cfg.log_level)
    input_dir = Path(args.input) if args.input else cfg.paths.curated_dir
    output_dir = Path(args.output) if args.output else cfg.paths.gold_dir
    return build_gold(input_dir, output_dir)


if __name__ == "__main__":
    main()
