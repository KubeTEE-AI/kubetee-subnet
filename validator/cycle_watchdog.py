"""Detect a main-loop call stuck beyond the normal cycle budget.

The proxy and metrics HTTP servers run in their own threads, so serving HTTP
is not evidence that the validator is scoring. Dump every thread first, then
exit so Kubernetes restarts a process which cannot recover on its own.
"""

import faulthandler
import logging
import os
import threading
import time

log = logging.getLogger("validator")


def start_stall_watchdog(
    started: float,
    timeout_seconds: float,
    action=lambda: os._exit(1),
) -> threading.Event:
    """Watch one synchronous cycle; return an Event that cancels the watch."""
    stopped = threading.Event()

    def watch() -> None:
        deadline = started + timeout_seconds
        while not stopped.wait(
            max(0.0, min(15.0, deadline - time.monotonic()))
        ):
            if time.monotonic() >= deadline:
                log.critical(
                    "cycle watchdog: main loop stalled; thread dump follows"
                )
                faulthandler.dump_traceback()
                action()
                return

    threading.Thread(target=watch, name="cycle-watchdog", daemon=True).start()
    return stopped
