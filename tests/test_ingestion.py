import os
import pytest
import pandas as pd
from decimal import Decimal
from unittest.mock import patch
import openpyxl

from src.ingestion import ingest_agency_excel

CREATOR_LOOKUP = {"budi_cooks": "uuid-001", "sari_fashion": "uuid-002"}


def make_excel(tmp_path, rows, sheet_name="Agency"):
    """Helper: buat file Excel sementara untuk test."""
    filepath = str(tmp_path / "test.xlsx")
    df = pd.DataFrame(rows)
    with pd.ExcelWriter(filepath, engine="openpyxl") as writer:
        df.to_excel(writer, sheet_name=sheet_name, index=False)
    return filepath


def test_happy_path(tmp_path):
    """Row valid harus masuk valid_rows dengan tipe Decimal."""
    rows = [{
        "Period": "2025-W03",
        "Creator Username": "@budi_cooks",
        "GMV (IDR)": 15750000,
        "Live GMV": 9000000,
        "Video GMV": 6750000,
        "Orders": 87,
        "CTR": 0.0421,
        "CVR": 0.0727,
    }]
    fp = make_excel(tmp_path, rows)
    valid, invalid = ingest_agency_excel(fp, CREATOR_LOOKUP)

    assert len(valid) == 1
    assert len(invalid) == 0
    assert valid[0]["creator_id"] == "uuid-001"
    assert isinstance(valid[0]["total_gmv"], Decimal)


def test_all_gmv_null(tmp_path):
    """Row dengan semua GMV kosong harus masuk invalid dengan reason all_gmv_null."""
    rows = [{
        "Period": "2025-W04",
        "Creator Username": "@budi_cooks",
        "GMV (IDR)": None,
        "Live GMV": None,
        "Video GMV": None,
        "Orders": None,
        "CTR": None,
        "CVR": None,
    }]
    fp = make_excel(tmp_path, rows)
    valid, invalid = ingest_agency_excel(fp, CREATOR_LOOKUP)

    assert len(valid) == 0
    assert invalid[0]["reason"] == "all_gmv_null"


def test_unknown_creator(tmp_path):
    """Username yang tidak ada di lookup harus unknown_creator."""
    rows = [{
        "Period": "2025-W03",
        "Creator Username": "@ghost_user",
        "GMV (IDR)": 5000000,
        "Live GMV": 0,
        "Video GMV": 5000000,
        "Orders": 10,
        "CTR": 0.01,
        "CVR": 0.02,
    }]
    fp = make_excel(tmp_path, rows)
    valid, invalid = ingest_agency_excel(fp, CREATOR_LOOKUP)

    assert len(valid) == 0
    assert invalid[0]["reason"] == "unknown_creator"
    assert invalid[0]["username"] == "ghost_user"


def test_monetary_precision(tmp_path):
    """GMV harus di-round ke 4 desimal dengan benar."""
    rows = [{
        "Period": "2025-W03",
        "Creator Username": "@budi_cooks",
        "GMV (IDR)": 15750000.12345,
        "Live GMV": 9000000,
        "Video GMV": 6750000,
        "Orders": 87,
        "CTR": 0.0421,
        "CVR": 0.0727,
    }]
    fp = make_excel(tmp_path, rows)
    valid, _ = ingest_agency_excel(fp, CREATOR_LOOKUP)

    assert valid[0]["total_gmv"] == Decimal("15750000.1235")


def test_missing_sheet(tmp_path):
    """Sheet tidak ada harus return invalid dengan reason missing_sheet."""
    rows = [{"col": "val"}]
    fp = make_excel(tmp_path, rows, sheet_name="OtherSheet")
    valid, invalid = ingest_agency_excel(fp, CREATOR_LOOKUP)

    assert len(valid) == 0
    assert invalid[0]["reason"] == "missing_sheet"