"""Tests for src.time_travel: pinned reads and snapshot listing."""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from src.exceptions import InputError, SnapshotNotFoundError
from src.migrate import migrate
from src.generate_data import generate_rows, write_raw
from src.config import GeneratorConfig
from src.time_travel import list_snapshots, main, show_snapshot

REPO_ROOT = Path(__file__).resolve().parent.parent


def _two_snapshots(tmp_path):
    raw = tmp_path / "raw"
    out = tmp_path / "curated"
    write_raw(generate_rows(GeneratorConfig(rows=5)), raw)
    first = migrate(raw, out)
    write_raw(generate_rows(GeneratorConfig(rows=6)), raw)
    second = migrate(raw, out)
    return out, first, second


def test_show_latest_and_pinned(tmp_path):
    out, first, second = _two_snapshots(tmp_path)
    assert show_snapshot(out, "latest")["snapshot_id"] == second["snapshot_id"]
    pinned = show_snapshot(out, first["snapshot_id"])
    assert pinned["snapshot_id"] == first["snapshot_id"]
    assert pinned["rows"] == 5


def test_list_returns_oldest_first(tmp_path):
    out, first, second = _two_snapshots(tmp_path)
    listed = list_snapshots(out)
    assert [s["snapshot_id"] for s in listed] == [
        first["snapshot_id"], second["snapshot_id"],
    ]


def test_unknown_snapshot_raises(tmp_path):
    out, _, _ = _two_snapshots(tmp_path)
    with pytest.raises(SnapshotNotFoundError):
        show_snapshot(out, "0" * 16)


def test_no_snapshots_raises(tmp_path):
    with pytest.raises(InputError):
        show_snapshot(tmp_path / "empty", "latest")
    assert list_snapshots(tmp_path / "empty") == []


def test_cli_list_and_show(tmp_path, capsys):
    out, first, second = _two_snapshots(tmp_path)
    result = main(["--list", "--curated-dir", str(out)])
    assert [s["snapshot_id"] for s in result] == [
        first["snapshot_id"], second["snapshot_id"],
    ]
    printed = json.loads(capsys.readouterr().out)
    assert len(printed) == 2
    shown = main(["--snapshot", first["snapshot_id"], "--curated-dir", str(out)])
    assert shown["rows"] == 5


def test_cli_end_to_end_via_subprocess(tmp_path):
    """The documented README commands run as real subprocesses."""
    env = {"PYTHONPATH": str(REPO_ROOT)}
    subprocess.check_call(
        [sys.executable, "-m", "src.generate_data", "--rows", "50",
         "--out", str(tmp_path / "raw")],
        cwd=REPO_ROOT, env={**os.environ, **env},
    )
    subprocess.check_call(
        [sys.executable, "-m", "src.migrate", "--input", str(tmp_path / "raw"),
         "--output", str(tmp_path / "curated")],
        cwd=REPO_ROOT, env={**os.environ, **env},
    )
    subprocess.check_call(
        [sys.executable, "-m", "src.aggregate", "--input", str(tmp_path / "curated"),
         "--output", str(tmp_path / "gold")],
        cwd=REPO_ROOT, env={**os.environ, **env},
    )
    out = subprocess.check_output(
        [sys.executable, "-m", "src.time_travel", "--snapshot", "latest",
         "--curated-dir", str(tmp_path / "curated")],
        cwd=REPO_ROOT, env={**os.environ, **env}, text=True,
    )
    assert json.loads(out)["rows"] == 50
    assert (tmp_path / "gold" / "monthly_demand.csv").is_file()
