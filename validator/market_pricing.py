"""Lium marketplace pricing feed — DORMANT in v1.3.1 (default OFF).

When ``KUBETEE_MARKET_PRICING=1`` the effective per-class price becomes

    max(static floor, (1 + MARKET_MARKUP_FRAC) * highest(Lium, Targon))

with NO card ceiling (owner decision 2026-10-29: an above-card market pays
market + 10%). The static floor always holds: when both feeds price a
class below the floor — or both are dark for it — the class pays the floor.

Lium input (owner decisions 2026-10-29):
- field: the provider-pricing dashboard's **median asking price of rented
  nodes** ("Median of rented nodes", panel 6 of grafana.lium.io's
  `price-your-gpus` dashboard), taken on the LATEST snapshot.
- SKU rule: one card class maps to several Lium GPU types (e.g.
  `NVIDIA B300 SXM6 AC` vs `NVIDIA B300 SXM6 PC`); the class takes the
  HIGHEST type value (B300 rule, applied to every multi-SKU class).
- fallback: a GPU type with NO rented nodes uses the median over ALL its
  listed nodes; a class no SKU rents therefore resolves to its
  all-listed median.
- source: Lium's public Grafana (`grafana.lium.io`), anonymous read —
  same query the dashboard runs against `executor_price_history`.

The Targon half is the existing `TargonPayoutFeed` resolution (live
`unitRate`; `maxPrice` fallback for unsupplied classes; `targetPrice` is
never read).

v1.3.1 ships this DORMANT: ``KUBETEE_MARKET_PRICING`` defaults to 0, no
Lium request is ever made, and `TargonPayoutFeed.effective_card()` stays
byte-identical to v1.3.0 (floor-clamped, card-capped). Activation is a
coordinated env flip across every weight-setting validator — flipping
only some makes their weights diverge (old: card-capped clamp; new:
market + 10%, uncapped).
"""

from __future__ import annotations

import json
import os
import urllib.request

# The markup over the winning market price (the "+10%").
MARKET_MARKUP_FRAC = 0.10

_LIUM_QUERY_URL = "https://grafana.lium.io/api/ds/query"
_LIUM_DATASOURCE = {
    "type": "grafana-postgresql-datasource",
    "uid": "eflbe16w0qigwd",
}
_USER_AGENT = "kubetee-validator/0.1"

# Lium's own "Market now" query (panel 6 of provider-pricing-v1), one row
# per gpu_type on the latest snapshot: the median asking price of RENTED
# nodes plus the median over ALL listed nodes (fallback when a type has no
# rented nodes). Lium's display HAVING (>=3 nodes per type) is kept.
_MARKET_SQL = """
SELECT gpu_type AS "type",
       count(*) AS "nodes",
       (percentile_cont(0.5) WITHIN GROUP (ORDER BY asking_price_per_gpu) FILTER (WHERE rented))::float8 AS "median_rented",
       (percentile_cont(0.5) WITHIN GROUP (ORDER BY asking_price_per_gpu))::float8 AS "median_all"
FROM executor_price_history
WHERE snapshot_time = (SELECT max(snapshot_time) FROM executor_price_history WHERE snapshot_time > now() - interval '1 day')
  AND gpu_type IS NOT NULL
GROUP BY 1
HAVING count(*) >= 3
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
    """Collapse per-type medians to per-class: rented median preferred
    (all-nodes median when the type has no rented nodes), highest SKU
    per class wins."""
    per_class: dict[str, float] = {}
    for row in rows:
        klass = _class_of_type(row.get("type", ""))
        if klass is None:
            continue
        value = row.get("median_rented")
        if value is None:
            value = row.get("median_all")
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
    """Live per-class market median ($/card/hr) from Lium's Grafana."""
    body = json.dumps(
        {
            "queries": [
                {
                    "refId": "A",
                    "datasource": _LIUM_DATASOURCE,
                    "format": "table",
                    "rawSql": _MARKET_SQL,
                }
            ],
            "from": "now-1h",
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
    """Last known Lium medians from the on-disk cache, or None."""
    try:
        with open(_cache_path(), "r", encoding="utf-8") as handle:
            payload = json.load(handle)
    except (OSError, json.JSONDecodeError):
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
            json.dump({"per_card_usd": per_card}, handle)
    except OSError:
        pass


def market_price(
    klass: str,
    lium: dict[str, float] | None,
    targon: dict[str, float] | None,
) -> float | None:
    """(1 + MARKET_MARKUP_FRAC) x the market's best $/card for one class.

    The market is the HIGHEST of the Lium median and the Targon live
    payout for that class. Returns None when neither feed has a value
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
