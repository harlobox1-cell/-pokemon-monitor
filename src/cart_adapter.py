from __future__ import annotations

from dataclasses import dataclass
import re

from .alert_policy import refine_snapshot
from .buy_rules import evaluate_buy_rule, trusted_product_url
from .retailers import parse_product


@dataclass
class CartAttempt:
    ok: bool
    message: str
    title: str = ""
    price: float | None = None
    sku: str | None = None
    status: str = "blocked"


async def add_verified_toymate_item(page, item: dict) -> CartAttempt:
    """One explicit cart-only attempt; no retry, checkout or payment actions."""
    url = item.get("url")
    if not trusted_product_url(url):
        return CartAttempt(False, "Exact HTTPS Toymate product URL required")
    try:
        response = await page.goto(url, wait_until="domcontentloaded", timeout=30000)
        if response is None or response.status >= 400:
            return CartAttempt(False, "Retailer page unavailable or rate limited; stopped")
        await page.wait_for_timeout(1200)
        html = await page.content()
        snap = refine_snapshot(parse_product(page.url, html, "toymate-au"), html, item)
    except Exception:
        return CartAttempt(False, "Product evidence could not be verified; stopped")

    def result(message, status="blocked"):
        return CartAttempt(False, message, snap.title, snap.price, snap.sku, status)

    decision = evaluate_buy_rule(snap, item)
    if not decision.eligible:
        return result(decision.reason)

    try:
        forms = page.locator('form:has(input[name="id"]):has(input[name="quantity"])')
        if await forms.count() != 1:
            return result("Exactly one product form required")
        form = forms.first
        identifier = form.locator('input[name="id"]')
        if (not snap.product_id or await identifier.count() != 1
                or await identifier.input_value() != snap.product_id):
            return result("Cart product ID does not match verified structured product evidence")
        quantity = form.locator('input[name="quantity"]')
        if await quantity.count() != 1:
            return result("Exactly one quantity control required")
        await quantity.fill("1")
        if await quantity.input_value() != "1":
            return result("Quantity one could not be verified")
        button = form.locator('button[type="submit"]')
        if (await button.count() != 1 or await button.is_disabled()
                or await button.get_attribute("aria-disabled") == "true"
                or not await button.is_visible()):
            return result("Add-to-cart control unavailable")
        if not re.fullmatch(r'(?:I agree\s*\+\s*)?add to (?:cart|basket)',
                            (await button.inner_text()).strip(), re.I):
            return result("Explicit add-to-cart control required")
        # Check again after UI interaction and immediately before the single click.
        html = await page.content()
        fresh = refine_snapshot(parse_product(page.url, html, "toymate-au"), html, item)
        decision = evaluate_buy_rule(fresh, item)
        if not decision.eligible:
            return result(decision.reason)
        if (fresh.product_id != snap.product_id
                or await identifier.input_value() != fresh.product_id
                or await quantity.input_value() != "1"):
            return result("Product or quantity changed before cart action")
    except Exception:
        return result("Cart controls could not be verified; stopped before click")

    try:
        await button.click()
        await page.wait_for_timeout(1200)
    except Exception:
        # A click timeout may follow a successful submission. Never try again.
        return result("Cart action outcome unknown; no retry attempted", "unconfirmed")
    if "/checkout" in page.url.lower():
        return result("Unexpected checkout navigation; stopped before payment", "safety_stop")
    # A cart link in a site header is not proof that an item was added.
    return result("Cart control clicked once; basket contents unverified; checkout not attempted", "unconfirmed")
