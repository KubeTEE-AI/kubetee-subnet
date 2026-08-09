"""version.py: semver helpers + validator_version() env override."""

from version import parse_semver, validator_version, version_at_least


def test_parse_semver_core():
    assert parse_semver("1.0.0") == (1, 0, 0)
    assert parse_semver("v1.2.3") == (1, 2, 3)
    assert parse_semver("1.0.0-rc1") == (1, 0, 0)
    assert parse_semver("") is None
    assert parse_semver("not-a-version") is None


def test_version_at_least():
    assert version_at_least("1.0.1", "1.0.0") is True
    assert version_at_least("1.0.0", "1.0.1") is False
    assert version_at_least("1.0.1", "1.0.1") is True
    assert version_at_least("", "1.0.0") is False
    assert version_at_least("1.0.0", "") is True  # bad minimum → allow


def test_validator_version_env_override(monkeypatch):
    monkeypatch.delenv("KUBETEE_VALIDATOR_VERSION", raising=False)
    from version import __version__

    assert validator_version() == __version__
    monkeypatch.setenv("KUBETEE_VALIDATOR_VERSION", "v2.3.4")
    assert validator_version() == "2.3.4"
