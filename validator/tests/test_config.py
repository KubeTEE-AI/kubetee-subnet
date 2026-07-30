import os
import pytest

from config import ConfigError, load_config

BASE = {
    "SUBNET_NETUID": "90",
    "VALIDATOR_HOTKEY_SEED": "seed words here",
    "RANCHER_URL": "https://rancher.example.com",
    "RANCHER_BEARER_TOKEN": "tok",
    "TAOSTATS_API_KEY": "tao-key",
}


# All config env keys we care about; clear any leaked values each test.
_ALL_KEYS = [
    "SUBNET_NETUID", "VALIDATOR_HOTKEY_SEED", "RANCHER_URL",
    "RANCHER_BEARER_TOKEN", "RANCHER_CA_FILE", "TAOSTATS_API_KEY",
    "KUBETEE_OWNER_UID", "KUBETEE_CYCLE_SECONDS", "KUBETEE_WINDOW_HOURS",
    "KUBETEE_GPU_USD_PRICES", "KUBETEE_EMISSION_USD_PER_HOUR",
    "KUBETEE_TARGON_PAYOUT_ENABLED", "KUBETEE_TARGON_PRICE_FLOOR_FRAC",
    "KUBETEE_HIPPIUS_ACCESS_KEY", "KUBETEE_HIPPIUS_SECRET_KEY",
    "KUBETEE_METRICS_PORT", "KUBETEE_SKIP_RANCHER", "SUBTENSOR_ENDPOINT",
]


def _set(monkeypatch, **over):
    defaults = dict(BASE)
    defaults.update(over)
    for key in _ALL_KEYS:
        if key in defaults and defaults[key] is not None:
            monkeypatch.setenv(key, defaults[key])
        else:
            monkeypatch.delenv(key, raising=False)


def test_valid_config(monkeypatch):
    _set(monkeypatch)
    cfg = load_config()
    assert cfg.netuid == 90
    assert cfg.network == "finney"
    assert cfg.owner_uid == 0
    assert cfg.is_publisher is False
    assert cfg.emission_usd_per_epoch() == pytest.approx(0.0)


def test_missing_required_raises(monkeypatch):
    monkeypatch.delenv("TAOSTATS_API_KEY", raising=False)
    monkeypatch.setenv("SUBNET_NETUID", "90")
    with pytest.raises(ConfigError):
        load_config()


def test_usd_card_override(monkeypatch):
    _set(monkeypatch, KUBETEE_GPU_USD_PRICES='{"H100": 2.5, "B300": 9.0}')
    cfg = load_config()
    assert cfg.usd_card_override == {"H100": 2.5, "B300": 9.0}


def test_bad_usd_card(monkeypatch):
    _set(monkeypatch, KUBETEE_GPU_USD_PRICES="not-json")
    with pytest.raises(ConfigError):
        load_config()


def test_publisher_flag(monkeypatch):
    _set(
        monkeypatch,
        KUBETEE_HIPPIUS_ACCESS_KEY="ak",
        KUBETEE_HIPPIUS_SECRET_KEY="sk",
    )
    cfg = load_config()
    assert cfg.is_publisher is True


def test_emission_budget(monkeypatch):
    _set(
        monkeypatch,
        KUBETEE_EMISSION_USD_PER_HOUR="100",
        KUBETEE_WINDOW_HOURS="1.0",
    )
    cfg = load_config()
    assert cfg.emission_usd_per_epoch() == pytest.approx(100.0)


def test_netuid_must_be_int(monkeypatch):
    _set(monkeypatch, SUBNET_NETUID="ninety")
    with pytest.raises(ConfigError):
        load_config()
