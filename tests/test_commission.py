from decimal import Decimal
import pytest
from src.commission import calculate_agency_commission


def test_bronze_tier():
    """GMV < 10jt → rate 5%."""
    result = calculate_agency_commission(Decimal("5000000"), Decimal("0"))
    assert result["tier_rate"] == Decimal("0.05")
    assert result["base_commission"] == Decimal("250000.0000")
    assert result["live_bonus"] == Decimal("0.0000")


def test_platinum_tier():
    """GMV ≥ 100jt → rate 11%."""
    result = calculate_agency_commission(Decimal("150000000"), Decimal("0"))
    assert result["tier_rate"] == Decimal("0.11")
    assert result["base_commission"] == Decimal("16500000.0000")


def test_live_bonus():
    """Live GMV dapat bonus 1.5% di atas base commission."""
    result = calculate_agency_commission(Decimal("50000000"), Decimal("20000000"))
    assert result["tier_rate"] == Decimal("0.09")
    assert result["live_bonus"] == Decimal("300000.0000")
    assert result["total_commission"] == result["base_commission"] + result["live_bonus"]


def test_zero_gmv():
    """GMV = 0 tidak boleh error, return semua 0."""
    result = calculate_agency_commission(Decimal("0"), Decimal("0"))
    assert result["total_commission"] == Decimal("0.0000")
    assert result["base_commission"] == Decimal("0.0000")