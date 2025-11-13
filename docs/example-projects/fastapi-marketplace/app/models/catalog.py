"""Catalog entities describing sellable items."""

from datetime import datetime
from enum import Enum
from typing import Annotated
from uuid import UUID

from pydantic import Field

from .shared import LocalizedText, MarketplaceBaseModel, MediaAsset, Money, Timestamped


class ProductCategory(str, Enum):
    accessories = "accessories"
    apparel = "apparel"
    electronics = "electronics"
    services = "services"


class VariantAttribute(MarketplaceBaseModel):
    name: str
    value: str


class CatalogVariant(MarketplaceBaseModel):
    id: UUID
    sku: Annotated[str, Field(pattern=r"^[A-Z0-9\-]{6,14}$")]
    title: str
    attributes: list[VariantAttribute] = Field(default_factory=list)
    price: Money
    media: list[MediaAsset]


class InventoryReservation(MarketplaceBaseModel):
    reservation_id: UUID
    variant_id: UUID
    quantity: Annotated[int, Field(gt=0, le=25)]
    expires_at: datetime


class Product(Timestamped):
    id: UUID
    slug: Annotated[str, Field(pattern=r"^[a-z0-9\-]{3,64}$")]
    title: str
    description: list[LocalizedText]
    category: ProductCategory
    variants: list[CatalogVariant]
    tags: list[str] = Field(default_factory=list)
    reservations: list[InventoryReservation] = Field(default_factory=list)
