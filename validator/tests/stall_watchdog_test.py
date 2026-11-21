"""The cycle watchdog must detect synchronous network deadlocks."""

import time

import cycle_watchdog


def test_stalled_main_cycle_dumps_threads_before_exiting(monkeypatch):
    dumped = []
    exited = []
    monkeypatch.setattr(
        cycle_watchdog.faulthandler,
        "dump_traceback",
        lambda: dumped.append(True),
    )
    start = time.monotonic()

    stopped = cycle_watchdog.start_stall_watchdog(
        start, timeout_seconds=0.05, action=lambda: exited.append(True)
    )
    try:
        time.sleep(0.2)
        assert exited == [True]
        assert dumped == [True]
    finally:
        stopped.set()


def test_completed_cycle_never_forces_process_exit():
    exited = []
    stopped = cycle_watchdog.start_stall_watchdog(
        time.monotonic(),
        timeout_seconds=0.05,
        action=lambda: exited.append(True),
    )
    stopped.set()
    stopped.wait(0.1)
    assert stopped.is_set()
    assert exited == []
