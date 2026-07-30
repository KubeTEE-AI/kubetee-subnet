"""Prometheus metrics + degraded-mode skip accountant."""

from __future__ import annotations

from prometheus_client import Counter, Gauge, start_http_server

CYCLES = Counter(
    "kubetee_validator_cycles_total",
    "Validator cycles, partitioned by outcome.",
    ["outcome"],  # ok | skip
)
SKIP = Counter(
    "kubetee_validator_skip_total",
    "Cycles skipped (previous on-chain weights persist, counters freeze).",
    ["reason"],
)
EARNING = Gauge(
    "kubetee_validator_miners_earning", "Miners that earned weight this cycle."
)
WEIGHT_UID = Gauge(
    "kubetee_validator_uid_weight",
    "Normalized weight assigned to a uid this cycle.",
    ["uid"],
)
OWNER_WEIGHT = Gauge(
    "kubetee_validator_owner_weight", "Owner remainder weight this cycle."
)
PRICING_SOURCE = Gauge(
    "kubetee_pricing_source",
    "The source the Targon clamp priced off this cycle (1).",
    ["source"],  # live | cache | card
)
CARD_SOURCE = Gauge(
    "kubetee_card_source",
    "The source the price card resolved from this cycle (1).",
    ["source"],  # published | cache | default
)
TARGON_AGE = Gauge(
    "kubetee_targon_price_age_seconds",
    "Age of the pricing data the Targon clamp used (seconds).",
)
USD_PER_ALPHA = Gauge(
    "kubetee_usd_per_alpha", "USD per alpha token this cycle."
)
EFFECTIVE_CARD = Gauge(
    "kubetee_effective_usd_per_card",
    "Post-clamp USD per GPU-hour per class.",
    ["class"],
)
PUBLISH = Counter(
    "kubetee_hippius_publish_total",
    "Hippius publish attempts by the owner validator.",
    ["object", "outcome"],  # payout|price-card x ok|error
)


def start_metrics_server(port: int) -> None:
    start_http_server(port)


def _reset_gauge_family(gauge: Gauge, label_names) -> None:
    # prometheus_client has no reset-all; clear known children by setting to 0.
    try:
        for sample in gauge.collect()[0].samples:
            label_values = tuple(
                sample.labels.get(name) for name in label_names
            )
            gauge.labels(*label_values).set(0)
    except Exception:  # noqa: BLE001 - metrics must never break the cycle
        pass


def record_skip(reason: str) -> None:
    SKIP.labels(reason).inc()
    CYCLES.labels("skip").inc()


def record_cycle(
    earning: int,
    weights: dict[int, float],
    owner_weight: float,
    usd_per_alpha: float,
    effective_card: dict[str, float],
    pricing_source: str,
    card_source: str,
    targon_age_seconds: float,
) -> None:
    CYCLES.labels("ok").inc()
    EARNING.set(earning)
    OWNER_WEIGHT.set(owner_weight)
    USD_PER_ALPHA.set(usd_per_alpha)
    TARGON_AGE.set(targon_age_seconds)

    _reset_gauge_family(WEIGHT_UID, ("uid",))
    for uid, weight in weights.items():
        WEIGHT_UID.labels(str(uid)).set(weight)

    _reset_gauge_family(EFFECTIVE_CARD, ("class",))
    for klass, price in effective_card.items():
        EFFECTIVE_CARD.labels(klass).set(price)

    for source in ("live", "cache", "card"):
        PRICING_SOURCE.labels(source).set(1 if source == pricing_source else 0)
    for source in ("published", "cache", "default"):
        CARD_SOURCE.labels(source).set(1 if source == card_source else 0)


def record_publish(obj: str, ok: bool) -> None:
    PUBLISH.labels(obj, "ok" if ok else "error").inc()
