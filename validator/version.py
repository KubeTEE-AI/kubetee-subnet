"""Validator release version (sent on every proxy request).

Precedence:
  1. ``KUBETEE_VALIDATOR_VERSION`` env (set at image build / release)
  2. The baked-in ``__version__`` constant below

Keep ``__version__`` in sync with the git tag / GHCR image tag (without the
leading ``v``). Example: image ``v1.0.1`` → ``__version__ = "1.0.1"``.
"""

from __future__ import annotations

import os
import re

__version__ = "1.1.6"

_SEMVER_RE = re.compile(
    r"^v?(?P<major>\d+)\.(?P<minor>\d+)\.(?P<patch>\d+)"
    r"(?:[-+][0-9A-Za-z.-]+)?$"
)


def validator_version() -> str:
    """Version string advertised to the Rancher proxy / User-Agent."""
    env = os.environ.get("KUBETEE_VALIDATOR_VERSION", "").strip()
    if env:
        return env.lstrip("v")
    return __version__


def parse_semver(raw: str) -> tuple[int, int, int] | None:
    """Parse a semver-ish string to (major, minor, patch), or None if invalid."""
    if not raw:
        return None
    m = _SEMVER_RE.match(raw.strip())
    if not m:
        return None
    return int(m.group("major")), int(m.group("minor")), int(m.group("patch"))


def version_at_least(client: str, minimum: str) -> bool:
    """True if ``client`` >= ``minimum`` (semver core only; pre-release ignored).

    Invalid / empty client versions are treated as older than any minimum.
    """
    c = parse_semver(client)
    m = parse_semver(minimum)
    if m is None:
        return True  # misconfigured minimum → do not lock everyone out
    if c is None:
        return False
    return c >= m
