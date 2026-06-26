"""Thermal classification, expressed relative to the card's own limit so the
bands mean the same thing on a 4090 (throttles ~83C) as on an A100 (~85C)."""


def zone_for(temp: float, critical: float) -> str:
    headroom = critical - temp
    if headroom > 25:
        return "cool"
    if headroom > 12:
        return "steady"
    if headroom > 5:
        return "warm"
    return "hot"
