"""Epoch-frozen three-provider inputs for v1.4.0.

`epoch` is the PRICING epoch: every reader must fetch this version's exact
chain epoch. `source_epoch` is separate: a publisher outage may explicitly
memorialize an older last-good provider observation. The two are never
confused. Readers NEVER call provider APIs. targetPrice is NEVER read.
$0 is a valid scalar observation, not an instruction to substitute a price.
"""

from datetime import datetime, timezone
import math

GPU_TYPES = ("B300", "B200", "H200", "H100", "RTX6000")
PROVIDERS = ("targon", "lium", "chutes")
MARKET_KEY = "market.json"
MARKET_VERSION = 3


def _number(value):
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
        or value < 0
    ):
        return None
    return float(value)


def _positive(raw):
    if not isinstance(raw, dict):
        return {}
    return {
        key: float(value)
        for key, value in raw.items()
        if key in GPU_TYPES and _number(value) is not None and value > 0
    }


def market_rows(raw):
    """Known scalar $/GPU/hr fields ONLY; zero is not missing."""
    if not isinstance(raw, dict):
        return {}
    result = {}
    for key in GPU_TYPES:
        value = raw.get(key)
        if isinstance(value, dict):
            value = value.get("maxPrice")
        if _number(value) is not None:
            result[key] = {"maxPrice": float(value)}
    return result


def targon_rate(row):
    """PAYOUT/h if positive; otherwise THIS row's offered Maximum.

    No targetPrice lookup and no substitution of another SKU's rate occurs.
    """
    if not isinstance(row, dict):
        raise ValueError("Targon raw observation missing")
    hourly = _number(row.get("unitRate"))
    if hourly is not None and hourly > 0:
        return hourly
    maximum = _number(row.get("maxPrice"))
    if maximum is not None:
        return maximum
    raise ValueError(
        "Targon has neither PAYOUT/h nor Maximum; never targetPrice"
    )


def targon_fields(raw):
    """Select highest attenuated PAYOUT/h-or-own-Maximum among a GPU's SKUs."""
    if not isinstance(raw, dict):
        raise ValueError("Targon grouped raw rows required")
    result = {}
    for key in GPU_TYPES:
        candidates = raw.get(key)
        for row in (
            candidates if isinstance(candidates, list) else [candidates]
        ):
            if not isinstance(row, dict):
                continue
            hourly, maximum = _number(row.get("unitRate")), _number(
                row.get("maxPrice")
            )
            selected = {"unitRate": hourly}
            if maximum is not None:
                # Optional for v1.4.0 hourly; independently used for legacy.
                selected["maxPrice"] = maximum
            try:
                targon_rate(selected)
            except ValueError:
                continue
            if key not in result or targon_rate(selected) > targon_rate(
                result[key]
            ):
                result[key] = selected
    return result


def targon_by_gpu(compute):
    """Preserve raw source observations grouped by SKU GPU type."""
    from targon_payout_feed import _gpu_class_of

    grouped = {}
    for row in compute if isinstance(compute, list) else []:
        if not isinstance(row, dict) or row.get("kind", "gpu") != "gpu":
            continue
        key = _gpu_class_of(str(row.get("key", "")))
        if key in GPU_TYPES:
            grouped.setdefault(key, []).append(row)
    return grouped


def chutes_for_epoch(raw, epoch):
    """Canonical Chutes snapshot read/write shape, not four incompatible forms.

    A previous sample must be explicitly marked `stale`; its original bucket
    is preserved for observability. A future post-epoch observation is never
    imported as current input. The containing market's chain epoch is checked
    independently by `parse_market_snapshot`.
    """
    if (
        type(epoch) is not int
        or epoch <= 0
        or not isinstance(raw, dict)
        or not isinstance(raw.get("per_class_usd"), dict)
        or type(raw.get("bucket")) is not int
        or raw["bucket"] > epoch
        or raw["bucket"] <= 0
    ):
        return None
    if raw["bucket"] != epoch and raw.get("stale") is not True:
        return None
    return {**raw, "observation_window": "current_24h"}


def _volatile_provider_rates(raw, providers, gpu_type=None):
    if not isinstance(raw, dict):
        raise ValueError("invalid shared market snapshot")
    if providers not in PROVIDERS:
        raise ValueError("unknown market provider")
    rows = raw.get("providers", {}).get(providers, {})
    result = (
        {key: targon_rate(value) for key, value in rows.items()}
        if providers == "targon"
        else {key: value["maxPrice"] for key, value in rows.items()}
    )
    return (
        {gpu_type: result[gpu_type]}
        if gpu_type in result
        else {} if gpu_type is not None else result
    )


def provider_rates(snapshot, provider):
    """Read same typed provider field for writer AND reader, not derived price."""
    return _volatile_provider_rates(snapshot, provider)


def build_market_snapshot(
    epoch, floors, targon, lium, chutes, source_epochs=None, raw_targon=None
):
    """Normalize raw markets with optional exact Targon recovery provenance."""
    frozen = chutes_for_epoch(chutes, epoch)
    if frozen is None:
        raise ValueError("invalid Chutes source epoch")
    if not isinstance(lium, dict):
        raise ValueError("invalid Lium source rows")
    data = {
        "targon": targon_fields(targon),
        # Lium's dashboard omits rather than reports zero earned rates.
        "lium": market_rows(_positive(lium)),
        "chutes": market_rows(frozen["per_class_usd"]),
    }
    if not any(data.values()):
        raise ValueError("no usable raw market fields")
    if not isinstance(floors, dict):
        raise ValueError(
            "manual floors map required; static card is not input"
        )
    old_floors = _positive(floors)
    inputs = source_epochs or {provider: epoch for provider in PROVIDERS}
    if not isinstance(inputs, dict):
        raise ValueError("missing input epochs")
    for provider in PROVIDERS:
        if (
            type(inputs.get(provider)) is not int
            or inputs[provider] > epoch
            or inputs[provider] <= 0
        ):
            raise ValueError(f"invalid {provider} source epoch")
    for provider, raw in data.items():
        if (
            raw
            and not source_epochs
            and provider == "chutes"
            and frozen["bucket"] != epoch
        ):
            inputs["chutes"] = frozen["bucket"]
    observed_epochs = dict(inputs)
    if not source_epochs and frozen["bucket"] != epoch:
        observed_epochs["chutes"] = frozen["bucket"]
    result = {
        "version": MARKET_VERSION,
        "epoch": epoch,
        "floors": old_floors,
        "providers": data,
        "source_epochs": observed_epochs,
        "chutes_snapshot": frozen,
        "taken_at": datetime.now(timezone.utc).isoformat(),
    }
    if raw_targon:
        if targon_fields(raw_targon) != data["targon"]:
            raise ValueError("raw Targon does not match normalized rate")
        # Per-SKU raw values are publisher recovery provenance, not a second
        # pricing input: MAXIMUM for v1.3.x; hourly-or-own-Maximum in v1.4.0.
        result["targon_raw"] = raw_targon
    return result


def parse_market_snapshot(raw, epoch):
    """Strict v3 current-chain-epoch read; never legacy card interpretation."""
    if (
        not isinstance(raw, dict)
        or raw.get("version") != MARKET_VERSION
        or type(epoch) is not int
        or epoch <= 0
        or type(raw.get("epoch")) is not int
        or raw["epoch"] != epoch
        or not isinstance(raw.get("floors"), dict)
        or not isinstance(raw.get("providers"), dict)
        or not isinstance(raw.get("source_epochs"), dict)
    ):
        return None
    try:
        chutes = chutes_for_epoch(raw.get("chutes_snapshot"), epoch)
        if chutes is None or chutes != raw["chutes_snapshot"]:
            return None
        data = raw["providers"]
        for provider in ("lium", "chutes"):
            for klass, row in data[provider].items():
                if row != market_rows({klass: row}).get(klass) or not (
                    provider == "chutes" or _positive({klass: row["maxPrice"]})
                ):
                    return None
        if market_rows(chutes["per_class_usd"]) != market_rows(
            data.get("chutes")
        ):
            return None
        provider_data = {
            "targon": targon_fields(data.get("targon")),
            "lium": market_rows(data.get("lium")),
            "chutes": market_rows(data.get("chutes")),
        }
        if raw["floors"] != _positive(raw["floors"]):
            return None
        for provider in PROVIDERS:
            source_epoch = raw["source_epochs"].get(provider)
            if (
                type(source_epoch) is not int
                or source_epoch <= 0
                or source_epoch > epoch
            ):
                return None
        for provider, values in data.items():
            if not isinstance(values, dict) or set(values) - set(GPU_TYPES):
                return None
        if set(data) != set(PROVIDERS):
            return None
        if raw["source_epochs"]["chutes"] != chutes["bucket"]:
            return None
        if "targon_raw" in raw:
            if targon_fields(raw["targon_raw"]) != provider_data["targon"]:
                return None
        raw_targon = raw.get("targon_raw")
        if raw_targon is not None:
            from targon_payout_feed import _legacy_maximum_rows

            if not _legacy_maximum_rows(raw_targon):
                return None
    except (TypeError, ValueError, KeyError, AttributeError):
        return None
    return {
        **raw,
        "floors": _positive(raw["floors"]),
        "providers": provider_data,
        "chutes_snapshot": chutes,
    }


def fetch_market_snapshot(epoch):
    """Sole transport seam; reader receives parsed snapshot or None only."""
    if type(epoch) is not int or epoch <= 0:
        return None
    try:
        from hippius_store import _get_public

        return parse_market_snapshot(_get_public(MARKET_KEY), epoch)
    except Exception:
        return None


def market_price(klass, market):
    """Rule: choose HIGHEST of all three providers, +10%, then manual floor."""
    rates = []
    for provider in PROVIDERS:
        rate = provider_rates(market, provider).get(klass)
        if rate is not None:
            rates.append(rate)
    if not rates:
        raise ValueError("no shared scalar observation for " + klass)
    # A class with no configured manual floor has NO retired 0.75*card floor.
    return max(
        float(market.get("floors", {}).get(klass, 0.0)), 1.10 * max(rates)
    )


def fetch_market_snapshot(epoch):
    """Read a v3 object only if it matches exactly this pricing epoch."""
    if type(epoch) is not int or epoch <= 0:
        return None
    try:
        from hippius_store import _get_public

        return parse_market_snapshot(_get_public(MARKET_KEY), epoch)
    except Exception:
        return None
