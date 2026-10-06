from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlparse

from .alert_policy import refine_snapshot
from .buy_rules import evaluate_buy_rule
from .retailers import infer_retailer, parse_product


@dataclass
class CartResult:
    ok: bool
    status: str
    message: str
    title: str = ""
    price: float | None = None
    sku: str | None = None
    url: str = ""


def validate_for_cart(snap, item: dict) -> tuple[bool, str]:
    """Use the shared explicit cart-test validator."""
    decision = evaluate_buy_rule(snap, item)
    return decision.eligible, decision.reason


async def toymate_cart_once(item: dict, *, headless: bool = True) -> CartResult:
    """Add one verified Toymate product to cart and STOP.

    This function deliberately never visits checkout and never submits payment.
    It is the first safe milestone for the future buyer.
    """
    url = str(item.get("url") or "")
    if infer_retailer(url) != "toymate-au":
        return CartResult(False, "blocked", "URL is not Toymate", url=url)

    from playwright.async_api import async_playwright

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=headless)
        context = await browser.new_context(locale="en-AU")
        page = await context.new_page()
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=30000)
            await page.wait_for_timeout(1200)
            html = await page.content()
            snap = parse_product(page.url, html, "toymate-au")
            snap = refine_snapshot(snap, html, item)
            allowed, reason = validate_for_cart(snap, item)
            if not allowed:
                return CartResult(False, "blocked", reason, snap.title, snap.price, snap.sku, url)

            selector = 'form:has(input[name="id"]):has(input[name="quantity"]) button[type="submit"]'
            buttons = page.locator(selector)
            count = await buttons.count()
            if count < 1:
                return CartResult(False, "failed", "Primary Toymate add-to-cart control not found", snap.title, snap.price, snap.sku, url)

            button = buttons.first
            if await button.is_disabled():
                return CartResult(False, "blocked", "Toymate add-to-cart control is disabled", snap.title, snap.price, snap.sku, url)

            # Quantity is hard-locked to one for the cart-only milestone.
            qty = page.locator('form:has(input[name="id"]) input[name="quantity"]').first
            if await qty.count():
                try:
                    await qty.fill("1")
                except Exception:
                    pass

            await button.click()
            await page.wait_for_timeout(1500)

            # Safety invariant: never continue into checkout.
            current = page.url.lower()
            if "/checkout" in current:
                return CartResult(False, "safety_stop", "Unexpected checkout navigation; stopped before payment", snap.title, snap.price, snap.sku, page.url)

            return CartResult(True, "carted", "One item added to cart; checkout was NOT attempted", snap.title, snap.price, snap.sku, page.url)
        finally:
            await context.close()
            await browser.close()

