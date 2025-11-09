from __future__ import annotations

from pydantic_fixturegen.core.cycle_report import (
    CycleEvent,
    attach_cycle_events,
    consume_cycle_events,
)


def test_cycle_event_payload_includes_optional_fields() -> None:
    event = CycleEvent(
        path="$.user",
        policy="reuse",
        reason="cycle",
        ref_path="$.user",
        fallback="stub",
    )
    payload = event.to_payload()
    assert payload["ref"] == "$.user"
    assert payload["fallback"] == "stub"


def test_attach_cycle_events_skips_non_weakref_instances() -> None:
    event = CycleEvent(path="$.user", policy="reuse", reason="cycle")
    attach_cycle_events(42, [event])  # ints are not weak-referenceable
    assert consume_cycle_events(42) == ()


def test_attach_and_consume_cycle_events() -> None:
    class Container:
        pass

    instance = Container()
    event = CycleEvent(path="$.user", policy="reuse", reason="cycle")
    attach_cycle_events(instance, [event])
    assert consume_cycle_events(instance) == (event,)
    # ensure registry entries are cleared
    assert consume_cycle_events(instance) == ()
