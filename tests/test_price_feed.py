"""Taostats price feed client (scoring v3, TDD).

Spec: kubetee/docs/superpowers/specs/2026-07-24-scoring-v3-usd-weights-design.md.
"""

from __future__ import annotations

import json
import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent / "scripts"))

from price_feed import (
    PriceFeedError,
    PriceQuote,
    TaostatsPriceFeed,
    check_divergence,
)

TAO_PAYLOAD = {"data": [{"price": "192.05"}]}
POOL_PAYLOAD = {"data": [{"netuid": 90, "price": "0.0067"}]}


class FakeOpener:
    def __init__(self, responses=None, error=None):
        self.responses = responses or {}
        self.error = error
        self.calls = []

    def __call__(self, url, headers, timeout):
        self.calls.append({"url": url, "headers": headers, "timeout": timeout})
        if self.error is not None:
            raise self.error
        for fragment, payload in self.responses.items():
            if fragment in url:
                return json.dumps(payload).encode()
        raise AssertionError(f"unexpected url {url}")


def make_feed(opener, api_key="secret123", netuid=90):
    return TaostatsPriceFeed(
        api_key=api_key, netuid=netuid, opener=opener, clock=lambda: 1000.0
    )


def test_fetch_combines_tao_and_pool_prices():
    opener = FakeOpener(
        {"price/latest": TAO_PAYLOAD, "dtao/pool/latest": POOL_PAYLOAD}
    )
    quote = make_feed(opener).fetch()
    assert isinstance(quote, PriceQuote)
    assert quote.tao_usd == pytest.approx(192.05)
    assert quote.alpha_tao == pytest.approx(0.0067)
    assert quote.usd_per_alpha == pytest.approx(192.05 * 0.0067)
    assert quote.fetched_at == 1000.0


def test_auth_header_gets_tao_prefix_and_netuid_in_url():
    opener = FakeOpener(
        {"price/latest": TAO_PAYLOAD, "dtao/pool/latest": POOL_PAYLOAD}
    )
    make_feed(opener, api_key="abc").fetch()
    assert len(opener.calls) == 2
    for call in opener.calls:
        assert call["headers"]["Authorization"] == "tao-abc"
    assert any("netuid=90" in c["url"] for c in opener.calls)


def test_existing_tao_prefix_not_doubled():
    opener = FakeOpener(
        {"price/latest": TAO_PAYLOAD, "dtao/pool/latest": POOL_PAYLOAD}
    )
    make_feed(opener, api_key="tao-abc").fetch()
    assert opener.calls[0]["headers"]["Authorization"] == "tao-abc"


@pytest.mark.parametrize(
    "tao, pool",
    [
        ({"data": []}, POOL_PAYLOAD),
        ({"nope": 1}, POOL_PAYLOAD),
        (TAO_PAYLOAD, {"data": [{"netuid": 90, "price": "0"}]}),
        (TAO_PAYLOAD, {"data": [{"netuid": 90, "price": "nan"}]}),
        (TAO_PAYLOAD, {"data": [{"netuid": 90}]}),
        ({"data": [{"price": "-1"}]}, POOL_PAYLOAD),
    ],
)
def test_malformed_or_nonpositive_payloads_fail_closed(tao, pool):
    opener = FakeOpener({"price/latest": tao, "dtao/pool/latest": pool})
    with pytest.raises(PriceFeedError):
        make_feed(opener).fetch()


def test_transport_error_becomes_price_feed_error():
    opener = FakeOpener(error=OSError("connection refused"))
    with pytest.raises(PriceFeedError):
        make_feed(opener).fetch()


def test_invalid_json_becomes_price_feed_error():
    class BadOpener:
        def __call__(self, url, headers, timeout):
            return b"<html>rate limited</html>"

    with pytest.raises(PriceFeedError):
        make_feed(BadOpener()).fetch()


def test_api_key_required():
    with pytest.raises(ValueError):
        TaostatsPriceFeed(api_key="", netuid=90, opener=FakeOpener())


def test_divergence_check():
    assert check_divergence(0.0067, 0.0068, max_frac=0.10) is False
    assert check_divergence(0.0067, 0.0100, max_frac=0.10) is True
    assert (
        check_divergence(0.0067, None, max_frac=0.10) is False
    )  # no chain ref
    assert (
        check_divergence(0.0067, 0.0, max_frac=0.10) is False
    )  # unusable ref
