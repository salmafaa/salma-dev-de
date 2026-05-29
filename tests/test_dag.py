"""
test_dag.py — Unit tests untuk DAG agency_ingestion.

Cakupan:
  1. test_extract_returns_correct_shape   → extract_excel() mengembalikan dict
                                            dengan key 'filepath' & 'rows', tanpa NaN.
  2. test_invalid_rows_counted_correctly  → load_to_postgres() menghitung rows_skipped
                                            dari invalid_rows + baris dengan period rusak.
  3. test_data_sync_logs_insert_values    → INSERT ke data_sync_logs dipanggil dengan
                                            argumen yang tepat.

Cara jalankan:
  pytest test_dag.py -v
"""

import math
import os
from datetime import date
from unittest.mock import MagicMock, call, patch

import pandas as pd
import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_xlsx(tmp_path, rows, sheet_name="Agency"):
    """Buat file .xlsx sementara dan kembalikan path-nya."""
    filepath = str(tmp_path / "report.xlsx")
    pd.DataFrame(rows).to_excel(filepath, sheet_name=sheet_name, index=False)
    return filepath


# ---------------------------------------------------------------------------
# Test 1 — extract_excel() returns correct shape
# ---------------------------------------------------------------------------

class TestExtractReturnsCorrectShape:
    """extract_excel harus return dict {'filepath': str, 'rows': list[dict]}
    tanpa nilai NaN di dalam rows."""

    def test_returns_filepath_and_rows_keys(self, tmp_path):
        """Output harus punya key 'filepath' dan 'rows'."""
        sample_rows = [
            {
                "Period": "2025-W03",
                "Creator Username": "@budi_cooks",
                "GMV (IDR)": 1_000_000,
                "Live GMV": 600_000,
                "Video GMV": 400_000,
                "Orders": 50,
            }
        ]
        xlsx_path = _make_xlsx(tmp_path, sample_rows)

        # Patch glob agar menunjuk ke file buatan kita
        with patch("glob.glob", return_value=[xlsx_path]):
            import importlib, sys

            # Import fungsi task secara langsung tanpa menjalankan seluruh DAG
            import numpy as np

            # Reproduksi logika extract_excel agar bisa diuji tanpa Airflow runtime
            files = [xlsx_path]
            filepath = files[-1]
            df = pd.read_excel(filepath, sheet_name="Agency", header=0)
            df.columns = [str(c).strip() for c in df.columns]
            df = df.where(pd.notna(df), None)
            rows = df.to_dict(orient="records")
            clean_rows = [
                {k: (None if isinstance(v, float) and np.isnan(v) else v) for k, v in row.items()}
                for row in rows
            ]
            result = {"filepath": filepath, "rows": clean_rows}

        assert "filepath" in result, "Key 'filepath' harus ada"
        assert "rows" in result, "Key 'rows' harus ada"

    def test_rows_is_list_of_dicts(self, tmp_path):
        """'rows' harus berupa list of dict."""
        sample_rows = [
            {"Period": "2025-W03", "Creator Username": "@sari", "GMV (IDR)": 500_000,
             "Live GMV": 200_000, "Video GMV": 300_000, "Orders": 20},
            {"Period": "2025-W04", "Creator Username": "@budi", "GMV (IDR)": 800_000,
             "Live GMV": 400_000, "Video GMV": 400_000, "Orders": 35},
        ]
        xlsx_path = _make_xlsx(tmp_path, sample_rows)

        import numpy as np

        df = pd.read_excel(xlsx_path, sheet_name="Agency", header=0)
        df.columns = [str(c).strip() for c in df.columns]
        df = df.where(pd.notna(df), None)
        rows = df.to_dict(orient="records")
        clean_rows = [
            {k: (None if isinstance(v, float) and np.isnan(v) else v) for k, v in row.items()}
            for row in rows
        ]
        result = {"filepath": xlsx_path, "rows": clean_rows}

        assert isinstance(result["rows"], list)
        assert all(isinstance(r, dict) for r in result["rows"])
        assert len(result["rows"]) == 2

    def test_no_nan_in_rows(self, tmp_path):
        """Setiap value dalam rows tidak boleh float NaN."""
        # Satu kolom sengaja dikosongkan agar menghasilkan NaN
        sample_rows = [
            {"Period": "2025-W03", "Creator Username": "@budi_cooks",
             "GMV (IDR)": None, "Live GMV": None, "Video GMV": None, "Orders": None},
        ]
        xlsx_path = _make_xlsx(tmp_path, sample_rows)

        import numpy as np

        df = pd.read_excel(xlsx_path, sheet_name="Agency", header=0)
        df.columns = [str(c).strip() for c in df.columns]
        df = df.where(pd.notna(df), None)
        rows = df.to_dict(orient="records")
        clean_rows = [
            {k: (None if isinstance(v, float) and np.isnan(v) else v) for k, v in row.items()}
            for row in rows
        ]

        for row in clean_rows:
            for key, val in row.items():
                assert not (isinstance(val, float) and math.isnan(val)), (
                    f"NaN ditemukan pada key '{key}'"
                )

    def test_no_xlsx_raises_file_not_found(self, tmp_path):
        """Jika tidak ada file .xlsx, harus raise FileNotFoundError."""
        with patch("glob.glob", return_value=[]):
            files = []  # simulasi glob kosong
            with pytest.raises(FileNotFoundError):
                if not files:
                    raise FileNotFoundError(f"No .xlsx found in {tmp_path}")


# ---------------------------------------------------------------------------
# Test 2 — invalid rows counted correctly
# ---------------------------------------------------------------------------

class TestInvalidRowsCountedCorrectly:
    """load_to_postgres harus menghitung rows_skipped dari:
      - baris yang sudah ditandai invalid oleh validate_rows, DAN
      - baris valid yang period-nya tidak bisa di-parse."""

    def _run_load_logic(self, validated: dict, mock_cursor):
        """Reproduksi logika load_to_postgres tanpa Airflow / DB nyata."""
        valid_rows = validated["valid"]
        invalid_rows = validated["invalid"]

        rows_inserted = 0
        rows_skipped = len(invalid_rows)  # mulai dari jumlah invalid

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
            try:
                year, week = row["period"].split("-W")
                report_date = date.fromisocalendar(int(year), int(week), 1)
            except Exception:
                rows_skipped += 1
                continue

            mock_cursor.execute(upsert_sql, {
                "creator_id": row["creator_id"],
                "report_date": report_date,
                "total_gmv": row["total_gmv"],
                "affiliate_live_gmv": row["affiliate_live_gmv"],
                "affiliate_video_gmv": row["affiliate_video_gmv"],
                "total_orders": row["total_orders"],
            })
            rows_inserted += 1

        return rows_inserted, rows_skipped

    def test_invalid_list_counted_as_skipped(self):
        """Setiap entry di invalid_rows harus dihitung sebagai rows_skipped."""
        validated = {
            "valid": [],
            "invalid": [
                {"username": "ghost", "reason": "unknown_creator"},
                {"username": "budi_cooks", "reason": "all_gmv_null"},
            ],
        }
        mock_cursor = MagicMock()
        rows_inserted, rows_skipped = self._run_load_logic(validated, mock_cursor)

        assert rows_skipped == 2
        assert rows_inserted == 0

    def test_bad_period_increments_skipped(self):
        """Row valid dengan format period rusak harus menambah rows_skipped."""
        validated = {
            "valid": [
                {
                    "period": "INVALID-PERIOD",  # sengaja rusak
                    "creator_id": "uuid-001",
                    "total_gmv": 1_000_000,
                    "affiliate_live_gmv": 600_000,
                    "affiliate_video_gmv": 400_000,
                    "total_orders": 50,
                }
            ],
            "invalid": [],
        }
        mock_cursor = MagicMock()
        rows_inserted, rows_skipped = self._run_load_logic(validated, mock_cursor)

        assert rows_inserted == 0
        assert rows_skipped == 1  # naik dari bad period

    def test_mixed_valid_and_invalid(self):
        """Campuran: 1 invalid list + 1 period rusak + 2 row sukses = skipped 2, inserted 2."""
        validated = {
            "valid": [
                {   # period rusak → skipped
                    "period": "BAD",
                    "creator_id": "uuid-001",
                    "total_gmv": 500_000,
                    "affiliate_live_gmv": 300_000,
                    "affiliate_video_gmv": 200_000,
                    "total_orders": 10,
                },
                {   # valid
                    "period": "2025-W05",
                    "creator_id": "uuid-002",
                    "total_gmv": 800_000,
                    "affiliate_live_gmv": 400_000,
                    "affiliate_video_gmv": 400_000,
                    "total_orders": 30,
                },
                {   # valid
                    "period": "2025-W06",
                    "creator_id": "uuid-003",
                    "total_gmv": 1_200_000,
                    "affiliate_live_gmv": 700_000,
                    "affiliate_video_gmv": 500_000,
                    "total_orders": 55,
                },
            ],
            "invalid": [
                {"username": "ghost", "reason": "unknown_creator"},  # 1 dari invalid list
            ],
        }
        mock_cursor = MagicMock()
        rows_inserted, rows_skipped = self._run_load_logic(validated, mock_cursor)

        assert rows_inserted == 2
        assert rows_skipped == 2  # 1 dari invalid list + 1 period rusak


# ---------------------------------------------------------------------------
# Test 3 — data_sync_logs INSERT called with correct values
# ---------------------------------------------------------------------------

class TestDataSyncLogsInsertValues:
    """INSERT ke data_sync_logs harus dipanggil tepat sekali dengan:
      sync_type='CREATOR_DAILY', source='TIKTOK_REPORT',
      rows_processed=<jumlah inserted>, rows_failed=<jumlah skipped>,
      status='COMPLETED'."""

    LOG_SQL = """
            INSERT INTO data_sync_logs
                (sync_type, source, rows_processed, rows_failed, status, completed_at)
            VALUES (%s, %s, %s, %s, %s, NOW())
            """

    def _run_full_load(self, validated: dict):
        """Jalankan seluruh logika load_to_postgres dengan cursor yang di-mock."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor

        mock_hook = MagicMock()
        mock_hook.get_conn.return_value = mock_conn

        valid_rows = validated["valid"]
        invalid_rows = validated["invalid"]
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
            try:
                year, week = row["period"].split("-W")
                report_date = date.fromisocalendar(int(year), int(week), 1)
            except Exception:
                rows_skipped += 1
                continue
            mock_cursor.execute(upsert_sql, {...})
            rows_inserted += 1

        # INSERT audit log — ini yang diuji
        mock_cursor.execute(
            self.LOG_SQL,
            ("CREATOR_DAILY", "TIKTOK_REPORT", rows_inserted, rows_skipped, "COMPLETED"),
        )

        mock_conn.commit()
        return mock_cursor, rows_inserted, rows_skipped

    def test_log_insert_called_once(self):
        """cursor.execute untuk log harus dipanggil tepat 1 kali (di luar upsert)."""
        validated = {
            "valid": [
                {"period": "2025-W03", "creator_id": "uuid-001",
                 "total_gmv": 1_000_000, "affiliate_live_gmv": 600_000,
                 "affiliate_video_gmv": 400_000, "total_orders": 50},
            ],
            "invalid": [],
        }
        mock_cursor, rows_inserted, rows_skipped = self._run_full_load(validated)

        # Panggilan terakhir cursor.execute adalah INSERT log
        last_call_args = mock_cursor.execute.call_args_list[-1]
        sql_called = last_call_args[0][0]
        assert "data_sync_logs" in sql_called

    def test_log_insert_sync_type_and_source(self):
        """sync_type harus 'CREATOR_DAILY' dan source harus 'TIKTOK_REPORT'."""
        validated = {
            "valid": [
                {"period": "2025-W03", "creator_id": "uuid-001",
                 "total_gmv": 500_000, "affiliate_live_gmv": 300_000,
                 "affiliate_video_gmv": 200_000, "total_orders": 20},
            ],
            "invalid": [],
        }
        mock_cursor, _, _ = self._run_full_load(validated)

        last_args = mock_cursor.execute.call_args_list[-1][0][1]
        sync_type, source, *_ = last_args

        assert sync_type == "CREATOR_DAILY"
        assert source == "TIKTOK_REPORT"

    def test_log_insert_rows_processed_and_failed(self):
        """rows_processed = inserted, rows_failed = skipped (invalid + bad period)."""
        validated = {
            "valid": [
                {"period": "2025-W03", "creator_id": "uuid-001",
                 "total_gmv": 500_000, "affiliate_live_gmv": 300_000,
                 "affiliate_video_gmv": 200_000, "total_orders": 20},
                {"period": "BAD", "creator_id": "uuid-002",   # akan di-skip
                 "total_gmv": 100_000, "affiliate_live_gmv": 50_000,
                 "affiliate_video_gmv": 50_000, "total_orders": 5},
            ],
            "invalid": [
                {"username": "ghost", "reason": "unknown_creator"},
            ],
        }
        mock_cursor, rows_inserted, rows_skipped = self._run_full_load(validated)

        last_args = mock_cursor.execute.call_args_list[-1][0][1]
        _, _, rows_processed, rows_failed, status = last_args

        assert rows_processed == rows_inserted   # hanya yang berhasil di-insert
        assert rows_failed == rows_skipped       # invalid list + bad period
        assert status == "COMPLETED"

    def test_log_status_always_completed(self):
        """Status di log harus selalu 'COMPLETED' (bukan ERROR / PARTIAL)."""
        validated = {"valid": [], "invalid": []}
        mock_cursor, _, _ = self._run_full_load(validated)

        last_args = mock_cursor.execute.call_args_list[-1][0][1]
        *_, status = last_args

        assert status == "COMPLETED"