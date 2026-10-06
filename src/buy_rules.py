"""Pure, fail-closed checks. Eligibility never executes a purchase."""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from urllib.parse import urlsplit

@dataclass(frozen=True)
class BuyDecision:
    eligible: bool
    reason: str

def positive_money(value):
    if value is None or isinstance(value, bool):
        return None
    try:
        amount = Decimal(str(value))
        return amount if amount.is_finite() and amount > 0 else None
    except (InvalidOperation, ValueError, TypeError):
        return None

def positive_quantity(value):
    return value if type(value) is int and value > 0 else None

def evaluate_buy_rule(snap, item: dict, *, cart_only=True) -> BuyDecision:
    """Validate an explicit quantity-one cart test; never authorizes payment."""
    def blocked(reason):
        return BuyDecision(False, reason)
    try:
        parsed = urlsplit(snap.url)
        if (parsed.scheme != 'https' or parsed.hostname not in
                {'toymate.com.au', 'www.toymate.com.au'} or
                parsed.username or parsed.password or parsed.port not in (None, 443)):
            return blocked('Untrusted product URL')
    except ValueError:
        return blocked('Invalid product URL')
    if item.get('url') and item['url'] != snap.url:
        return blocked('Product URL mismatch')
    if snap.retailer != 'toymate-au' or item.get('retailer', 'toymate-au') != snap.retailer:
        return blocked('Toymate adapter only')
    if snap.first_party is not True:
        return blocked('First-party retailer not confirmed')
    if snap.in_stock is not True:
        return blocked('Online stock not verified')
    if snap.currency != 'AUD' or item.get('currency', 'AUD') != 'AUD':
        return blocked('Currency mismatch')
    price, ceiling = positive_money(snap.price), positive_money(item.get('max_price'))
    if price is None or ceiling is None:
        return blocked('Price or maximum not verified')
    if price > ceiling:
        return blocked('Price exceeds configured maximum')
    expected = item.get('expected_sku')
    if not isinstance(expected, str) or not expected or expected != expected.strip():
        return blocked('Exact SKU/PID required')
    if snap.sku != expected:
        return blocked('SKU/PID mismatch')
    quantity = positive_quantity(item.get('quantity', 1))
    maximum = positive_quantity(item.get('max_quantity', 1))
    if quantity is None or maximum is None or quantity > maximum:
        return blocked('Invalid quantity or quantity exceeds maximum')
    if cart_only and quantity != 1:
        return blocked('Only quantity 1 is permitted by the cart adapter')
    return BuyDecision(True, 'Eligible for cart attempt only' if cart_only else 'Purchase controls satisfied; no execution configured')

def evaluate_purchase(snap, item: dict, settings: dict | None = None) -> BuyDecision:
    """Require explicit opt-in and verified evidence; no spending side effects."""
    settings = settings or {}
    if settings.get('purchases_enabled') is not True:
        return BuyDecision(False, 'Master purchase switch OFF')
    if item.get('auto_buy') is not True:
        return BuyDecision(False, 'Auto-buy OFF')
    if item.get('enabled') not in (True, 1) or item.get('discovered'):
        return BuyDecision(False, 'Explicit enabled product rule required')
    if any(k not in item for k in ('max_quantity', 'quantity', 'currency', 'url')):
        return BuyDecision(False, 'Complete purchase rule required')
    if getattr(snap, 'security_blocked', False) is not False:
        return BuyDecision(False, 'Retailer security verification required; stop')
    if getattr(snap, 'stock_verified', False) is not True:
        return BuyDecision(False, 'Purchase stock evidence not verified')
    return evaluate_buy_rule(snap, item, cart_only=False)
