"""Utilities for building transactional seeding fixtures."""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from sqlalchemy.orm import Session
else:
    Session = Any  # type: ignore[misc]

from pydantic_fixturegen.api._runtime import ModelArtifactPlan


class SQLModelSeedRunner:
    """Helper that seeds SQLModel sessions inside pytest fixtures."""

    def __init__(
        self,
        plan: ModelArtifactPlan,
        session_factory: Callable[[], Session],
    ) -> None:
        self.plan = plan
        self._session_factory = session_factory

    def seed(self, *, count: int = 1, rollback: bool = True, batch_size: int = 50) -> None:
        from pydantic_fixturegen.orm.sqlalchemy import SQLAlchemySeeder

        seeder = SQLAlchemySeeder(self.plan, self._session_factory)
        seeder.seed(
            count=count,
            batch_size=batch_size,
            rollback=rollback,
            truncate=False,
            dry_run=False,
        )


__all__ = ["SQLModelSeedRunner"]
