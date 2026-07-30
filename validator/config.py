"""Validator configuration, loaded once from the environment (fail-fast)."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field


class ConfigError(RuntimeError):
    """Raised when required configuration is missing or malformed."""


def _require(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise ConfigError(f"missing required environment variable {name}")
    return value


def _optional(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


def _require_int(name: str) -> int:
    raw = _require(name)
    try:
        return int(raw)
    except ValueError as exc:
        raise ConfigError(f"{name} must be an integer, got {raw!r}") from exc


def _get_int(name: str, default: int) -> int:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise ConfigError(f"{name} must be an integer, got {raw!r}") from exc


def _get_float(name: str, default: float) -> float:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError as exc:
        raise ConfigError(f"{name} must be a number, got {raw!r}") from exc


def _get_bool(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name, "").strip().lower()
    if not raw:
        return default
    if raw in {"1", "true", "yes", "on"}:
        return True
    if raw in {"0", "false", "no", "off"}:
        return False
    raise ConfigError(f"{name} must be a boolean, got {raw!r}")


def _parse_usd_card(raw: str) -> dict[str, float]:
    """Parse the JSON GPU price card override into a {class: usd} map."""
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ConfigError(
            f"KUBETEE_GPU_USD_PRICES must be JSON: {exc}"
        ) from exc
    if not isinstance(parsed, dict):
        raise ConfigError("KUBETEE_GPU_USD_PRICES must be a JSON object")
    card: dict[str, float] = {}
    for key, value in parsed.items():
        try:
            card[str(key).upper()] = float(value)
        except (TypeError, ValueError) as exc:
            raise ConfigError(
                f"KUBETEE_GPU_USD_PRICES[{key!r}] must be numeric, got {value!r}"
            ) from exc
    return card


@dataclass(frozen=True)
class Config:
    netuid: int
    network: str
    endpoint: str
    hotkey_seed: str
    owner_uid: int
    owner_miner_uid: int | None  # subnet-owner staging miner allowed hybrid posture
    rancher_url: str
    rancher_token: str
    rancher_ca_file: str
    cycle_seconds: int
    window_hours: float
    taostats_api_key: str
    usd_card_override: dict[str, float]
    emission_usd_per_hour: float
    skip_rancher: bool
    targon_payout_enabled: bool
    targon_floor_frac: float
    hippius_access_key: str
    hippius_secret_key: str
    metrics_port: int

    @property
    def is_publisher(self) -> bool:
        """The subnet-owner publisher holds Hippius write credentials."""
        return bool(self.hippius_secret_key)

    def emission_usd_per_epoch(self, tempo: int = 0, hours: float = 0.0) -> float:
        """USD the epoch allocates: the per-hour budget × per-epoch duration.

        `hours` is the per-epoch duration in hours (tempo × ~12s/3600). When
        unset (older callers), falls back to the static window_hours.
        """
        return self.emission_usd_per_hour * (hours if hours > 0 else self.window_hours)


def load_config() -> Config:
    """Load and validate configuration; raise ConfigError on any problem."""
    owner_miner_uid_raw = _get_int("KUBETEE_OWNER_MINER_UID", -1)
    return Config(
        netuid=_require_int("SUBNET_NETUID"),
        network=_optional("BT_NETWORK", "finney") or "finney",
        endpoint=_optional("SUBTENSOR_ENDPOINT"),
        hotkey_seed=_require("VALIDATOR_HOTKEY_SEED"),
        owner_uid=_get_int("KUBETEE_OWNER_UID", 0),
        owner_miner_uid=(
            owner_miner_uid_raw if owner_miner_uid_raw >= 0 else None
        ),
        rancher_url=_require("RANCHER_URL").rstrip("/"),
        rancher_token=_optional("RANCHER_BEARER_TOKEN"),
        rancher_ca_file=_optional("RANCHER_CA_FILE"),
        cycle_seconds=_get_int("KUBETEE_CYCLE_SECONDS", 360),
        window_hours=_get_float("KUBETEE_WINDOW_HOURS", 1.0),
        taostats_api_key=_require("TAOSTATS_API_KEY"),
        usd_card_override=_parse_usd_card(_optional("KUBETEE_GPU_USD_PRICES")),
        emission_usd_per_hour=_get_float("KUBETEE_EMISSION_USD_PER_HOUR", 0.0),
        skip_rancher=_get_bool("KUBETEE_SKIP_RANCHER", False),
        targon_payout_enabled=_get_bool(
            "KUBETEE_TARGON_PAYOUT_ENABLED", False
        ),
        targon_floor_frac=_get_float("KUBETEE_TARGON_PRICE_FLOOR_FRAC", 0.75),
        hippius_access_key=_optional("KUBETEE_HIPPIUS_ACCESS_KEY"),
        hippius_secret_key=_optional("KUBETEE_HIPPIUS_SECRET_KEY"),
        metrics_port=_get_int("KUBETEE_METRICS_PORT", 9100),
    )
