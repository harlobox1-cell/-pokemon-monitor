from __future__ import annotations

from dataclasses import dataclass


@dataclass
class BuyDecision:
    eligible: bool
    reason: str


def evaluate_buy_rule(snap, item: dict) -> BuyDecision:
    """Fail-closed decision layer for a future cart adapter."""
    if snap.retailer != "toymate-au":
        return BuyDecision(False, "Toymate adapter only")
    if not snap.first_party:
        return BuyDecision(False, "First-party retailer not confirmed")
    if snap.in_stock is not True:
        return BuyDecision(False, "Online stock not verified")
    if snap.currency != item.get("currency", "AUD"):
        return BuyDecision(False, "Currency mismatch")
    if snap.price is None or snap.price <= 0:
        return BuyDecision(False, "Price not verified")
    ceiling = item.get("max_price")
    if ceiling is None or snap.price > float(ceiling):
        return BuyDecision(False, "Price exceeds configured maximum")
    expected = str(item.get("expected_sku") or "").strip()
    if expected and str(snap.sku or "").strip() != expected:
        return BuyDecision(False, "SKU/PID mismatch")
    if int(item.get("quantity", 1)) != 1:
        return BuyDecision(False, "Only quantity 1 is permitted")
    return BuyDecision(True, "Eligible for cart attempt")
