"""Conservative checks for stock alerts; unknown seller evidence fails closed."""
import json
import re
from urllib.parse import urlsplit
from bs4 import BeautifulSoup

MARKETPLACE_RETAILERS = {'kmart-au': 'kmart', 'big-w-au': 'bigw', 'target-au': 'target'}


def normalized(value):
    return re.sub(r'[^a-z0-9]', '', str(value).lower())


def product_objects(soup):
    def walk(value):
        if isinstance(value, dict):
            kind = value.get('@type', [])
            if 'Product' in (kind if isinstance(kind, list) else [kind]):
                yield value
            for child in value.values():
                yield from walk(child)
        elif isinstance(value, list):
            for child in value:
                yield from walk(child)
    for script in soup.find_all('script', type='application/ld+json'):
        try:
            yield from walk(json.loads(script.get_text()))
        except (ValueError, TypeError):
            continue


def seller_status(soup, product, retailer):
    """Only positive seller evidence permits marketplace-capable sites."""
    expected = MARKETPLACE_RETAILERS.get(retailer)
    if expected is None:
        return True
    offers = product.get('offers', {}) if product else {}
    if isinstance(offers, list):
        offers = offers[0] if len(offers) == 1 else {}
    seller = offers.get('seller') or product.get('seller') if product else None
    if isinstance(seller, dict):
        seller = seller.get('name')
    if seller:
        return normalized(seller) in {expected, expected + 'australia'}
    # A site logo or footer does not establish who sells the product.
    text = soup.get_text(' ', strip=True)
    match = re.search(r'sold\s+(?:and\s+(?:shipped|fulfilled)\s+)?by\s+(.{1,60})', text, re.I)
    if match:
        return bool(re.match(r'(?:' + {'kmart':'Kmart','bigw':r'BIG\s*W','target':'Target'}[expected] + r')(?:\s+Australia)?(?:\s*[|.,]|\s+(?:Description|Product|Delivery|Shipping)|$)', match.group(1), re.I))
    return False


def toymate_online_status(soup, item, snap):
    """Read Toymate's explicit online status near the watched SKU.

    Toymate pages can contain active controls for related products, so only
    evidence in the watched product's SKU neighbourhood is trusted.
    """
    text = soup.get_text(' ', strip=True)
    sku = str(item.get('expected_sku') or snap.sku or '').strip()
    if not sku:
        return None
    match = re.search(r'.{0,500}SKU\s*:\s*' + re.escape(sku) + r'.{0,500}', text, re.I)
    if not match:
        return None
    scope = match.group(0)
    if re.search(r'Online\s*:\s*Not Available|Not Available Online|Instore Only|Stock\s*:\s*0\b', scope, re.I):
        return False
    if re.search(r'Online\s*:\s*Available\b|Available Online|Stock\s*:\s*[1-9]\d*\b', scope, re.I):
        return True
    return None


def refine_snapshot(snap, html, item):
    soup = BeautifulSoup(html, 'html.parser')
    products = list(product_objects(soup))
    matching = [p for p in products if str(p.get('url') or p.get('@id') or '').rstrip('/') == snap.url.rstrip('/')]
    product = matching[0] if matching else products[0] if len(products) == 1 else None
    if product:
        # Do not let unrelated product suggestions supply the current price.
        offers = product.get('offers', {})
        if isinstance(offers, list):
            offers = offers[0] if len(offers) == 1 else {}
        spec = offers.get('priceSpecification') or {}
        raw = offers.get('price', spec.get('price'))
        try:
            snap.price = float(raw) if raw is not None else None
        except (ValueError, TypeError):
            snap.price = None
        snap.currency = offers.get('priceCurrency') or spec.get('priceCurrency') or ''
        snap.sku = str(product.get('sku') or '') or None
        snap.title = str(product.get('name') or snap.title)
    else:
        snap.price = None
        snap.in_stock = None
        snap.note = 'No unambiguous structured product/price evidence'
    snap.first_party = seller_status(soup, product, snap.retailer)
    if not snap.first_party:
        snap.in_stock = None
        snap.note = 'Marketplace seller or first-party seller not confirmed'
    if snap.retailer == 'toymate-au':
        # Prefer Toymate's explicit online status for the watched SKU. This
        # avoids recommendation-card Add to Cart buttons contaminating stock.
        explicit_status = toymate_online_status(soup, item, snap)
        if explicit_status is not None:
            snap.in_stock = explicit_status
            snap.note = 'Verified Toymate online status for watched SKU'
        else:
            # Fallback for page variants that expose only the primary form.
            buttons = []
            for form in soup.find_all('form'):
                if form.find('input', attrs={'name': 'id'}) and form.find('input', attrs={'name': 'quantity'}):
                    buttons.extend(form.find_all('button', type='submit'))
            if buttons:
                snap.in_stock = any(not b.has_attr('disabled') and b.get('aria-disabled') != 'true' and re.search(r'add to cart|preorder|pre-order', b.get_text(' ', strip=True), re.I) for b in buttons)
                snap.note = 'Verified main product purchase button'
            else:
                snap.in_stock = None
                snap.note = 'Primary purchase control or explicit online status not found'
    if snap.retailer in MARKETPLACE_RETAILERS and snap.first_party:
        buttons = soup.select('button[data-testid="add-to-cart-button"], button[data-testid="add-to-bag-button"]')
        if buttons:
            snap.in_stock = any(not b.has_attr('disabled') and b.get('aria-disabled') != 'true' and b.get('data-visual-disabled') != 'true' for b in buttons)
            snap.note = 'Verified retailer purchase control; delivery still requires postcode'
        else:
            snap.in_stock = None
            snap.note = 'First-party seller confirmed but active purchase control not found'
    if item.get('expected_sku') and normalized(snap.sku) != normalized(item['expected_sku']):
        snap.in_stock = None
        snap.note = 'Product SKU changed or unavailable'
    for term in item.get('title_keywords', []):
        if normalized(term) not in normalized(snap.title):
            snap.in_stock = None
            snap.note = 'Product title no longer matches watchlist'
    return snap
