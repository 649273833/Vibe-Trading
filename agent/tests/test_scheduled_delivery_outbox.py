"""Briefing delivery is an outbox, not a callback (#942).

The dispatch path returns once the agent attempt is *accepted*, so "the job
fired" and "the briefing is ready" are different facts. Delivery therefore
hangs off a persisted row whose only source of truth is the store: a crash
between the two can cost the speed of a delivery, never the fact that one is
owed, and no restart or retry can send the same briefing twice.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from src.scheduled_research.executor import ScheduledResearchExecutor
from src.scheduled_research.models import (
    DeliveryStatus,
    JobStatus,
    ScheduledResearchJob,
)
from src.scheduled_research.store import ScheduledResearchJobStore


class _Sender:
    def __init__(self, fail_times: int = 0) -> None:
        self.sent: list[tuple[str, str | None, str]] = []
        self._fail_times = fail_times

    async def __call__(self, channel: str, target: str | None, text: str) -> None:
        if self._fail_times > 0:
            self._fail_times -= 1
            raise RuntimeError("channel unreachable")
        self.sent.append((channel, target, text))


def _store(tmp_path: Path) -> ScheduledResearchJobStore:
    return ScheduledResearchJobStore(tmp_path / "jobs.json")


def _job(**overrides) -> ScheduledResearchJob:
    base = dict(id="j1", prompt="brief me", schedule="60000", next_run_at=0)
    base.update(overrides)
    return ScheduledResearchJob(**base)


def _executor(store, *, reader=None, sender=None, dispatch=None, now=1_000) -> ScheduledResearchExecutor:
    async def _default_dispatch(job):
        return "sess-1"

    return ScheduledResearchExecutor(
        store,
        dispatch or _default_dispatch,
        now_fn=lambda: now,
        enabled=False,
        briefing_reader=reader,
        channel_sender=sender,
        max_consecutive_failures=3,
    )


def test_a_job_without_a_channel_never_arms_the_outbox(tmp_path: Path) -> None:
    """Delivery is opt-in: no channel, no row, nothing sent anywhere."""
    store = _store(tmp_path)
    store.upsert(_job())
    sender = _Sender()
    executor = _executor(store, reader=lambda _s: ("completed", "text"), sender=sender)

    asyncio.run(executor.tick(now_ms=1_000))

    assert store.get("j1").delivery.status is DeliveryStatus.NONE
    assert sender.sent == []


def test_a_firing_arms_the_outbox_and_the_sweep_delivers_it(tmp_path: Path) -> None:
    store = _store(tmp_path)
    store.upsert(_job(delivery_channel="telegram", delivery_target="chat-9"))
    sender = _Sender()
    executor = _executor(store, reader=lambda _s: ("completed", "VERDICT: hold"), sender=sender)

    asyncio.run(executor.tick(now_ms=1_000))

    record = store.get("j1").delivery
    assert record.status is DeliveryStatus.SENT
    assert record.session_id == "sess-1"
    assert record.key == "j1:sess-1:telegram"
    assert sender.sent == [("telegram", "chat-9", "VERDICT: hold")]


def test_a_run_still_in_flight_is_left_for_a_later_sweep(tmp_path: Path) -> None:
    """The briefing does not exist yet; the row must survive to try again."""
    store = _store(tmp_path)
    store.upsert(_job(delivery_channel="telegram"))
    sender = _Sender()
    executor = _executor(store, reader=lambda _s: None, sender=sender)

    asyncio.run(executor.tick(now_ms=1_000))

    assert store.get("j1").delivery.status is DeliveryStatus.PENDING
    assert sender.sent == []


def test_a_second_sweep_does_not_send_the_same_briefing_again(tmp_path: Path) -> None:
    store = _store(tmp_path)
    store.upsert(_job(delivery_channel="telegram"))
    sender = _Sender()
    executor = _executor(store, reader=lambda _s: ("completed", "text"), sender=sender)

    asyncio.run(executor.tick(now_ms=1_000))
    asyncio.run(executor.sweep_deliveries())
    asyncio.run(executor.sweep_deliveries())

    assert len(sender.sent) == 1


def test_a_restart_delivers_what_the_previous_process_never_sent(tmp_path: Path) -> None:
    """The row is the source of truth, so a new process finishes the work.

    This is the case a callback alone cannot cover: the run finished while the
    poller was down, and no in-memory subscriber exists any more.
    """
    store = _store(tmp_path)
    store.upsert(_job(delivery_channel="telegram"))
    asyncio.run(_executor(store, reader=lambda _s: None, sender=_Sender()).tick(now_ms=1_000))
    assert store.get("j1").delivery.status is DeliveryStatus.PENDING

    # A brand new executor over the same store — the process restarted.
    sender = _Sender()
    revived = _executor(_store(tmp_path), reader=lambda _s: ("completed", "late"), sender=sender)
    asyncio.run(revived.sweep_deliveries())

    assert sender.sent == [("telegram", None, "late")]
    assert store.get("j1").delivery.status is DeliveryStatus.SENT


def test_a_failed_run_is_terminal_because_no_briefing_will_ever_exist(tmp_path: Path) -> None:
    store = _store(tmp_path)
    store.upsert(_job(delivery_channel="telegram"))
    sender = _Sender()
    executor = _executor(store, reader=lambda _s: ("failed", ""), sender=sender)

    asyncio.run(executor.tick(now_ms=1_000))

    record = store.get("j1").delivery
    assert record.status is DeliveryStatus.FAILED
    assert "run failed" in (record.error or "")
    assert sender.sent == []


def test_a_channel_outage_is_retried_rather_than_written_off(tmp_path: Path) -> None:
    """A transient send failure must not throw the briefing away."""
    store = _store(tmp_path)
    store.upsert(_job(delivery_channel="telegram"))
    sender = _Sender(fail_times=2)
    executor = _executor(store, reader=lambda _s: ("completed", "text"), sender=sender)

    asyncio.run(executor.tick(now_ms=1_000))
    assert store.get("j1").delivery.status is DeliveryStatus.PENDING
    assert store.get("j1").delivery.attempts == 1

    asyncio.run(executor.sweep_deliveries())
    assert store.get("j1").delivery.status is DeliveryStatus.PENDING

    asyncio.run(executor.sweep_deliveries())
    assert store.get("j1").delivery.status is DeliveryStatus.SENT
    assert len(sender.sent) == 1


def test_delivery_gives_up_once_the_attempt_threshold_is_reached(tmp_path: Path) -> None:
    """Retrying forever would be its own failure mode."""
    store = _store(tmp_path)
    store.upsert(_job(delivery_channel="telegram"))
    sender = _Sender(fail_times=99)
    executor = _executor(store, reader=lambda _s: ("completed", "text"), sender=sender)

    asyncio.run(executor.tick(now_ms=1_000))
    for _ in range(5):
        asyncio.run(executor.sweep_deliveries())

    record = store.get("j1").delivery
    assert record.status is DeliveryStatus.FAILED
    assert record.attempts == 3
    assert sender.sent == []


def test_the_sweep_is_inert_without_collaborators(tmp_path: Path) -> None:
    """An install with no channel runtime must not be changed by any of this."""
    store = _store(tmp_path)
    store.upsert(_job(delivery_channel="telegram"))
    executor = _executor(store)

    asyncio.run(executor.tick(now_ms=1_000))

    assert asyncio.run(executor.sweep_deliveries()) == 0
    assert store.get("j1").delivery.status is DeliveryStatus.PENDING
