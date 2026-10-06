from __future__ import annotations

import argparse
import asyncio
import json

from playwright.async_api import async_playwright

from src.alert_policy import refine_snapshot
from src.buy_rules import evaluate_buy_rule
from src.retailers import parse_product


async def cart_once(url: str, sku: str, max_price: float, headed: bool = False):
    item = {
        "url": url,
        "retailer": "toymate-au",
        "expected_sku": sku,
        "currency": "AUD",
        "max_price": max_price,
        "quantity": 1,
    }

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=not headed)
        context = await browser.new_context(locale="en-AU")
        page = await context.new_page()
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=30000)
            await page.wait_for_timeout(1500)
            html = await page.content()
            snap = refine_snapshot(parse_product(page.url, html, "toymate-au"), html, item)
            decision = evaluate_buy_rule(snap, item)
            if not decision.eligible:
                return {"status": "BLOCKED", "reason": decision.reason, "snapshot": snap.to_dict()}

            # Use the visible product-page control rather than constructing a private cart request.
            candidates = [
                page.get_by_text("I agree + add to cart", exact=False),
                page.get_by_role("button", name="Add to Cart"),
                page.get_by_role("button", name="Add to cart"),
            ]
            clicked = False
            for locator in candidates:
                try:
                    if await locator.count() and await locator.first.is_visible():
                        await locator.first.click()
                        clicked = True
                        break
                except Exception:
                    continue
            if not clicked:
                return {"status": "FAILED", "reason": "Visible Toymate add-to-cart control not found"}

            await page.wait_for_timeout(1800)
            if "/checkout" in page.url.lower():
                return {"status": "SAFETY_STOP", "reason": "Unexpected checkout navigation; no payment action attempted"}

            # Confirm from the rendered page that a basket/cart state appeared.
            body = (await page.locator("body").inner_text()).lower()
            cart_signals = ("basket", "cart", "view cart", "view basket")
            confirmed = any(x in body for x in cart_signals)
            return {
                "status": "CARTED" if confirmed else "CART_CLICKED",
                "reason": "Quantity 1 cart action completed; checkout/payment was not attempted",
                "title": snap.title,
                "price": snap.price,
                "sku": snap.sku,
                "url": page.url,
            }
        finally:
            await context.close()
            await browser.close()


def main():
    parser = argparse.ArgumentParser(description="Toymate quantity-1 cart test; never checks out.")
    parser.add_argument("--url", required=True)
    parser.add_argument("--sku", required=True)
    parser.add_argument("--max-price", required=True, type=float)
    parser.add_argument("--headed", action="store_true")
    args = parser.parse_args()
    result = asyncio.run(cart_once(args.url, args.sku, args.max_price, args.headed))
    print(json.dumps(result, indent=2, default=str))


if __name__ == "__main__":
    main()

