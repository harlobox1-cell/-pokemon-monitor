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

    def to_dict(self):
        return asdict(self)
