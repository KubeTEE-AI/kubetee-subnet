"""ChainState.set_weights must use the configured endpoint, not public Finney."""

from unittest.mock import MagicMock, patch

from chain_state import ChainState


def test_set_weights_executes_on_the_instance_client():
    """Regression: bt.set_weights() defaults to network=finney and opens a
    second client on entrypoint-finney / lite.chain / lite.sub.latent.to,
    ignoring SUBTENSOR_ENDPOINT."""
    fake = MagicMock()
    fake.endpoint = "ws://subtensor.example.com:9944"
    with (
        patch("chain_state.bt.Subtensor", return_value=fake),
        patch("chain_state.derive_hotkey_keypair", return_value="kp"),
    ):
        chain = ChainState(
            "finney", "ws://subtensor.example.com:9944", "seed"
        )
        assert chain.endpoint == "ws://subtensor.example.com:9944"
        chain.set_weights(90, {0: 0.8, 56: 0.2})

    fake.execute.assert_called_once()
    intent, wallet = fake.execute.call_args[0]
    assert wallet == "kp"
    assert intent.netuid == 90
    fake.execute.return_value.raise_for_failure.assert_called_once()
