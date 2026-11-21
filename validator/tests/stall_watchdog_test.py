"""The cycle watchdog must detect synchronous network deadlocks."""

import time

import cycle_watchdog
from validator import Validator
import validator_metrics as metrics


def test_heartbeat_only_advances_after_a_full_cycle(monkeypatch):
    completed = []
    monkeypatch.setattr(
        metrics, "record_cycle_completed", lambda: completed.append(True)
    )
    obj = object.__new__(Validator)
    obj.once = True
    obj.config = type(
        "Config",
        (),
        {
            "cycle_seconds": 0,
            "netuid": 90,
            "network": "finney",
            "is_publisher": False,
            "owner_uid": 0,
        },
    )()
    obj.chain = type("Chain", (), {"endpoint": "test"})()
    obj.dry_run = True
    obj.hippius = None
    monkeypatch.setattr(obj, "_log_chain_hyperparams", lambda: None)
    obj.run_cycle = lambda: completed.append("cycle")
    obj.run_forever()
    assert completed == ["cycle", True]

    completed.clear()
    obj.run_cycle = lambda: (_ for _ in ()).throw(
        RuntimeError("stalled fetch")
    )
    obj.run_forever()
    assert completed == []


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
