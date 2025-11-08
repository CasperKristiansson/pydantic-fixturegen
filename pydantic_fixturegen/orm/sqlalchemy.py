"""SQLAlchemy / SQLModel seeding helpers."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Any

from pydantic_fixturegen.api._runtime import ModelArtifactPlan

from ..logging import Logger, get_logger


@dataclass(slots=True)
class SQLAlchemySeedResult:
    inserted: int
    rollback: bool
    dry_run: bool


class SQLAlchemySeeder:
    """Insert generated payloads into a SQLAlchemy/SQLModel session."""

    def __init__(
        self,
        plan: ModelArtifactPlan,
        session_factory: Callable[[], Any],
        *,
        logger: Logger | None = None,
    ) -> None:
        self.plan = plan
        self._session_factory = session_factory
        self.logger = logger or get_logger()

    def seed(
        self,
        count: int,
        *,
        batch_size: int = 50,
        rollback: bool = False,
        dry_run: bool = False,
        truncate: bool = False,
    ) -> SQLAlchemySeedResult:
        inserted = 0

        with self._session_factory() as session:
            try:
                if truncate and not dry_run:
                    self._truncate_targets(session)

                while inserted < count:
                    chunk = min(batch_size, count - inserted)
                    self._process_chunk(session, chunk, dry_run=dry_run)
                    inserted += chunk

                if dry_run or rollback:
                    session.rollback()
                else:
                    session.commit()
            except Exception:
                session.rollback()
                raise

        self.logger.info(
            "Seeded SQLAlchemy models",
            event="sqlalchemy_seed_complete",
            count=inserted,
            rollback=rollback,
            dry_run=dry_run,
        )
        return SQLAlchemySeedResult(inserted=inserted, rollback=rollback, dry_run=dry_run)

    def _truncate_targets(self, session: Any) -> None:
        from sqlmodel import delete

        for model_cls in (*self.plan.related_models, self.plan.model_cls):
            session.exec(delete(model_cls))
        session.commit()

    def _process_chunk(self, session: Any, chunk_size: int, *, dry_run: bool) -> None:
        for _ in range(chunk_size):
            sample = self.plan.sample_factory()
            for model_cls, payload in _expand_sample(self.plan, sample):
                obj = model_cls(**_clean_payload(payload))
                if not dry_run:
                    session.add(obj)
        if not dry_run:
            session.flush()


def _expand_sample(
    plan: ModelArtifactPlan,
    sample: Any,
) -> Iterable[tuple[type[Any], dict[str, Any]]]:
    if isinstance(sample, dict):
        expected_keys = {plan.model_cls.__name__, *[cls.__name__ for cls in plan.related_models]}
        if expected_keys.issubset(sample.keys()):
            ordered: list[tuple[type[Any], dict[str, Any]]] = []
            for related_cls in plan.related_models:
                payload = sample.get(related_cls.__name__)
                if isinstance(payload, dict):
                    ordered.append((related_cls, payload))
            primary_payload = sample.get(plan.model_cls.__name__)
            if isinstance(primary_payload, dict):
                ordered.append((plan.model_cls, primary_payload))
                return ordered
    if not isinstance(sample, dict):
        raise RuntimeError("Seeder expected payload dictionary")
    return [(plan.model_cls, sample)]


def _clean_payload(payload: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in payload.items() if key != "__cycles__"}
