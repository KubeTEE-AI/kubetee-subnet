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


def render_context(extra: dict[str, Any]) -> str:
    """Render structured context as space-separated ``key=value`` pairs."""
    return " ".join(f"{key}={value}" for key, value in extra.items())


def _format_with_context(record: dict[str, Any]) -> str:
    base = "{time:YYYY-MM-DD HH:mm:ss.SSS} | {level} | {message}"
    if record["extra"]:
        # Pre-render and escape: the returned string is a loguru format
        # template, so literal braces must be doubled and "<" escaped —
        # loguru otherwise parses substrings like "<redacted-seed>" as
        # color markup tags and the handler errors out.
        context = render_context(record["extra"])
        escaped = (
            context.replace("{", "{{").replace("}", "}}").replace("<", "\\<")
        )
        base = base + " | " + escaped
    if record["exception"]:
        # A callable format must request the traceback explicitly; loguru
        # only auto-appends it for plain string formats.
        return base + "\n{exception}\n"
    return base + "\n"


def configure_logging(level: str = "INFO") -> None:
    """Replace all sinks with one stderr sink at ``level`` (e.g. "INFO")."""
    logger.remove()
    logger.configure(patcher=_flatten_extra_kwarg)
    logger.add(
        # Resolve sys.stderr at write time: binding the stream object here
        # pins whatever stderr replacement (e.g. pytest capsys) is active
        # when configure_logging runs, and writing to it later fails —
        # loguru's handler-error dump would then echo in-flight exception
        # chains, defeating redaction.
        lambda message: sys.stderr.write(message),
        format=_format_with_context,
        level=level,
        # Never render local variable values into tracebacks: they can
        # contain seeds/bearer tokens (redaction contract, AC5).
        diagnose=False,
    )
