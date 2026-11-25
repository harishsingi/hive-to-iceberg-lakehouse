# Hive to Apache Iceberg Lakehouse Migration

A runnable local simulation of migrating Hive tables to Apache Iceberg:
ACID-style atomic snapshots, schema validation, data-quality gates with
quarantine, snapshot time travel, and a gold aggregate, orchestrated in
stages. All data is synthetic, all code is original and clean-room, and no
proprietary code, data, schema names, or internal system details from any
employer are included.

**What this actually is:** a plain-Python pipeline (standard library plus
PyYAML) that mirrors Iceberg semantics with files on disk: the curated
table is a CSV plus a `snapshot.json` manifest and an append-only
`snapshots.jsonl` log. It is **not** Spark, Iceberg, S3, or Airflow, and it
does not claim to be; the module layout and the DAG are structured so the
same stages map onto those systems in production. No network calls and no
credentials are involved anywhere.

**Original context:** Data platform rebuild migrating Hive tables to Apache
Iceberg to get ACID transactions, schema evolution and snapshot time
travel, with PySpark pipelines orchestrated by Airflow and an ML demand
product built on top.

**This portfolio version:** Synthetic automotive parts and service
transactions only. The data is invented: part names, regions, quantities
and dates drawn from small fixed pools with a seeded RNG, so runs are
reproducible.

## Architecture

![Iceberg lakehouse architecture](docs/iceberg-lakehouse.svg)
```
raw (CSV landing) -> bronze (validated) -> silver (curated + snapshot) -> gold (monthly aggregates)
                         |                          |
                    quarantine.csv           snapshot.json / snapshots.jsonl
                    (bad rows + reason)      (time-travel reads)
```

| Module | Responsibility |
|---|---|
| `src/generate_data.py` | Seeded synthetic raw-data generator (writes `data/raw/transactions.csv`) |
| `src/schema.py` | The transaction schema: column contract + per-row validation rules |
| `src/quality.py` | Splits rows into valid / quarantined; duplicate `txn_id` detection; run metrics |
| `src/snapshots.py` | Content-hashed snapshot ids, manifests, append-only log, `latest`/id resolution |
| `src/migrate.py` | Bronze-to-silver curation: validate, quarantine, write curated + snapshot |
| `src/aggregate.py` | Silver-to-gold: monthly demand by part and region |
| `src/time_travel.py` | Read a pinned snapshot (`--snapshot <id>` or `latest`), or `--list` all of them |
| `src/config.py` | Configuration (defaults, `config.yaml`, `LAKEHOUSE_*` env overrides) |
| `src/exceptions.py` | Typed errors: `InputError`, `SchemaValidationError`, `DataQualityError`, `SnapshotNotFoundError` |
| `src/logging_config.py` | One logging setup shared by every module (no `print` for operational output) |
| `dags/iceberg_migration_dag.py` | Airflow DAG over the same functions; imports cleanly without Airflow installed |

## Setup

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"        # runtime dep: PyYAML; dev deps: pytest, ruff
```

Python 3.10+ required. No other services, accounts, or credentials needed.

## Run

```bash
python -m src.generate_data --rows 5000 --out data/raw
python -m src.migrate --input data/raw --output data/curated
python -m src.aggregate --input data/curated --output data/gold
python -m src.time_travel --snapshot latest
python -m src.time_travel --list
```

Defaults come from `config.yaml` at the repo root, so the bare commands
also work (`python -m src.generate_data`, then `python -m src.migrate`,
...). `LAKEHOUSE_ROWS` / `LAKEHOUSE_SEED` override the generator from the
environment. Every command accepts `--help`, `--config <file>`, and
`--log-level`.

### Idempotency

A snapshot id is a content hash of the valid rows. Re-running `migrate`
on unchanged input reproduces the same id and skips the rewrite; changed
input creates a new snapshot whose manifest records the previous one as
its parent. The snapshot log is append-only and never rewritten.

### Data quality

Bad rows never abort a run and are never silently dropped: they go to
`data/curated/quarantine.csv` with a `dq_reason` column, and the counts
(rows in / valid / quarantined, with a per-reason breakdown) are logged
and stored in the snapshot manifest. Only the degenerate case, zero
valid rows, aborts the run with `DataQualityError`.

## Test

```bash
python -m pytest tests/ -q     # 59 tests covering every module
python -m ruff check src tests dags conftest.py
```

## Key ideas demonstrated
- Partition evolution and schema evolution without rewriting history
- Snapshot isolation: readers pin a snapshot, writers append a new one
- Idempotent, re-runnable jobs with content-hashed snapshots
- Data quality gates before a snapshot is promoted, with quarantine instead of silent drops

## Before / After

Hover any component to see what it is and why it is needed.

![Before / After architecture](docs/before-after-elaborated.svg)
<details>
<summary><b>Backfill + snapshot — click to expand the 4 steps</b></summary>

Collapsed, this is just: Hive source -> PySpark migrate -> Iceberg on S3 -> Snapshots

1. The original Hive tables stay as the source, so nothing is lost during migration.
2. PySpark jobs migrate tables in stages, so each table is proven before it moves.
3. Iceberg tables on S3 give ACID transactions, so writes are atomic and safe.
4. Every write creates a snapshot, so any earlier version can be read or rolled back to; readers pin a snapshot, so the old and new versions can be compared before cutover.
</details>

### Earlier issues, risk, and impact after

| Aspect | Detail |
|---|---|
| Earlier issues | Hive tables with no transactions, so a failed write could leave partial data; a static metastore where schema changes needed rewrites; no way to read an earlier snapshot, so a bad load could not be rolled back cleanly; backfills run by hand, easy to get wrong and hard to repeat; no quality gate before a snapshot is promoted; readers and writers shared the same state, so queries could see half-written data. |
| Risk | A failed write could leave partial data behind; a bad load could become the current version with no clean rollback; a hand-run backfill that went wrong had to be redone from scratch; changing a schema meant rewriting history. |
| Impact after | Writes are atomic with ACID transactions; schema and partition changes apply without rewriting history; snapshot isolation lets readers pin a version while writers append a new one; DQ gates run before a snapshot is promoted; Airflow orchestrates the migration in stages. |
