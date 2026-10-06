from __future__ import annotations

from dataclasses import dataclass

from .alert_policy import refine_snapshot
from .buy_rules import evaluate_buy_rule
from .retailers import parse_product


@dataclass
class CartAttempt:
    ok: bool
    message: str
    title: str = ""
    price: float | None = None
    sku: str | None = None


async def add_verified_toymate_item(page, item: dict) -> CartAttempt:
    """Add one verified item to a Toymate cart. Does not proceed beyond cart."""
    await page.goto(item["url"], wait_until="domcontentloaded", timeout=30000)
    await page.wait_for_timeout(1200)

    html = await page.content()
    snap = parse_product(page.url, html, "toymate-au")
    snap = refine_snapshot(snap, html, item)
    decision = evaluate_buy_rule(snap, item)
    if not decision.eligible:
        return CartAttempt(False, decision.reason, snap.title, snap.price, snap.sku)

    form = page.locator('form:has(input[name="id"]):has(input[name="quantity"])').first
    if await form.count() != 1:
        return CartAttempt(False, "Primary product form not found", snap.title, snap.price, snap.sku)

    quantity = form.locator('input[name="quantity"]')
    if await quantity.count():
        await quantity.fill("1")

    button = form.locator('button[type="submit"]').first
    if await button.count() != 1 or await button.is_disabled():
        return CartAttempt(False, "Add-to-cart control unavailable", snap.title, snap.price, snap.sku)

    await button.click()
    await page.wait_for_timeout(1200)
    return CartAttempt(True, "Added one verified item to cart", snap.title, snap.price, snap.sku)

