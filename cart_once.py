from __future__ import annotations

import argparse
import asyncio
import json

from src.buyer import toymate_cart_once


async def cart_once(url: str, sku: str, max_price: float, headed: bool = False):
    result = await toymate_cart_once({
        "url": url, "retailer": "toymate-au", "expected_sku": sku,
        "currency": "AUD", "max_price": max_price, "quantity": 1, "max_quantity": 1,
    }, headless=not headed)
    return {
        "status": result.status.upper(), "reason": result.message,
        "title": result.title, "price": result.price, "sku": result.sku, "url": result.url,
    }


def main():
    parser = argparse.ArgumentParser(description="Explicit Toymate quantity-one cart test; never checks out.")
    parser.add_argument("--url", required=True)
    parser.add_argument("--sku", required=True)
    parser.add_argument("--max-price", required=True, type=float)
    parser.add_argument("--headed", action="store_true")
    args = parser.parse_args()
    result = asyncio.run(cart_once(args.url, args.sku, args.max_price, args.headed))
    print(json.dumps(result, indent=2, default=str))


if __name__ == "__main__":
    main()
