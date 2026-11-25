"""Snapshot manifests: the local analogue of Iceberg snapshot metadata.

Every curated write records a manifest (``snapshot.json``) plus an
append-only log (``snapshots.jsonl``) in the curated directory, so readers
can pin a snapshot id and read exactly that version — the local form of
Iceberg time travel. A snapshot id is a content hash of the canonical
sorted valid rows, so re-running the same input reproduces the same id
(idempotency) and different content can never collide with an old snapshot.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from .exceptions import InputError, SnapshotNotFoundError
from .quality import RunMetrics

SNAPSHOT_FILE = "snapshot.json"
SNAPSHOT_LOG = "snapshots.jsonl"


def compute_snapshot_id(rows: Iterable[dict[str, Any]]) -> str:
    """Content hash of the canonical (sorted, JSON) row set.

    Rows are sorted by their JSON representation so row order in the input
    file does not change the id; only content does.
    """
    canonical = "\n".join(
        sorted(json.dumps(dict(row), sort_keys=True) for row in rows)
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]


@dataclass
class Snapshot:
    """One curated-table version."""

    snapshot_id: str
    created_at: str  # ISO 8601, UTC
    rows: int
    parent_snapshot_id: str | None
    metrics: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Snapshot":
        return cls(
            snapshot_id=str(data["snapshot_id"]),
            created_at=str(data["created_at"]),
            rows=int(data["rows"]),
            parent_snapshot_id=data.get("parent_snapshot_id"),
            metrics=dict(data.get("metrics", {})),
        )


def new_snapshot(
    rows: list[dict[str, Any]],
    metrics: RunMetrics,
    parent_snapshot_id: str | None,
) -> Snapshot:
    """Build a snapshot manifest for a fresh curated write."""
    return Snapshot(
        snapshot_id=compute_snapshot_id(rows),
        created_at=datetime.now(timezone.utc).isoformat(),
        rows=len(rows),
        parent_snapshot_id=parent_snapshot_id,
        metrics=metrics.to_dict(),
    )


def latest_snapshot(curated_dir: Path) -> Snapshot | None:
    """Return the current snapshot manifest, or ``None`` if none exists."""
    path = curated_dir / SNAPSHOT_FILE
    if not path.is_file():
        return None
    try:
        return Snapshot.from_dict(json.loads(path.read_text(encoding="utf-8")))
    except (json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
        raise InputError(f"corrupt snapshot manifest {path}: {exc}") from exc


def read_snapshot_log(curated_dir: Path) -> list[Snapshot]:
    """Return every snapshot in the append-only log, oldest first."""
    path = curated_dir / SNAPSHOT_LOG
    if not path.is_file():
        return []
    snapshots: list[Snapshot] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            snapshots.append(Snapshot.from_dict(json.loads(line)))
    return snapshots


def resolve_snapshot(curated_dir: Path, snapshot_ref: str) -> Snapshot:
    """Resolve ``"latest"`` or a snapshot id to a manifest.

    Raises :class:`SnapshotNotFoundError` for an unknown id, and
    :class:`InputError` when no snapshot exists at all.
    """
    if snapshot_ref == "latest":
        snapshot = latest_snapshot(curated_dir)
        if snapshot is None:
            raise InputError(f"no snapshots found in {curated_dir}; run migrate first")
        return snapshot
    for snapshot in read_snapshot_log(curated_dir):
        if snapshot.snapshot_id == snapshot_ref:
            return snapshot
    current = latest_snapshot(curated_dir)
    if current is not None and current.snapshot_id == snapshot_ref:
        return current
    raise SnapshotNotFoundError(
        f"snapshot {snapshot_ref!r} not found in {curated_dir}"
    )


def record_snapshot(curated_dir: Path, snapshot: Snapshot) -> None:
    """Persist a snapshot as current and append it to the history log.

    Appending to the log is skipped when the id is already the latest entry,
    so an idempotent re-run does not grow the log.
    """
    curated_dir.mkdir(parents=True, exist_ok=True)
    (curated_dir / SNAPSHOT_FILE).write_text(
        json.dumps(snapshot.to_dict(), indent=2), encoding="utf-8"
    )
    log_path = curated_dir / SNAPSHOT_LOG
    existing = read_snapshot_log(curated_dir)
    if existing and existing[-1].snapshot_id == snapshot.snapshot_id:
        return
    with log_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(snapshot.to_dict()) + "\n")
