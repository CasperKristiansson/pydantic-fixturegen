from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, HTTPException

from ...models.catalog import (
    CatalogVariant,
    InventoryReservation,
    Product,
    ProductCategory,
    VariantAttribute,
)
from ...models.shared import LocalizedText, MediaAsset, Money

router = APIRouter()


_CATALOG: dict[str, Product] = {
    "aurora-pack": Product(
        id=UUID("6a0fa723-0a89-4a19-a775-9c421c901111"),
        slug="aurora-pack",
        title="Aurora Photography Pack",
        description=[
            LocalizedText(locale="en-US", text="Night photography essentials"),
            LocalizedText(locale="sv-SE", text="Allt du behöver för nattfoto"),
        ],
        category=ProductCategory.accessories,
        variants=[
            CatalogVariant(
                id=UUID("0d1b9175-3ab6-4d83-8a4a-2ae8bfd1a001"),
                sku="LENS-001",
                title="Tripod",
                attributes=[VariantAttribute(name="height", value="150cm")],
                price=Money(amount=Decimal("99.00")),
                media=[
                    MediaAsset(
                        id=UUID("6fb9b2dd-0620-4eac-8ce3-38f04fa710bc"),
                        url="https://cdn.example.com/img/tripod.png",
                        alt_text="carbon tripod",
                    )
                ],
            ),
            CatalogVariant(
                id=UUID("8f91b119-f779-415d-88d9-845d8f50c9d1"),
                sku="LIGHT-100",
                title="Portable light",
                attributes=[VariantAttribute(name="lumens", value="1000")],
                price=Money(amount=Decimal("129.00")),
                media=[],
            ),
        ],
        tags=["photo", "night"],
        reservations=[
            InventoryReservation(
                reservation_id=UUID("ab449e59-734e-4ff1-b889-8d0fd6f4d01b"),
                variant_id=UUID("8f91b119-f779-415d-88d9-845d8f50c9d1"),
                quantity=2,
                expires_at=datetime.utcnow() + timedelta(hours=4),
            )
        ],
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
        audit_trail=[],
    ),
    "summit-kit": Product(
        id=UUID("e2bb7c56-963c-4bee-83f4-a76d03a012ab"),
        slug="summit-kit",
        title="Summit Adventure Kit",
        description=[LocalizedText(locale="en-US", text="Layered apparel bundle")],
        category=ProductCategory.apparel,
        variants=[],
        tags=["hike"],
        reservations=[],
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
        audit_trail=[],
    ),
}


@router.get("/products", response_model=list[Product])
def list_products(category: ProductCategory | None = None) -> list[Product]:
    if category is None:
        return list(_CATALOG.values())
    return [product for product in _CATALOG.values() if product.category == category]


@router.get("/products/{slug}", response_model=Product)
def get_product(slug: str) -> Product:
    product = _CATALOG.get(slug)
    if product is None:
        raise HTTPException(status_code=404, detail="Product not found")
    return product
