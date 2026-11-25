"""Configuration for the package, separated from the pipeline logic.

Defaults live in code (see :data:`DEFAULT_CONFIG`); a YAML file may
override any of them. Paths are resolved relative to the repository root
unless given as absolute paths, so the same config works from any working
directory. No credentials are read or stored here: this pipeline runs
fully locally and talks to no external service.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from .exceptions import InputError

REPO_ROOT = Path(__file__).resolve().parent.parent

# ---------------------------------------------------------------------------
# Defaults (also mirrored in config.yaml at the repo root for discoverability)
# ---------------------------------------------------------------------------
DEFAULT_SEED = 42
DEFAULT_ROWS = 1000
DEFAULT_START_DATE = "2024-01-01"
DEFAULT_DATE_SPAN_DAYS = 700
DEFAULT_PARTS: tuple[str, ...] = (
    "brake pad",
    "filter",
    "battery",
    "alternator",
    "sensor",
    "pump",
)
DEFAULT_REGIONS: tuple[str, ...] = ("SE", "NE", "MW", "W")
MIN_QTY = 1
MAX_QTY = 20


@dataclass(frozen=True)
class GeneratorConfig:
    """Settings for synthetic raw-data generation."""

    rows: int = DEFAULT_ROWS
    seed: int = DEFAULT_SEED
    start_date: str = DEFAULT_START_DATE
    date_span_days: int = DEFAULT_DATE_SPAN_DAYS
    parts: tuple[str, ...] = DEFAULT_PARTS
    regions: tuple[str, ...] = DEFAULT_REGIONS
    min_qty: int = MIN_QTY
    max_qty: int = MAX_QTY

    def __post_init__(self) -> None:
        if self.rows <= 0:
            raise ValueError(f"rows must be positive, got {self.rows}")
        if self.date_span_days < 0:
            raise ValueError(f"date_span_days must be >= 0, got {self.date_span_days}")
        if self.min_qty < 1 or self.max_qty < self.min_qty:
            raise ValueError(
                f"invalid qty range: min_qty={self.min_qty}, max_qty={self.max_qty}"
            )
        if not self.parts or not self.regions:
            raise ValueError("parts and regions must be non-empty")


@dataclass(frozen=True)
class Paths:
    """Directory layout. Relative paths resolve against the repo root."""

    raw_dir: Path = Path("data/raw")
    curated_dir: Path = Path("data/curated")
    gold_dir: Path = Path("data/gold")

    def resolve(self, base: Path = REPO_ROOT) -> "Paths":
        """Return a copy with every path made absolute against ``base``."""
        def _abs(p: Path) -> Path:
            return p if p.is_absolute() else base / p

        return Paths(
            raw_dir=_abs(self.raw_dir),
            curated_dir=_abs(self.curated_dir),
            gold_dir=_abs(self.gold_dir),
        )


@dataclass(frozen=True)
class AppConfig:
    """Top-level config: generator settings plus directory layout."""

    generator: GeneratorConfig = field(default_factory=GeneratorConfig)
    paths: Paths = field(default_factory=Paths)
    log_level: str = "INFO"


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def _defaults_dict() -> dict[str, Any]:
    gen = GeneratorConfig()
    paths = Paths()
    return {
        "generator": {
            "rows": gen.rows,
            "seed": gen.seed,
            "start_date": gen.start_date,
            "date_span_days": gen.date_span_days,
            "parts": list(gen.parts),
            "regions": list(gen.regions),
            "min_qty": gen.min_qty,
            "max_qty": gen.max_qty,
        },
        "paths": {
            "raw_dir": str(paths.raw_dir),
            "curated_dir": str(paths.curated_dir),
            "gold_dir": str(paths.gold_dir),
        },
        "log_level": "INFO",
    }


def _coerce_env_overrides(data: dict[str, Any]) -> dict[str, Any]:
    """Apply documented environment-variable overrides, if set.

    ``LAKEHOUSE_ROWS`` overrides ``generator.rows``;
    ``LAKEHOUSE_SEED`` overrides ``generator.seed``.
    Values must parse as integers; anything else raises ``InputError``.
    """
    for env_name, section, key in (
        ("LAKEHOUSE_ROWS", "generator", "rows"),
        ("LAKEHOUSE_SEED", "generator", "seed"),
    ):
        raw = os.environ.get(env_name)
        if raw is None or raw == "":
            continue
        try:
            data.setdefault(section, {})[key] = int(raw)
        except ValueError as exc:
            raise InputError(f"{env_name} must be an integer, got {raw!r}") from exc
    return data


def load_config(path: str | Path | None = None) -> AppConfig:
    """Load configuration from ``path`` (YAML) over the built-in defaults.

    ``path=None`` loads ``config.yaml`` from the repo root when it exists,
    and plain defaults otherwise. Unknown top-level keys are ignored so an
    older config file never breaks a newer reader; malformed YAML or a
    wrong-typed value raises :class:`InputError` / ``ValueError``.
    """
    data: dict[str, Any] = _defaults_dict()
    cfg_path = Path(path) if path is not None else REPO_ROOT / "config.yaml"
    if cfg_path.is_file():
        try:
            loaded = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
        except yaml.YAMLError as exc:
            raise InputError(f"cannot parse config file {cfg_path}: {exc}") from exc
        if not isinstance(loaded, dict):
            raise InputError(f"config file {cfg_path} must contain a YAML mapping")
        data = _deep_merge(data, loaded)
    data = _coerce_env_overrides(data)

    gen = data.get("generator", {})
    paths = data.get("paths", {})
    try:
        return AppConfig(
            generator=GeneratorConfig(
                rows=int(gen["rows"]),
                seed=int(gen["seed"]),
                start_date=str(gen["start_date"]),
                date_span_days=int(gen["date_span_days"]),
                parts=tuple(gen["parts"]),
                regions=tuple(gen["regions"]),
                min_qty=int(gen["min_qty"]),
                max_qty=int(gen["max_qty"]),
            ),
            paths=Paths(
                raw_dir=Path(paths["raw_dir"]),
                curated_dir=Path(paths["curated_dir"]),
                gold_dir=Path(paths["gold_dir"]),
            ).resolve(),
            log_level=str(data.get("log_level", "INFO")),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise InputError(f"invalid config values in {cfg_path}: {exc}") from exc
