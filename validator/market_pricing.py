"""Lium marketplace pricing feed — selected by the price card (v1.3.3).

When the published price card's ``pricing.lium`` switch is on the effective
per-class price becomes

    max(static floor, (1 + MARKET_MARKUP_FRAC) * highest(Lium, Targon))

with NO card ceiling (owner decision 2026-10-29: an above-card market pays
market + 10%). The static floor always holds: when both feeds price a
class below the floor — or both are dark for it — the class pays the floor.

Lium input (owner decision 2026-11-07):
- field: **Earned p75** from "Utilisation and earnings by GPU type, last
  7 days" (panel 7 of grafana.lium.io's `price-your-gpus` dashboard),
  with its GPU type variable set to All. This is estimated rental earnings
  per listed GPU-hour: 95% of asking price while rented; idle pay excluded.
- SKU rule: one card class maps to several Lium GPU types (e.g.
  `NVIDIA B300 SXM6 AC` vs `NVIDIA B300 SXM6 PC`); the class takes the
  HIGHEST type value (B300 rule, applied to every multi-SKU class).
- source: Lium's public Grafana (`grafana.lium.io`), anonymous read —
  same query the dashboard runs against `executor_price_history`.

The Targon half is the existing `TargonPayoutFeed` resolution (live
/targets PAYOUT/h `unitRate`; `maxPrice` ("Maximum") and `targetPrice` are
never read).

v1.3.3 ships this DORMANT (card switch ``pricing.lium`` defaults to false):
no Lium request is ever made, and `TargonPayoutFeed.effective_card()` stays
byte-identical to v1.3.0 (floor-clamped, card-capped) until the owner flips
the switch on the published card (`scripts/set_pricing_flags.py --lium on`)
— every v1.3.3+ validator then adopts market + 10% on its next epoch read.
"""

from __future__ import annotations

import json
import os
import urllib.request

# The markup over the winning market price (the "+10%").
MARKET_MARKUP_FRAC = 0.10
CACHE_METRIC = "lium-earned-p75-7d"

_LIUM_QUERY_URL = "https://grafana.lium.io/api/ds/query"
_LIUM_DATASOURCE = {
    "type": "grafana-postgresql-datasource",
    "uid": "eflbe16w0qigwd",
}
_USER_AGENT = "kubetee-validator/0.1"

# Lium's own panel-7 query with $gpu_type = 'All', reduced to the selected
# Earned p75 column. Each node contributes its seven-day earned average;
# the percentile is over nodes, grouped by GPU type. Keep Lium's listing
# coverage (>=96 samples) and display minimum (>=3 nodes per type).
_EARNED_P75_SQL = """
WITH node7 AS (
  SELECT executor_id, gpu_type, max(gpu_count) AS gpu_count,
         avg(rented::int)::float8 AS rented_share,
         0.95 * avg(CASE WHEN rented THEN asking_price_per_gpu ELSE 0 END)::float8 AS earned
  FROM executor_price_history
  WHERE snapshot_time > now() - interval '7 days' AND gpu_type IS NOT NULL AND ('All' = 'All' OR gpu_type = 'All')
  GROUP BY 1, 2
  HAVING count(*) >= 96
)
SELECT gpu_type AS "GPU type",
       count(*) AS "Nodes",
       percentile_cont(0.75) WITHIN GROUP (ORDER BY earned) AS "Earned p75"
FROM node7
GROUP BY 1
HAVING count(*) >= 3
ORDER BY sum(gpu_count) DESC
""".strip()


class MarketFeedError(RuntimeError):
    """A Lium market snapshot could not be produced."""


def _class_of_type(raw_type: str) -> str | None:
    """Map a Lium `gpu_type` name to a KubeTEE card class, or None.

    "RTX 6000" must not match "RTX A6000" (Ampere) and RTX PRO 5000 must
    not match at all; GB300-class (Vera Rubin) names contain "B300" and
    collapse into B300.
    """
    text = str(raw_type).upper()
    if "RTX PRO 6000" in text or "RTX 6000" in text:
        return "RTX6000"
    for klass in ("H100", "H200", "B200", "B300"):
        if klass in text:
            return klass
    return None


def _per_class_from_rows(rows: list[dict]) -> dict[str, float]:
    """Collapse per-type seven-day Earned p75s to the highest SKU/class."""
    per_class: dict[str, float] = {}
    for row in rows:
        klass = _class_of_type(row.get("GPU type", ""))
        if klass is None:
            continue
        value = row.get("Earned p75")
        try:
            value = float(value)
        except (TypeError, ValueError):
            continue
        if value <= 0:
            continue
        if value > per_class.get(klass, 0.0):
            per_class[klass] = value
    return per_class


def parse_market_response(payload: dict) -> dict[str, float]:
    """Extract per-class $/card from a Grafana /api/ds/query response."""
    result = (payload.get("results") or {}).get("A")
    if not isinstance(result, dict):
        raise MarketFeedError("lium grafana: no query result")
    if result.get("status") not in (None, 200):
        raise MarketFeedError(
            f"lium grafana: query status {result.get('status')}"
        )
    frames = result.get("frames") or []
    for frame in frames:
        if not isinstance(frame, dict):
            continue
        fields = [
            (f or {}).get("name")
            for f in (frame.get("schema") or {}).get("fields") or []
        ]
        columns = (frame.get("data") or {}).get("values") or []
        if not fields or len(columns) != len(fields):
            continue
        rows = [dict(zip(fields, values)) for values in zip(*columns)]
        per_class = _per_class_from_rows(rows)
        if not per_class:
            raise MarketFeedError("lium grafana: no usable per-class data")
        return per_class
    raise MarketFeedError("lium grafana: no data frame")


def fetch_lium_per_card_usd() -> dict[str, float]:
    """Live per-class seven-day Earned p75 ($/card/hr) from Lium."""
    body = json.dumps(
        {
            "queries": [
                {
                    "refId": "A",
                    "datasource": _LIUM_DATASOURCE,
                    "format": "table",
                    "rawSql": _EARNED_P75_SQL,
                }
            ],
            "from": "now-7d",
            "to": "now",
        }
    ).encode("utf-8")
    request = urllib.request.Request(
        _LIUM_QUERY_URL,
        data=body,
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": _USER_AGENT,
        },
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        payload = json.loads(response.read())
    if not isinstance(payload, dict):
        raise MarketFeedError("lium grafana: unexpected payload")
    return parse_market_response(payload)


def _cache_path() -> str:
    # Read lazily (not at import) so tests can redirect it per-run.
    return os.environ.get("KUBETEE_LIUM_CACHE") or os.path.expanduser(
        "~/.kubetee/lium_market_cache.json"
    )


def load_lium_cache() -> dict[str, float] | None:
    """Last known Lium seven-day Earned p75s from the on-disk cache, or None."""
    try:
        with open(_cache_path(), "r", encoding="utf-8") as handle:
            payload = json.load(handle)
    except (OSError, json.JSONDecodeError):
        return None
    if payload.get("metric") != CACHE_METRIC:
        return None
    per_card = payload.get("per_card_usd")
    if not isinstance(per_card, dict):
        return None
    return {
        str(k).upper(): float(v)
        for k, v in per_card.items()
        if isinstance(v, (int, float)) and float(v) > 0
    } or None


def save_lium_cache(per_card: dict[str, float]) -> None:
    """Best-effort cache write; never blocks the cycle."""
    try:
        os.makedirs(os.path.dirname(_cache_path()), exist_ok=True)
        with open(_cache_path(), "w", encoding="utf-8") as handle:
            json.dump(
                {"metric": CACHE_METRIC, "per_card_usd": per_card}, handle
            )
    except OSError:
        pass


def market_price(
    klass: str,
    lium: dict[str, float] | None,
    targon: dict[str, float] | None,
) -> float | None:
    """(1 + MARKET_MARKUP_FRAC) x the market's best $/card for one class.

    The market is the HIGHEST of the Lium seven-day Earned p75 and the
    Targon live payout for that class. Returns None when neither feed has a
    value
    (the caller then pays the static floor).
    """
    values: list[float] = []
    for feed in (lium, targon):
        value = (feed or {}).get(klass)
        if value is not None and float(value) > 0:
            values.append(float(value))
    if not values:
        return None
    return (1.0 + MARKET_MARKUP_FRAC) * max(values)
