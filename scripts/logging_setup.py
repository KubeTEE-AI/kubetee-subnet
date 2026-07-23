"""Loguru sink configuration, ported from rbmk ml-pipeline
(src/ml_pipeline/runtime/logging.py) so both codebases log identically:
``YYYY-MM-DD HH:mm:ss.SSS LEVEL message | {key=value context}``.
"""

from __future__ import annotations

import sys
from typing import Any

from loguru import logger


def _flatten_extra_kwarg(record: dict[str, Any]) -> None:
    """Unwrap the repo-wide ``extra={...}`` kwarg convention.

    loguru stores keyword arguments in ``record["extra"]`` — so the
    convention's dict lands nested under the literal key ``"extra"``.
    Flattening it makes every call site's context render directly.
    """
    nested = record["extra"].pop("extra", None)
    if isinstance(nested, dict):
        record["extra"].update(nested)
    elif nested is not None:
        record["extra"]["context"] = nested


def _format_with_context(record: dict[str, Any]) -> str:
    base = "{time:YYYY-MM-DD HH:mm:ss.SSS} {level} {message}"
    if record["extra"]:
        return base + " | {extra}\n"
    return base + "\n"


def configure_logging(level: str = "INFO") -> None:
    """Replace all sinks with one stderr sink at ``level`` (e.g. "INFO")."""
    logger.remove()
    logger.configure(patcher=_flatten_extra_kwarg)
    logger.add(
        sys.stderr,
        format=_format_with_context,
        level=level,
    )
