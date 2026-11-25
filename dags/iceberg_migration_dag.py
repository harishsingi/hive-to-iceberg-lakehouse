"""Airflow DAG: hive_to_iceberg_migration.

Daily pipeline: land synthetic raw data -> curate with data-quality gates
-> build the gold aggregate -> promote the snapshot. Each task calls the
same functions the CLI uses (``src.generate_data`` / ``src.migrate`` /
``src.aggregate``), so the DAG and the local run can never drift apart.

Airflow is an optional dependency: if it is not installed the module still
imports cleanly and ``DAG`` is ``None``, so local development and tests do
not need Airflow. Install it with ``pip install apache-airflow`` to run
the DAG for real.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

DAG_ID = "hive_to_iceberg_migration"
SCHEDULE = timedelta(days=1)
START_DATE = datetime(2024, 1, 1)
RETRIES = 2
RETRY_DELAY = timedelta(minutes=5)

try:
    from airflow import DAG
    from airflow.operators.python import PythonOperator
except ImportError:  # Airflow not installed (local dev / tests)
    DAG = None  # type: ignore[assignment]
    PythonOperator = None  # type: ignore[assignment]
    logger.info("apache-airflow not installed; DAG definition skipped")

# Imported lazily inside task callables so importing this module never
# requires the pipeline config to exist.
from src import aggregate, generate_data, migrate  # noqa: E402


def _task_generate(**_context):
    """Land the next batch of synthetic raw transactions."""
    return str(generate_data.main(["--rows", "5000"]))


def _task_curate(**_context):
    """Validate, quarantine, and snapshot the raw batch."""
    summary = migrate.main([])
    if summary["metrics"]["rows_quarantined"]:
        logger.warning(
            "curated with %s quarantined rows (see quarantine.csv)",
            summary["metrics"]["rows_quarantined"],
        )
    return summary


def _task_build_gold(**_context):
    """Rebuild the monthly demand aggregate from the curated table."""
    return str(aggregate.main([]))


def _task_promote(**_context):
    """Log the current snapshot id; promotion is the snapshot itself.

    In production this step would register the new snapshot as the
    current table version in the Iceberg catalog and notify downstream
    readers. Locally the manifest written by ``migrate`` already is the
    promoted version, so this task records that fact in the DAG log.
    """
    from src.config import load_config
    from src.snapshots import latest_snapshot

    snapshot = latest_snapshot(load_config().paths.curated_dir)
    if snapshot is None:
        raise RuntimeError("no snapshot to promote; curate step produced none")
    logger.info("promoted snapshot %s (%d rows)", snapshot.snapshot_id, snapshot.rows)
    return snapshot.snapshot_id


dag = None
if DAG is not None:
    with DAG(
        dag_id=DAG_ID,
        schedule=SCHEDULE,
        start_date=START_DATE,
        catchup=False,
        default_args={"retries": RETRIES, "retry_delay": RETRY_DELAY},
        tags=["lakehouse", "iceberg", "portfolio"],
        doc_md=__doc__,
    ) as dag:
        land_raw = PythonOperator(task_id="land_raw", python_callable=_task_generate)
        spark_curate = PythonOperator(task_id="spark_curate", python_callable=_task_curate)
        build_gold = PythonOperator(task_id="build_gold", python_callable=_task_build_gold)
        promote_snapshot = PythonOperator(
            task_id="promote_snapshot", python_callable=_task_promote
        )
        land_raw >> spark_curate >> build_gold >> promote_snapshot
