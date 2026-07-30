"""Cancellation safety regressions for the process-wide database gate."""

from __future__ import annotations

import asyncio
import threading
import time
from unittest.mock import patch

from backend.database_access import DatabaseAccessGate


async def wait_thread_event(event: threading.Event, label: str) -> None:
    deadline = time.monotonic() + 2
    while time.monotonic() < deadline:
        if event.is_set():
            return
        await asyncio.sleep(0.005)
    raise AssertionError(f"Timed out waiting for {label}")


async def expect_cancelled(task: asyncio.Task, unblock: threading.Event) -> None:
    task.cancel()
    unblock.set()
    try:
        await task
    except asyncio.CancelledError:
        return
    raise AssertionError("Gate task ignored cancellation")


async def probe_both_modes(gate: DatabaseAccessGate) -> None:
    async def probe() -> None:
        async with gate.shared():
            pass
        async with gate.exclusive():
            pass

    await asyncio.wait_for(probe(), 1)
    assert gate.is_idle


async def cancel_during_transition(method_name: str) -> None:
    gate = DatabaseAccessGate()
    transitioned = threading.Event()
    unblock = threading.Event()
    original = getattr(gate, method_name)

    def delayed(*args) -> None:
        original(*args)
        transitioned.set()
        unblock.wait()

    async def enter() -> None:
        context = gate.shared() if method_name == "_try_shared" else gate.exclusive()
        async with context:
            await asyncio.Event().wait()

    with patch.object(gate, method_name, delayed):
        task = asyncio.create_task(enter())
        await wait_thread_event(transitioned, method_name)
        await expect_cancelled(task, unblock)

    assert gate.is_idle, f"{method_name} leaked gate state"
    await probe_both_modes(gate)


async def cancel_active_mode(exclusive: bool) -> None:
    gate = DatabaseAccessGate()
    entered = asyncio.Event()

    async def hold() -> None:
        context = gate.exclusive() if exclusive else gate.shared()
        async with context:
            entered.set()
            await asyncio.Event().wait()

    task = asyncio.create_task(hold())
    await asyncio.wait_for(entered.wait(), 1)
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
    else:
        raise AssertionError("Active gate task ignored cancellation")
    assert gate.is_idle
    await probe_both_modes(gate)


async def run_regressions() -> None:
    # Each transition mutates state before its worker is released, reproducing
    # cancellation after a successful callback but before the await returns.
    for method_name in ("_try_shared", "_queue_exclusive", "_try_exclusive"):
        await cancel_during_transition(method_name)
    await cancel_active_mode(exclusive=False)
    await cancel_active_mode(exclusive=True)


def test_gate_cancellation_does_not_leak_state() -> None:
    asyncio.run(run_regressions())


if __name__ == "__main__":
    test_gate_cancellation_does_not_leak_state()
    print("PASS: database gate cancellation leaves no readers, writers, or queue")
