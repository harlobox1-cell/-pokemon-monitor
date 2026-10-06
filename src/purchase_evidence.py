"""Conservative purchase-only evidence; does not change stock-alert heuristics."""
import re
from urllib.parse import urldefrag


def annotate_purchase_evidence(snap, soup, products, product, item):
    text = soup.get_text(' ', strip=True)
    snap.stock_verified = False
    snap.product_id = None
    snap.security_blocked = bool(
        re.search(r'captcha|verify you are human|waiting room|you are in (?:a |the )?queue|'
                  r'3d secure|3ds verification|security verification|too many requests|rate limit', text, re.I)
        or soup.select('iframe[src*="captcha"], iframe[src*="challenge"], '
                       '.g-recaptcha, .h-captcha, .cf-turnstile')
    )
    if (snap.security_blocked or len(products) != 1 or not product
            or snap.retailer != 'toymate-au' or snap.first_party is not True
            or snap.in_stock is not True):
        return
    sku = item.get('expected_sku')
    if not isinstance(sku, str) or not sku or product.get('sku') != sku:
        return
    for key in ('url', '@id'):
        if product.get(key):
            value = product[key]
            if not isinstance(value, str) or urldefrag(value)[0].rstrip('/') != snap.url.rstrip('/'):
                return
    offers = product.get('offers')
    if isinstance(offers, list):
        offers = offers[0] if len(offers) == 1 else None
    if not isinstance(offers, dict):
        return
    if offers.get('availability') not in (
        'InStock', 'https://schema.org/InStock', 'http://schema.org/InStock'
    ):
        return
    # Domain ownership never overrides contradictory explicit seller evidence.
    for source in (product, offers):
        if 'seller' in source:
            seller = source['seller']
            name = seller.get('name') if isinstance(seller, dict) else seller
            if not isinstance(name, str) or name.strip().lower() not in ('toymate', 'toymate australia'):
                return
    # Keep availability beside the exact watched SKU, never a recommendation.
    if not re.search(r'SKU\s*:\s*' + re.escape(sku) + r'\s+Online\s*:\s*Available\b', text):
        return
    for form in soup.select('form:has(input[name="id"]):has(input[name="quantity"])'):
        for button in form.select('button[type="submit"]'):
            if button.has_attr('disabled') or button.get('aria-disabled') == 'true':
                return
    identifier = product.get('productID')
    if isinstance(identifier, str) and identifier.strip() and identifier == identifier.strip():
        snap.product_id = identifier
    snap.stock_verified = True
