# Airflow DAG definition (illustrative, mirrors production orchestration pattern)
# schedule: daily; tasks: generate/land -> curate -> quality_gate -> promote_snapshot
DAG_ID="hive_to_iceberg_migration"
TASKS=["land_raw","spark_curate","quality_gate","promote_snapshot"]
