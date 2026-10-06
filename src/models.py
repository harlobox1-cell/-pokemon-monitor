from __future__ import annotations
from dataclasses import dataclass, asdict

@dataclass
class ProductSnapshot:
    retailer: str
    url: str
    title: str
    price: float | None
    currency: str
    in_stock: bool | None
    sku: str | None
    source: str
    note: str = ""
    first_party: bool = False

    stock_verified: bool = False
    security_blocked: bool = False
    product_id: str | None = None

    def to_dict(self):
        return asdict(self)
