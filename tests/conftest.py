"""Shared fixtures.

The runtime logs via loguru with the ml-pipeline call-site convention
(short message + ``extra={...}`` structured context); the suite's caplog
assertions capture through stdlib logging and match ``key=value`` fragments.
This bridge forwards every loguru record into the stdlib "basic_validator"
logger (the pre-loguru logger name the tests filter on), rendering the
extras as ``key=value`` pairs exactly like the production sink.
"""

import logging
import pathlib
import sys

import pytest
from loguru import logger

sys.path.insert(
    0, str(pathlib.Path(__file__).resolve().parent.parent / "scripts")
)

from logging_setup import render_context  # noqa: E402


def _propagate_to_stdlib(message) -> None:
    record = message.record
    text = record["message"]
    if record["extra"]:
        text = f"{text}: {render_context(record['extra'])}"
    logging.getLogger("basic_validator").handle(
        logging.LogRecord(
            name="basic_validator",
            level=record["level"].no,
            pathname=record["file"].path,
            lineno=record["line"],
            msg=text,
            args=None,
            exc_info=None,
        )
    )


@pytest.fixture(autouse=True)
def loguru_to_stdlib_logging():
    handler_identifier = logger.add(
        _propagate_to_stdlib, format="{message}", level=0
    )
    yield
    # main() may have called logger.remove() (sink reset), dropping this
    # sink already; removing an unknown id must not fail the test.
    try:
        logger.remove(handler_identifier)
    except ValueError:
        pass
