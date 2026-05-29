import pandas as pd
from decimal import Decimal, ROUND_HALF_UP, InvalidOperation
from typing import Optional

MONETARY_COLS = ["GMV (IDR)", "Live GMV", "Video GMV"]
RATE_COLS = ["CTR", "CVR"]
QUANTIZE_4 = Decimal("0.0001")


def _to_decimal(val) -> Optional[Decimal]:
    """Convert value to Decimal(4dp), return None if blank/invalid."""
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return None
    try:
        return Decimal(str(val)).quantize(QUANTIZE_4, rounding=ROUND_HALF_UP)
    except InvalidOperation:
        return None


def _to_float(val) -> Optional[float]:
    """Convert rate value to float, return None if blank/invalid."""
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return None
    try:
        return float(val)
    except (ValueError, TypeError):
        return None


def ingest_agency_excel(
    filepath: str,
    creator_lookup: dict[str, str],  # username (no @) -> creator_id
    sheet_name: str = "Agency",
) -> tuple[list[dict], list[dict]]:
    """
    Parse the Agency sheet of a TikTok Seller Center Excel export.

    Returns:
        valid_rows   — dicts ready to upsert into creator_daily_performance
        invalid_rows — dicts with keys: row_number, username, reason
    """
    # --- Load sheet ---
    try:
        df = pd.read_excel(filepath, sheet_name=sheet_name, header=0)
    except ValueError:
        # Sheet not found
        return [], [{"row_number": 0, "username": None, "reason": "missing_sheet"}]
    except Exception:
        return [], [{"row_number": 0, "username": None, "reason": "bad_header"}]

    # Normalise column names (strip whitespace)
    df.columns = [str(c).strip() for c in df.columns]

    required_cols = {"Period", "Creator Username", "GMV (IDR)", "Live GMV", "Video GMV", "Orders", "CTR", "CVR"}
    if not required_cols.issubset(set(df.columns)):
        return [], [{"row_number": 0, "username": None, "reason": "bad_header"}]

    valid_rows: list[dict] = []
    invalid_rows: list[dict] = []

    for idx, row in df.iterrows():
        row_number = int(idx) + 2  # Excel 1-based + header row

        raw_username = str(row.get("Creator Username", "")).strip()
        username_clean = raw_username.lstrip("@")

        # Resolve GMV values first to check all-null
        gmv_vals = {col: _to_decimal(row.get(col)) for col in MONETARY_COLS}
        all_gmv_null = all(v is None for v in gmv_vals.values())

        if all_gmv_null:
            invalid_rows.append({
                "row_number": row_number,
                "username": username_clean or None,
                "reason": "all_gmv_null",
            })
            continue

        if username_clean not in creator_lookup:
            invalid_rows.append({
                "row_number": row_number,
                "username": username_clean,
                "reason": "unknown_creator",
            })
            continue

        creator_id = creator_lookup[username_clean]

        valid_rows.append({
            "creator_id": creator_id,
            "period": str(row.get("Period", "")).strip(),
            "total_gmv": gmv_vals["GMV (IDR)"] or Decimal("0.0000"),
            "affiliate_live_gmv": gmv_vals["Live GMV"] or Decimal("0.0000"),
            "affiliate_video_gmv": gmv_vals["Video GMV"] or Decimal("0.0000"),
            "total_orders": int(row["Orders"]) if pd.notna(row.get("Orders")) else 0,
            "ctr": _to_float(row.get("CTR")),
            "cvr": _to_float(row.get("CVR")),
        })

    return valid_rows, invalid_rows