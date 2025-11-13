"""Namespace package for marketplace models.

Intentionally avoids re-exporting individual classes so safe-import discovery can
import submodules without circular imports. Import the module you need directly,
for example `from app.models import order`.
"""

__all__ = [
    "catalog",
    "customer",
    "notification",
    "order",
    "payment",
    "shared",
]
