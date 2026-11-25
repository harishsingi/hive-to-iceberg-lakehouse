"""Tests for src.config and src.logging_config."""

import pytest

from src.config import load_config
from src.exceptions import InputError
from src.logging_config import setup_logging


def test_defaults_load_without_config_file(tmp_path, monkeypatch):
    # Point at a directory with no config.yaml: pure built-in defaults.
    monkeypatch.chdir(tmp_path)
    cfg = load_config(tmp_path / "missing.yaml")
    assert cfg.generator.rows == 1000
    assert cfg.generator.seed == 42
    assert cfg.generator.parts[0] == "brake pad"
    assert cfg.log_level == "INFO"


def test_yaml_overrides_defaults(tmp_path):
    cfg_file = tmp_path / "config.yaml"
    cfg_file.write_text(
        "generator:\n  rows: 25\n  seed: 7\npaths:\n  raw_dir: my/raw\n",
        encoding="utf-8",
    )
    cfg = load_config(cfg_file)
    assert cfg.generator.rows == 25
    assert cfg.generator.seed == 7
    assert cfg.paths.raw_dir.name == "raw"
    assert cfg.paths.raw_dir.is_absolute()
    # Untouched values keep defaults.
    assert cfg.generator.min_qty == 1


def test_env_overrides_rows_and_seed(tmp_path, monkeypatch):
    monkeypatch.setenv("LAKEHOUSE_ROWS", "33")
    monkeypatch.setenv("LAKEHOUSE_SEED", "99")
    cfg = load_config(tmp_path / "missing.yaml")
    assert cfg.generator.rows == 33
    assert cfg.generator.seed == 99


def test_bad_env_value_raises(tmp_path, monkeypatch):
    monkeypatch.setenv("LAKEHOUSE_ROWS", "not-a-number")
    with pytest.raises(InputError):
        load_config(tmp_path / "missing.yaml")


def test_malformed_yaml_raises(tmp_path):
    cfg_file = tmp_path / "config.yaml"
    cfg_file.write_text("generator: [unclosed\n", encoding="utf-8")
    with pytest.raises(InputError):
        load_config(cfg_file)


def test_invalid_values_raise(tmp_path):
    cfg_file = tmp_path / "config.yaml"
    cfg_file.write_text("generator:\n  rows: 0\n", encoding="utf-8")
    with pytest.raises(InputError):
        load_config(cfg_file)


def test_unknown_log_level_raises():
    with pytest.raises(ValueError):
        setup_logging("NOPE")


def test_setup_logging_returns_logger():
    logger = setup_logging("INFO")
    assert logger.name == "hive_to_iceberg"
