"""Shared fixtures.

The runtime logs via loguru (rbmk-python-design); the suite's caplog
assertions capture through stdlib logging. This bridge forwards every loguru
record into the stdlib "basic_validator" logger (the pre-loguru logger name
the tests filter on) so `caplog.at_level(..., logger="basic_validator")`
keeps working unchanged.
"""

import logging

import pytest
from loguru import logger


class _StdlibPropagateHandler(logging.Handler):
    def emit(self, record: logging.LogRecord) -> None:
        logging.getLogger("basic_validator").handle(record)


@pytest.fixture(autouse=True)
def loguru_to_stdlib_logging():
    handler_identifier = logger.add(
        _StdlibPropagateHandler(), format="{message}", level=0
    )
    yield
    # main() may have called logger.remove() (sink reset), dropping this
    # sink already; removing an unknown id must not fail the test.
    try:
        logger.remove(handler_identifier)
    except ValueError:
        pass
