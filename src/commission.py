from decimal import Decimal, ROUND_HALF_UP

QUANTIZE_4 = Decimal("0.0001")

TIERS = [
    (Decimal("100000000"), Decimal("0.11")),
    (Decimal("50000000"),  Decimal("0.09")),
    (Decimal("10000000"),  Decimal("0.07")),
    (Decimal("0"),         Decimal("0.05")),
]

LIVE_BONUS_RATE = Decimal("0.015")


def calculate_agency_commission(
    monthly_gmv: Decimal,
    live_gmv: Decimal,
) -> dict:
    """
    Calculate tiered commission + LIVE bonus.

    Returns:
        tier_rate, base_commission, live_bonus, total_commission
    """
    if monthly_gmv <= Decimal("0"):
        return {
            "tier_rate": Decimal("0.05"),
            "base_commission": Decimal("0.0000"),
            "live_bonus": Decimal("0.0000"),
            "total_commission": Decimal("0.0000"),
        }

    tier_rate = Decimal("0.05")
    for threshold, rate in TIERS:
        if monthly_gmv >= threshold:
            tier_rate = rate
            break

    base_commission = (monthly_gmv * tier_rate).quantize(QUANTIZE_4, rounding=ROUND_HALF_UP)
    live_bonus = (live_gmv * LIVE_BONUS_RATE).quantize(QUANTIZE_4, rounding=ROUND_HALF_UP)
    total_commission = (base_commission + live_bonus).quantize(QUANTIZE_4, rounding=ROUND_HALF_UP)

    return {
        "tier_rate": tier_rate,
        "base_commission": base_commission,
        "live_bonus": live_bonus,
        "total_commission": total_commission,
    }