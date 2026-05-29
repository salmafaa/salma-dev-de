import glob
import os
from datetime import datetime, timedelta

import pendulum
from airflow.decorators import dag, task
from airflow.providers.postgres.hooks.postgres import PostgresHook
from airflow.sensors.filesystem import FileSensor

DATA_DIR = os.environ.get("AGENCY_DATA_DIR", "/opt/airflow/data")
CONN_ID = "postgres_entropi"


@dag(
    dag_id="agency_ingestion",
    schedule="0 2 * * 1",   # Senin 09:00 WIB = 02:00 UTC
    start_date=pendulum.datetime(2025, 1, 1, tz="UTC"),
    catchup=False,
    tags=["entropi", "agency"],
    default_args={
        "owner": "entroli",
        "depends_on_past": False,
    },
)
def agency_ingestion():

    # --- Sensor: tunggu file .xlsx di folder data/ ---
    wait_for_file = FileSensor(
        task_id="wait_for_xlsx",
        filepath=f"{DATA_DIR}/*.xlsx",
        poke_interval=60,       # cek tiap 60 detik
        timeout=60 * 60 * 6,    # timeout 6 jam
        mode="reschedule",
        fs_conn_id="fs_default",
    )

    @task()
    def extract_excel() -> dict:
        import pandas as pd
        import numpy as np
        
        files = sorted(glob.glob(f"{DATA_DIR}/*.xlsx"))
        if not files:
            raise FileNotFoundError(f"No .xlsx found in {DATA_DIR}")
        filepath = files[-1]

        try:
            df = pd.read_excel(filepath, sheet_name="Agency", header=0)
        except ValueError as e:
            raise ValueError(f"Sheet 'Agency' not found: {e}")

        df.columns = [str(c).strip() for c in df.columns]
        
        # ← Ganti NaN dengan None supaya bisa di-serialize ke JSON
        df = df.where(pd.notna(df), None)
        
        rows = df.to_dict(orient="records")
        
        # ← Pastikan tidak ada NaN tersisa
        clean_rows = []
        for row in rows:
            clean_row = {k: (None if isinstance(v, float) and np.isnan(v) else v) for k, v in row.items()}
            clean_rows.append(clean_row)
        
        return {"filepath": filepath, "rows": clean_rows}

    @task()
    def validate_rows(raw: dict) -> dict:
        import sys
        sys.path.insert(0, '/opt/airflow')
        
        from src.ingestion import ingest_agency_excel

        hook = PostgresHook(postgres_conn_id=CONN_ID)
        records = hook.get_records("SELECT username, id FROM creators WHERE status = 'ACTIVE'")
        creator_lookup = {row[0].lstrip("@"): row[1] for row in records}

        valid, invalid = ingest_agency_excel(
            filepath=raw["filepath"],
            creator_lookup=creator_lookup,
        )
        return {"valid": valid, "invalid": invalid}

    @task(retries=2, retry_delay=timedelta(minutes=5))
    def load_to_postgres(validated: dict) -> int:
        """Upsert valid rows ke creator_daily_performance + log ke data_sync_logs."""
        from datetime import date

        valid_rows: list[dict] = validated["valid"]
        invalid_rows: list[dict] = validated["invalid"]

        hook = PostgresHook(postgres_conn_id=CONN_ID)
        conn = hook.get_conn()
        cursor = conn.cursor()

        rows_inserted = 0
        rows_skipped = len(invalid_rows)

        upsert_sql = """
            INSERT INTO creator_daily_performance
                (creator_id, report_date, total_gmv, affiliate_live_gmv,
                 affiliate_video_gmv, total_orders)
            VALUES (%(creator_id)s, %(report_date)s, %(total_gmv)s,
                    %(affiliate_live_gmv)s, %(affiliate_video_gmv)s, %(total_orders)s)
            ON CONFLICT (creator_id, report_date) DO UPDATE SET
                total_gmv           = EXCLUDED.total_gmv,
                affiliate_live_gmv  = EXCLUDED.affiliate_live_gmv,
                affiliate_video_gmv = EXCLUDED.affiliate_video_gmv,
                total_orders        = EXCLUDED.total_orders,
                updated_at          = NOW();
        """

        for row in valid_rows:
            # Convert period "2025-W03" ke report_date (Senin minggu itu)
            try:
                year, week = row["period"].split("-W")
                report_date = date.fromisocalendar(int(year), int(week), 1)
            except Exception:
                rows_skipped += 1
                continue

            cursor.execute(upsert_sql, {
                "creator_id": row["creator_id"],
                "report_date": report_date,
                "total_gmv": row["total_gmv"],
                "affiliate_live_gmv": row["affiliate_live_gmv"],
                "affiliate_video_gmv": row["affiliate_video_gmv"],
                "total_orders": row["total_orders"],
            })
            rows_inserted += 1

        # Insert audit log
        cursor.execute(
            """
            INSERT INTO data_sync_logs
                (sync_type, source, rows_processed, rows_failed, status, completed_at)
            VALUES (%s, %s, %s, %s, %s, NOW())
            """,
            ("CREATOR_DAILY", "TIKTOK_REPORT", rows_inserted, rows_skipped, "COMPLETED"),
        )

        conn.commit()
        cursor.close()
        conn.close()

        return rows_inserted

    @task()
    def refresh_matview(rows_loaded: int) -> None:
        """Refresh materialized view setelah load sukses."""
        hook = PostgresHook(postgres_conn_id=CONN_ID)
        hook.run("REFRESH MATERIALIZED VIEW CONCURRENTLY mv_weekly_gmv_by_tier;")

    # --- Task dependency ---
    raw = extract_excel()
    validated = validate_rows(raw)
    loaded = load_to_postgres(validated)
    refresh_matview(loaded)

    # FileSensor harus jalan dulu sebelum extract
    wait_for_file >> raw


agency_ingestion()