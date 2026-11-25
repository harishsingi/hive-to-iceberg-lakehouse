"""Generate synthetic parts/service transactions into the raw landing zone.

The data is invented for this portfolio: part names, regions, quantities
and dates are drawn from small fixed pools with a seeded RNG, so runs are
reproducible. Nothing here comes from any employer, customer, or real
system. Run as ``python -m src.generate_data [--rows N] [--out DIR]``.
"""

from __future__ import annotations

import argparse
import csv
import datetime
import logging
import random
from dataclasses import replace
from pathlib import Path

from .config import GeneratorConfig, load_config
from .logging_config import setup_logging
from .schema import TRANSACTION_FIELDS, parse_date

logger = logging.getLogger(__name__)

RAW_FILENAME = "transactions.csv"


def generate_rows(cfg: GeneratorConfig) -> list[dict[str, str | int]]:
    """Build ``cfg.rows`` synthetic transactions with a seeded RNG.

    The RNG is constructed from ``cfg.seed`` (never the global ``random``
    module state), so two runs with the same config produce identical rows.
    Dates start at ``cfg.start_date`` and span ``cfg.date_span_days``.
    """
    rng = random.Random(cfg.seed)
    start = parse_date(cfg.start_date)
    rows: list[dict[str, str | int]] = []
    for txn_id in range(cfg.rows):
        txn_date = start + datetime.timedelta(days=rng.randint(0, cfg.date_span_days))
        rows.append(
            {
                "txn_id": txn_id,
                "part": rng.choice(cfg.parts),
                "dealer_region": rng.choice(cfg.regions),
                "qty": rng.randint(cfg.min_qty, cfg.max_qty),
                "txn_date": txn_date.isoformat(),
            }
        )
    return rows


def write_raw(rows: list[dict[str, str | int]], out_dir: Path) -> Path:
    """Write rows as CSV to ``out_dir/transactions.csv``; return its path."""
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / RAW_FILENAME
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(TRANSACTION_FIELDS))
        writer.writeheader()
        writer.writerows(rows)
    return path


def main(argv: list[str] | None = None) -> Path:
    """CLI entry point: generate raw data and log where it landed."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rows", type=int, default=None,
                        help="rows to generate (default: from config)")
    parser.add_argument("--seed", type=int, default=None,
                        help="RNG seed (default: from config)")
    parser.add_argument("--out", type=str, default=None,
                        help="output directory (default: configured raw_dir)")
    parser.add_argument("--config", type=str, default=None,
                        help="YAML config file (default: config.yaml if present)")
    parser.add_argument("--log-level", type=str, default=None,
                        help="log level, e.g. DEBUG (default: from config)")
    args = parser.parse_args(argv)

    cfg = load_config(args.config)
    gen = cfg.generator
    if args.rows is not None:
        gen = replace(gen, rows=args.rows)
    if args.seed is not None:
        gen = replace(gen, seed=args.seed)
    setup_logging(args.log_level or cfg.log_level)

    rows = generate_rows(gen)
    out_dir = Path(args.out) if args.out else cfg.paths.raw_dir
    path = write_raw(rows, out_dir)
    logger.info("wrote %d rows to %s (seed=%d)", len(rows), path, gen.seed)
    return path


if __name__ == "__main__":
    main()
