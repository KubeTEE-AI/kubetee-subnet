"""Public static card consumes full epoch payload without affecting cards."""

import json
from dashboard import build_html, build_dashboard_json


def test_missing_chutes_has_no_zero_or_active_cards():
    body = build_html({})
    assert "Chutes SN64 · median earnings" in body
    assert "Chutes unavailable" in body
    card = body.split("Chutes SN64 · median earnings", 1)[1].split(
        "GPU inventory", 1
    )[0]
    assert "$0" not in card
    assert "static_dynamic_probe" not in body


def test_epoch_card_serializes_clamps_and_escapes():
    snapshot = {
        "chutes_earnings": {
            "per_class_usd": {
                "H200": 1.2345,
                "B300": 99.0,
                "B200": 8.0,
                "RTX6000": 1.5,
            },
            "samples": {"H200": 4, "B300": 1, "B200": 2, "RTX6000": 3},
            "observed_at": "2026-11-07T00:00Z",
            "observation_window": "current_24h",
            "stale": False,
            "bucket": 314,
            "lte_date": "bad <script>",
        }
    }
    body = build_html(snapshot)
    assert body.count("H200 · 4 miners") == 1
    for gpu, value in (
        ("H200", "$1.23/GPU/hr"),
        ("B300", "$99.00/GPU/hr"),
        ("RTX6000", "$1.50/GPU/hr"),
    ):
        assert gpu in body and value in body
        assert "bad <script>" not in body
    card = body.split("Chutes SN64 · median earnings", 1)[1].split(
        "GPU inventory", 1
    )[0]
    positions = [
        card.index(gpu)
        for gpu in ("B300", "B200", "H200", "RTX6000")
        if gpu in card
    ]
    assert positions == sorted(positions)
    assert "4 miner" in body
    assert json.loads(
        json.dumps(build_dashboard_json(snapshot)["chutes_earnings"])
    )
    assert "<script" not in body


def test_snapshot_does_not_change_pricing_or_weights():
    payload = {
        "card": {"H200": 2},
        "effective_card": {"H200": 2},
        "miners": [],
        "chutes_epoch": {"H200": 100},
    }
    result = build_dashboard_json(payload)
    assert result["effective_card"] == {"H200": 2}
