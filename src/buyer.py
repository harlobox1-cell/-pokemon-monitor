from __future__ import annotations

from dataclasses import dataclass

from .buy_rules import evaluate_buy_rule, trusted_product_url
from .cart_adapter import add_verified_toymate_item


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
    """Use a fresh temporary browser for one cart-only attempt; never pay."""
    url = item.get("url")
    if not trusted_product_url(url):
        return CartResult(False, "blocked", "Exact HTTPS Toymate product URL required")

    from playwright.async_api import async_playwright

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=headless)
        context = None
        try:
            context = await browser.new_context(locale="en-AU")
            page = await context.new_page()
            attempt = await add_verified_toymate_item(page, item)
            return CartResult(attempt.ok, attempt.status, attempt.message,
                              attempt.title, attempt.price, attempt.sku, page.url)
        finally:
            try:
                if context is not None:
                    await context.close()
            finally:
                await browser.close()
