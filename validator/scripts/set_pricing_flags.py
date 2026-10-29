#!/usr/bin/env python3
"""Flip the published price card's pricing switches (v1.3.3, owner only).

The card's flat `targon_pricing` / `lium_pricing` fields select the
pricing mode every v1.3.3+ validator prices in, read from price-card.json
each epoch. This script is the owner's on-the-fly dial:

  targon_pricing=true   the live Targon clamp pulls the card DOWN toward
                        SN4 payouts, floored per class (the v1.2.0+ default)
  targon_pricing=false  pay the flat card; no feed pull-down
  lium_pricing=true     market + 10%: max(floor, 1.10 x highest(Lium,
                        Targon)), no card cap
  lium_pricing=false    Lium medians are display-only on the dashboard

It GETs the live price-card.json, flips the requested switches, and PUTs
it back byte-preserving (epoch/prices/floors untouched — only the
switches and published_at change). The owner validator PRESERVES the
published switches on every re-publish (validator.py `_publisher_pricing`),
so the flip survives and propagates to every reader within one epoch.

Usage:
  KUBETEE_HIPPIUS_ACCESS_KEY=... KUBETEE_HIPPIUS_SECRET_KEY=... \
      python scripts/set_pricing_flags.py --lium on
  python scripts/set_pricing_flags.py --show          # read-only peek

Credentials come from the same KUBETEE_HIPPIUS_* env vars as the owner
validator (never committed).
"""

from __future__ import annotations

import argparse
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from hippius_store import (
    DEFAULT_CARD_KEY,
    HippiusError,
    HippiusStore,
)  # noqa: E402
from price_card import parse_price_card  # noqa: E402


def _parse_flag(raw: str) -> bool | None:
    value = (raw or "").strip().lower()
    if value in {"on", "1", "true", "yes"}:
        return True
    if value in {"off", "0", "false", "no"}:
        return False
    return None


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Flip the published price card's pricing switches "
        "(owner only)."
    )
    parser.add_argument(
        "--targon",
        choices=["on", "off"],
        help="the Targon supply-side clamp switch",
    )
    parser.add_argument(
        "--lium",
        choices=["on", "off"],
        help="the Lium market + 10% switch",
    )
    parser.add_argument(
        "--show",
        action="store_true",
        help="read-only: print the current card + switches, change nothing",
    )
    args = parser.parse_args()

    access = os.environ.get("KUBETEE_HIPPIUS_ACCESS_KEY", "").strip()
    secret = os.environ.get("KUBETEE_HIPPIUS_SECRET_KEY", "").strip()
    if not args.show and not (access and secret):
        print(
            "ERROR: KUBETEE_HIPPIUS_ACCESS_KEY + KUBETEE_HIPPIUS_SECRET_KEY "
            "required to flip (use --show for a read-only peek)",
            file=sys.stderr,
        )
        return 2

    try:
        card = HippiusStore("", "").get_json(DEFAULT_CARD_KEY)
    except HippiusError as exc:
        print(f"ERROR: cannot read published card: {exc}", file=sys.stderr)
        return 1

    parsed = parse_price_card(card)
    if parsed is None:
        print(
            f"ERROR: published card is not a valid v1 card: {card!r}",
            file=sys.stderr,
        )
        return 1
    prices, floors, pricing = parsed

    print(
        f"published card: epoch={card.get('epoch')} "
        f"prices={prices} floors={floors or {}}"
    )
    print(f"pricing switches: {pricing}")

    if args.show:
        return 0

    desired = dict(pricing)
    for name, arg in (("targon", args.targon), ("lium", args.lium)):
        if arg is None:
            continue
        value = _parse_flag(arg)
        if value is None:
            print(f"ERROR: bad --{name} value {arg!r}", file=sys.stderr)
            return 2
        desired[name] = value
    if desired == pricing:
        print("no change — published switches already match; not writing")
        return 0

    # Byte-preserving flip: keep every other field exactly as published
    # (epoch, prices, floors, version) and only move the switches +
    # published_at. An in-place mutation of the fetched object — never a
    # rebuild from defaults — so nothing else can drift in the same write.
    for name, value in desired.items():
        card[f"{name}_pricing"] = value
    card["published_at"] = time.time()
    try:
        HippiusStore(access, secret).put_json(DEFAULT_CARD_KEY, card)
    except HippiusError as exc:
        print(f"ERROR: cannot write card: {exc}", file=sys.stderr)
        return 1
    print(f"pricing switches now: {desired}")
    print(
        "every v1.3.3+ validator adopts this on its next epoch read; "
        "the owner validator preserves it on re-publish"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
