"""On-chain state: hotkey-seed wallet, metagraph read, and set_weights.

Only the hotkey is ever derived — the validator never touches a coldkey or a
keyfile. The seed-derived sr25519 Keypair satisfies the SDK's Signer protocol,
so it is passed directly as the wallet.
"""

from __future__ import annotations

from dataclasses import dataclass

import bittensor as bt
from bittensor.keyfiles import Keypair
from bittensor.sp_core import CRYPTO_SR25519


@dataclass(frozen=True)
class Miner:
    """A metagraph neuron, reduced to what scoring needs."""

    uid: int
    hotkey: str
    is_validator: bool


def derive_hotkey_keypair(seed: str) -> Keypair:
    """Derive the validator hotkey keypair from a seed (mnemonic or hex)."""
    seed = seed.strip()
    if not seed:
        raise ValueError("VALIDATOR_HOTKEY_SEED is empty")
    if seed.startswith("0x"):
        return Keypair.create_from_seed(
            bytes.fromhex(seed[2:]), CRYPTO_SR25519
        )
    return Keypair.create_from_mnemonic(seed, CRYPTO_SR25519)


class ChainState:
    """Thin wrapper over the vendored bittensor v11 SDK."""

    def __init__(self, network: str, endpoint: str, hotkey_seed: str) -> None:
        network = (network or "finney").strip()
        self._subtensor = bt.Subtensor(endpoint or network)
        self._keypair = derive_hotkey_keypair(hotkey_seed)

    @property
    def endpoint(self) -> str:
        """Resolved websocket URL the SDK is actually using."""
        return self._subtensor.endpoint

    @property
    def hotkey_ss58(self) -> str:
        return self._keypair.ss58_address

    @property
    def keypair(self):
        """The validator's sr25519 keypair (used for set_weights + proxy auth)."""
        return self._keypair

    def metagraph(self, netuid: int) -> list[Miner]:
        """Read the subnet metagraph as a list of miners keyed by uid."""
        graph = self._subtensor.subnets.metagraph(netuid, commitments=False)
        if graph is None:
            raise RuntimeError(f"no metagraph for netuid {netuid}")
        # Cache the raw metagraph for emission/price reads
        self._last_metagraph = graph
        miners: list[Miner] = []
        for neuron in getattr(graph, "neurons", []):
            miners.append(
                Miner(
                    uid=int(neuron.uid),
                    hotkey=str(neuron.hotkey),
                    is_validator=bool(
                        getattr(neuron, "validator_permit", False)
                    ),
                )
            )
        return miners

    def emissions(self) -> dict[int, float]:
        """On-chain emission per UID (alpha tokens, from last epoch)."""
        mg = getattr(self, "_last_metagraph", None)
        if mg is None or not hasattr(mg, "raw") or not mg.raw:
            return {}
        raw_em = mg.raw.get("emission", [])
        return {
            uid: float(em) / 1e9 if em else 0.0
            for uid, em in enumerate(raw_em)
        }

    def alpha_out_emission(self) -> float:
        """Alpha minted per block for the subnet (in TAO, from chain storage)."""
        mg = getattr(self, "_last_metagraph", None)
        if mg is None or not hasattr(mg, "raw") or not mg.raw:
            return 0.0
        raw = mg.raw.get("alpha_out_emission", 0)
        return float(raw) / 1e9 if raw else 0.0

    def moving_price(self) -> float:
        """On-chain EMA alpha->TAO price (from metagraph)."""
        mg = getattr(self, "_last_metagraph", None)
        if mg is None:
            return 0.0
        return float(getattr(mg, "moving_price", 0.0) or 0.0)

    def spot_price(self) -> float:
        """On-chain spot alpha->TAO price from the metagraph."""
        mg = getattr(self, "_last_metagraph", None)
        if mg is None:
            return 0.0
        return float(getattr(mg, "price", 0.0) or 0.0)

    def emission_pool_usd(
        self, tao_usd: float, miner_share: float = 0.41
    ) -> float:
        """Total USD value of the emission pool per epoch (from on-chain emissions).

        Uses the actual emission[] array from the metagraph (the real alpha
        paid last epoch), not the EMA-based Targon formula which is near-zero
        for new subnets.

        pool_usd = total_emission_alpha × tao_usd × spot_price
        """
        emissions = self.emissions()
        if not emissions:
            return 1.0
        total_alpha = sum(emissions.values())
        spot = self.spot_price()
        if total_alpha <= 0 or spot <= 0 or tao_usd <= 0:
            return 1.0
        return total_alpha * tao_usd * spot

    def hyperparams(self, netuid: int) -> dict | None:
        """Subnet hyperparameters as a flat name -> value map, or None."""
        try:
            raw = self._subtensor.subnets.subnet_hyperparameters(netuid)
        except Exception:  # noqa: BLE001 - best-effort read
            return None
        if not isinstance(raw, dict):
            return None
        out: dict[str, object] = {}
        for key, value in raw.items():
            if (
                isinstance(value, (int, float, str, bool))
                and value is not None
            ):
                out[str(key)] = value
        return out

    def tempo(self, netuid: int) -> int | None:
        """Subnet epoch length in blocks, if available."""
        hyperparams = self.hyperparams(netuid)
        if not hyperparams:
            return None
        for attr in ("tempo", "blocks_per_epoch", "epoch_length"):
            value = hyperparams.get(attr)
            if isinstance(value, (int, float)):
                return int(value)
        return None

    def epoch_progress(self, netuid: int) -> tuple[int, int, int] | None:
        """Epoch state: (tempo, blocks_since_last_step, blocks_until_next_epoch)."""
        hyperparams = self.hyperparams(netuid)
        if not hyperparams:
            return None
        tempo = None
        for attr in ("tempo", "blocks_per_epoch", "epoch_length"):
            v = hyperparams.get(attr)
            if isinstance(v, (int, float)):
                tempo = int(v)
                break
        since = None
        for attr in (
            "blocks_since_last_step",
            "blocks_since_last_epoch",
            "steps_since_last_epoch",
        ):
            v = hyperparams.get(attr)
            if isinstance(v, (int, float)):
                since = int(v)
                break
        until = None
        for attr in ("blocks_until_next_epoch", "blocks_until_epoch"):
            v = hyperparams.get(attr)
            if isinstance(v, (int, float)):
                until = int(v)
                break
        if tempo is None:
            return None
        return tempo, since, until

    def set_weights(
        self, netuid: int, weights_by_uid: dict[int, float]
    ) -> None:
        """Set on-chain weights, signed by the hotkey keypair."""
        if not weights_by_uid:
            raise ValueError("weights_by_uid must not be empty")
        # Use this instance's endpoint. bt.set_weights() defaults to
        # network="finney" and opens a *second* client on the public pool,
        # ignoring SUBTENSOR_ENDPOINT (readers with a private Finney node
        # then hit entrypoint-finney / lite.chain / lite.sub.latent.to).
        result = self._subtensor.execute(
            bt.SetWeights(netuid=netuid, weights=weights_by_uid),
            self._keypair,
            retries=2,
        )
        result.raise_for_failure()
