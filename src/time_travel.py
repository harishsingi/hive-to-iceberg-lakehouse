"""Read a pinned snapshot: the local analogue of Iceberg time travel.

``python -m src.time_travel --snapshot latest`` prints the current
snapshot manifest; ``--snapshot <id>`` prints that earlier version from
the snapshot log; ``--list`` prints every snapshot, oldest first.
Reading never mutates state: a pinned read cannot see a newer write.
"""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path

from .config import load_config
from .logging_config import setup_logging
from .snapshots import read_snapshot_log, resolve_snapshot

logger = logging.getLogger(__name__)


def list_snapshots(curated_dir: Path) -> list[dict]:
    """Return all snapshot manifests in the log, oldest first."""
    return [snap.to_dict() for snap in read_snapshot_log(curated_dir)]


def show_snapshot(curated_dir: Path, snapshot_ref: str) -> dict:
    """Resolve and return one snapshot manifest as a plain dict."""
    return resolve_snapshot(curated_dir, snapshot_ref).to_dict()


def main(argv: list[str] | None = None) -> dict | list[dict]:
    """CLI entry point: ``python -m src.time_travel [--snapshot ID | --list]``."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", type=str, default="latest",
                        help="snapshot id to read, or 'latest' (default)")
    parser.add_argument("--list", action="store_true",
                        help="list all snapshots instead of showing one")
    parser.add_argument("--curated-dir", type=str, default=None,
                        help="curated directory (default: configured curated_dir)")
    parser.add_argument("--config", type=str, default=None,
                        help="YAML config file (default: config.yaml if present)")
    parser.add_argument("--log-level", type=str, default=None,
                        help="log level, e.g. DEBUG (default: from config)")
    args = parser.parse_args(argv)

    cfg = load_config(args.config)
    setup_logging(args.log_level or cfg.log_level)
    curated_dir = Path(args.curated_dir) if args.curated_dir else cfg.paths.curated_dir

    if args.list:
        snapshots = list_snapshots(curated_dir)
        if not snapshots:
            logger.warning("no snapshots found in %s; run migrate first", curated_dir)
        print(json.dumps(snapshots, indent=2))
        return snapshots
    snapshot = show_snapshot(curated_dir, args.snapshot)
    print(json.dumps(snapshot, indent=2))
    return snapshot


if __name__ == "__main__":
    main()
