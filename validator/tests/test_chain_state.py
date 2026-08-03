"""chain_state: hotkey-seed derivation + metagraph mapping (no chain calls)."""

import pytest

# Skip the whole module if the vendored bittensor SDK is not importable.
bt = pytest.importorskip("bittensor")

from chain_state import Miner, derive_hotkey_keypair


def test_derive_from_mnemonic():
    kp = derive_hotkey_keypair("abandon " * 11 + "about")
    addr = kp.ss58_address
    assert isinstance(addr, str) and addr.startswith("5") and len(addr) >= 47
    # deterministic
    assert (
        derive_hotkey_keypair("abandon " * 11 + "about").ss58_address == addr
    )


def test_derive_from_hex_seed():
    kp = derive_hotkey_keypair("0x" + "01" * 32)
    assert isinstance(kp.ss58_address, str)


def test_derive_empty_raises():
    with pytest.raises(ValueError):
        derive_hotkey_keypair("   ")


def test_miner_dataclass():
    m = Miner(uid=1, hotkey="5abc", is_validator=False)
    assert m.uid == 1 and m.hotkey == "5abc"
