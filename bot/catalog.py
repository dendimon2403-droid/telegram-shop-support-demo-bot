"""Demo catalog. In a real project this would live in the database / an admin panel."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Product:
    id: str
    category: str
    name: str
    price_cents: int
    description: str

    @property
    def image_url(self) -> str:
        # Placeholder photos; a real shop would store Telegram file_ids or its own URLs.
        return f"https://picsum.photos/seed/{self.id}/640/400"


CATEGORIES = {
    "brew": "Brewing",
    "grind": "Grinders",
    "beans": "Beans",
}

PRODUCTS: dict[str, Product] = {
    p.id: p
    for p in [
        Product("v60", "brew", "Pour-over dripper V60", 1800, "Ceramic cone dripper for clean, bright coffee."),
        Product("kettle", "brew", "Gooseneck kettle 0.9 L", 4500, "Precise pouring control, stainless steel."),
        Product("press", "brew", "French press 600 ml", 2400, "Borosilicate glass, metal filter."),
        Product("hand", "grind", "Hand grinder", 5900, "Steel burrs, 25 clicks of adjustment."),
        Product("elec", "grind", "Electric burr grinder", 12900, "Quiet motor, 30 grind settings."),
        Product("eth", "beans", "Ethiopia Yirgacheffe 250 g", 1500, "Floral and citrus, light roast."),
        Product("col", "beans", "Colombia Huila 250 g", 1400, "Caramel and cocoa, medium roast."),
    ]
}


def products_in(category: str) -> list[Product]:
    return [p for p in PRODUCTS.values() if p.category == category]


def money(cents: int) -> str:
    return f"${cents / 100:.2f}"
