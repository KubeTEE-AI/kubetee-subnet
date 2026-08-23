"""ChainState.set_weights must use the configured endpoint, not public Finney."""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from chain_state import ChainState


def _chain(fake=None):
    fake = fake or MagicMock()
    fake.endpoint = "ws://subtensor.example.com:9944"
    with (
        patch("chain_state.bt.Subtensor", return_value=fake),
        patch("chain_state.derive_hotkey_keypair", return_value="kp"),
    ):
        return (
            ChainState("finney", "ws://subtensor.example.com:9944", "seed"),
            fake,
        )


def test_set_weights_executes_on_the_instance_client():
    """Regression: bt.set_weights() defaults to network=finney and opens a
    second client on entrypoint-finney / lite.chain / lite.sub.latent.to,
    ignoring SUBTENSOR_ENDPOINT."""
    chain, fake = _chain()
    assert chain.endpoint == "ws://subtensor.example.com:9944"
    chain.set_weights(90, {0: 0.8, 56: 0.2})

    fake.execute.assert_called_once()
    intent, wallet = fake.execute.call_args[0]
    assert wallet == "kp"
    assert intent.netuid == 90
    fake.execute.return_value.raise_for_failure.assert_called_once()


def test_emissions_use_typed_neuron_balance():
    chain, _fake = _chain()
    chain._last_metagraph = SimpleNamespace(
        neurons=[
            SimpleNamespace(uid=0, emission=SimpleNamespace(amount=1.25)),
            SimpleNamespace(uid=56, emission=SimpleNamespace(amount=0.0)),
        ]
    )
    assert chain.emissions() == {0: 1.25, 56: 0.0}


def test_epoch_progress_uses_cached_metagraph():
    chain, _fake = _chain()
    chain._last_metagraph = SimpleNamespace(
        tempo=360, blocks_since_last_step=40
    )
    assert chain.epoch_progress(90) == (360, 40, 320)
    assert chain.tempo(90) == 360


def test_spot_and_moving_price_from_metagraph():
    chain, _fake = _chain()
    chain._last_metagraph = SimpleNamespace(price=0.0125, moving_price=0.01)
    assert chain.spot_price() == 0.0125
    assert chain.moving_price() == 0.01


def test_weights_rate_limit_uses_typed_namespace():
    fake = MagicMock()
    fake.hyperparameters.weights_rate_limit.return_value = 100
    chain, _ = _chain(fake)
    assert chain.weights_rate_limit(90) == 100
    fake.hyperparameters.weights_rate_limit.assert_called_once_with(90)
