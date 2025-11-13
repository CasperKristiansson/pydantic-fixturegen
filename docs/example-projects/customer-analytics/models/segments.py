"""Segment configuration + snapshot payloads."""
from __future__ import annotations

from pydantic import Field

from .events import PurchaseEvent, SessionEvent
from .identity import LifecycleStage
from .shared import AnalyticsBaseModel, MetricWindow


class SegmentFilter(AnalyticsBaseModel):
    stage: LifecycleStage = LifecycleStage.activated
    min_orders: int = Field(default=1, ge=0)
    locales: list[str] = Field(default_factory=lambda: ["sv_SE", "en_US"])
    window: MetricWindow = MetricWindow()


class SegmentSnapshot(AnalyticsBaseModel):
    name: str = "repeat-buyers"
    filter: SegmentFilter = Field(default_factory=SegmentFilter)
    purchases: list[PurchaseEvent] = Field(default_factory=lambda: [PurchaseEvent()])
    sessions: list[SessionEvent] = Field(default_factory=lambda: [SessionEvent()])


SegmentFilter.model_rebuild()
SegmentSnapshot.model_rebuild()
