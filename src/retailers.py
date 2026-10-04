from __future__ import annotations
import json
import re
from urllib.parse import urljoin, urlparse
from bs4 import BeautifulSoup
from .models import ProductSnapshot

RETAILERS = {
    "eb-games-au": ["ebgames.com.au"],
    "jb-hifi-au": ["jbhifi.com.au"],
    "big-w-au": ["bigw.com.au"],
    "kmart-au": ["kmart.com.au"],
    "target-au": ["target.com.au"],
    "toymate-au": ["toymate.com.au"],
    "pokemon-centre-au": ["pokemoncenter.com"],
    "pokemon-center-us": ["pokemoncenter.com"],
    "costco-au": ["costco.com.au"],
}

OUT_WORDS = [
    "out of stock", "sold out", "currently unavailable", "not available",
    "unavailable online", "temporarily unavailable", "available soon",
]
IN_WORDS = [
    "add to cart", "add to bag", "add to basket", "in stock",
    "delivery available", "available for delivery", "buy now", "pre-order",
]

PRICE_RE = re.compile(r"(?:AUD\s*|A\$\s*|\$\s*)(\d{1,5}(?:[.,]\d{2})?)", re.I)
SKU_RE = re.compile(r"(?:SKU|PID|Product\s*ID|Product\s*Code)\s*[:#]?\s*([A-Za-z0-9_-]{4,30})", re.I)


def infer_retailer(url: str) -> str:
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    if "jbhifi.com.au" in host:
        return "jb-hifi-au"
    if "pokemoncenter.com" in host:
        return "pokemon-centre-au" if parsed.path.lower().startswith("/en-au") else "pokemon-center-us"
    for name, domains in RETAILERS.items():
        if name.startswith("pokemon-"):
            continue
        if any(host == d or host.endswith("." + d) for d in domains):
            return name
    return "unknown"


def _availability_from_schema(value) -> bool | None:
    if not value:
        return None
    s = str(value).lower()
    if any(x in s for x in ["instock", "limitedavailability", "preorder", "presale"]):
        return True
    if any(x in s for x in ["outofstock", "soldout", "discontinued"]):
        return False
    return None


def _walk_jsonld(obj):
    if isinstance(obj, dict):
        yield obj
        for v in obj.values():
            yield from _walk_jsonld(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _walk_jsonld(v)


def parse_product(url: str, html: str, retailer: str | None = None) -> ProductSnapshot:
    retailer = retailer or infer_retailer(url)
    soup = BeautifulSoup(html, "html.parser")
    title = ""
    price = None
    currency = "AUD" if retailer != "pokemon-center-us" else "USD"
    stock = None
    sku = None
    source = "html"
    note = ""

    for node in soup.find_all("script", attrs={"type": "application/ld+json"}):
        raw = node.string or node.get_text("", strip=True)
        if not raw:
            continue
        try:
            data = json.loads(raw)
        except Exception:
            continue
        for item in _walk_jsonld(data):
            typ = item.get("@type")
            types = typ if isinstance(typ, list) else [typ]
            if "Product" not in types:
                continue
            title = title or str(item.get("name") or "").strip()
            sku = sku or str(item.get("sku") or item.get("productID") or "").strip() or None
            offers = item.get("offers")
            if isinstance(offers, list):
                offers = offers[0] if offers else None
            if isinstance(offers, dict):
                p = offers.get("price") or offers.get("lowPrice")
                try:
                    price = float(str(p).replace(",", "")) if p is not None else price
                except ValueError:
                    pass
                currency = str(offers.get("priceCurrency") or currency)
                av = _availability_from_schema(offers.get("availability"))
                stock = av if av is not None else stock
            source = "json-ld"
            break
        if title:
            break

    if not title:
        meta_title = soup.find("meta", attrs={"property": "og:title"}) or soup.find("meta", attrs={"name": "twitter:title"})
        if meta_title and meta_title.get("content"):
            title = meta_title.get("content").strip()
        elif soup.title:
            title = soup.title.get_text(" ", strip=True)
        else:
            title = url

    if price is None:
        for prop in ["product:price:amount", "og:price:amount"]:
            tag = soup.find("meta", attrs={"property": prop})
            if tag and tag.get("content"):
                try:
                    price = float(tag.get("content").replace(",", ""))
                    break
                except ValueError:
                    pass

    text = " ".join(soup.stripped_strings)
    lower = text.lower()

    if price is None:
        m = PRICE_RE.search(text)
        if m:
            try:
                price = float(m.group(1).replace(",", ""))
            except ValueError:
                pass

    if sku is None:
        m = SKU_RE.search(text)
        if m:
            sku = m.group(1)

    if stock is None:
        out_hit = next((x for x in OUT_WORDS if x in lower), None)
        in_hit = next((x for x in IN_WORDS if x in lower), None)
        if out_hit and not in_hit:
            stock = False
            note = f"matched '{out_hit}'"
        elif in_hit and not out_hit:
            stock = True
            note = f"matched '{in_hit}'"
        elif in_hit and out_hit:
            note = "mixed stock wording; availability left unknown"

    return ProductSnapshot(
        retailer=retailer,
        url=url,
        title=title[:240],
        price=price,
        currency=currency,
        in_stock=stock,
        sku=sku,
        source=source,
        note=note,
    )


def discover_product_links(base_url: str, html: str, include_keywords: list[str], exclude_keywords: list[str]) -> list[tuple[str, str]]:
    soup = BeautifulSoup(html, "html.parser")
    base_host = (urlparse(base_url).hostname or "").lower()
    includes = [x.lower().strip() for x in include_keywords if x.strip()]
    excludes = [x.lower().strip() for x in exclude_keywords if x.strip()]
    found: dict[str, str] = {}

    for a in soup.find_all("a", href=True):
        href = urljoin(base_url, a.get("href"))
        parsed = urlparse(href)
        if parsed.scheme not in ("http", "https"):
            continue
        if (parsed.hostname or "").lower() != base_host:
            continue
        label = " ".join(a.stripped_strings).strip()
        hay = f"{label} {parsed.path}".lower()
        if includes and not all(k in hay for k in includes):
            continue
        if any(k in hay for k in excludes):
            continue
        if any(x in parsed.path.lower() for x in ["/search", "/account", "/login", "/cart", "/checkout"]):
            continue
        canonical = parsed._replace(fragment="").geturl()
        if canonical not in found:
            found[canonical] = label or canonical
    return list(found.items())[:100]
