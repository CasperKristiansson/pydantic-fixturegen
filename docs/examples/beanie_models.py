"""Demo Beanie models used by the CLI integration checklist."""

from __future__ import annotations

import datetime as dt

from beanie import Document
from pydantic import Field


class DemoCustomer(Document):
    """Simple customer document with a few tagged attributes."""

    email: str
    name: str
    tier: str = "basic"
    tags: list[str] = Field(default_factory=list)

    class Settings:
        name = "demo_customers"


class DemoPurchase(Document):
    """Purchase document seeded alongside DemoCustomer."""

    customer_id: str
    order_number: str
    total_cents: int
    status: str = "PENDING"
    fulfilled_at: dt.datetime | None = None

    class Settings:
        name = "demo_purchases"


__all__ = ["DemoCustomer", "DemoPurchase"]
