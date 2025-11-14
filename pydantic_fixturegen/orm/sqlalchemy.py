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
        auto_primary_keys: bool = True,
    ) -> SQLAlchemySeedResult:
        inserted = 0

        with self._session_factory() as session:
            try:
                if truncate and not dry_run:
                    self._truncate_targets(session)

                while inserted < count:
                    chunk = min(batch_size, count - inserted)
                    self._process_chunk(
                        session,
                        chunk,
                        dry_run=dry_run,
                        auto_primary_keys=auto_primary_keys,
                    )
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

    def _process_chunk(
        self,
        session: Any,
        chunk_size: int,
        *,
        dry_run: bool,
        auto_primary_keys: bool,
    ) -> None:
        for _ in range(chunk_size):
            sample = self.plan.sample_factory()
            for model_cls, payload in _expand_sample(self.plan, sample):
                obj = model_cls(
                    **_clean_payload(model_cls, payload, auto_primary_keys=auto_primary_keys)
                )
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


def _clean_payload(
    model_cls: type[Any],
    payload: dict[str, Any],
    auto_primary_keys: bool = True,
) -> dict[str, Any]:
    data = {key: value for key, value in payload.items() if key != "__cycles__"}
    if not auto_primary_keys:
        return data
    for field_name in _sqlmodel_auto_primary_key_fields(model_cls):
        if data.get(field_name) is not None:
            data[field_name] = None
    return data


_SQLMODEL_PK_FIELDS_CACHE: dict[type[Any], tuple[str, ...]] = {}


def _sqlmodel_auto_primary_key_fields(model_cls: type[Any]) -> tuple[str, ...]:
    cached = _SQLMODEL_PK_FIELDS_CACHE.get(model_cls)
    if cached is not None:
        return cached
    try:
        from sqlmodel import SQLModel
    except ModuleNotFoundError:  # pragma: no cover - optional dependency
        result: tuple[str, ...] = ()
        _SQLMODEL_PK_FIELDS_CACHE[model_cls] = result
        return result
    if not isinstance(model_cls, type) or not issubclass(model_cls, SQLModel):
        result = ()
        _SQLMODEL_PK_FIELDS_CACHE[model_cls] = result
        return result
    fields = getattr(model_cls, "model_fields", {})
    names: list[str] = []
    for field_name, field_info in fields.items():
        if not getattr(field_info, "primary_key", False):
            continue
        default_value = getattr(field_info, "default", object())
        default_factory = getattr(field_info, "default_factory", None)
        default_is_none = default_value is None
        if not default_is_none and callable(default_factory):
            try:
                default_is_none = default_factory() is None
            except Exception:  # pragma: no cover - user-defined factory
                default_is_none = False
        if default_is_none:
            names.append(field_name)
    result = tuple(names)
    _SQLMODEL_PK_FIELDS_CACHE[model_cls] = result
    return result
