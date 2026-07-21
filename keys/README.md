# Dev Keys for KubeTEE single-node testing pyramid

This directory (and the approach) is inspired by fdn-subnet's use of explicit,
reproducible dev keys:

- fdn-subnet mounts `.swarm/keys/` (bootnode.key, nodeN.key, overwatch.key etc.)
  read-only into containers.
- fdn-subnet documents and hardcodes **PUBLIC Frontier dev-genesis keys**
  (Alith, Baltathar, Charleth, ...) in `scripts/register_live_subnet.py` for
  `--local-dev`. These are the substrate-style well-known accounts that a
  `--dev` chain pre-funds. See big warning banner there.

## For kubetee-subnet (bittensor localnet)

We do the equivalent with **pinned dev seeds** (not random `new_coldkey`)
for the g004 triad (D7):

- `DEV_ALICE_SEED` — classic substrate Alice (pre-funded by
  subtensor-localnet). **alice is the validator**: registered and staked on
  the subnet, signs `set_weights` (`BT_WALLET=alice` in compose). It also
  stays the funding source.
- `DEV_OWNER_SEED` — pinned dev seed for the subnet owner wallet (the one
  that does `subnet create`, registers its hotkey to get a UID, calls
  `sudo start`, sets hypers, and is the **recycle target** the owner share
  of weights points at).
- `DEV_BOB_SEED` — pinned dev seed for the **bob miner wallet**: the miner
  whose Rancher cluster (labeled `kubetee.ai/miner-hotkey`) the basic
  validator scores. Replaces the retired legacy sample `miner` wallet (its
  pinned seed constant was removed with it). Must be an ordinary random hex
  seed (#20): the earlier all-`0x0b` value serialised into an unreadable
  keyfile, so bob could never sign or register.
  Hotkey ss58: `5FsfgiqMdQzgqtJQLb15ox6MzcZLvFG55vtAsy4TYuDCEEFs`.

Result:
- Owner coldkey/hotkey SS58 is always the same:
  `5FLbZav21bAsjH5SAdmJZwTP5C4b3bcaaWqC6GSmGmsbzUJ9`
- First registration on a fresh subnet tends to land on a stable UID
  (commonly 0 for the creator).
- UIDs are resolved from the metagraph by hotkey SS58
  (`KUBETEE_OWNER_HOTKEY` / `KUBETEE_VALIDATOR_HOTKEY` in compose) — there
  is no `TARGET_UID` anymore.
- The validator container entrypoint + setup is fully deterministic.

## How it works here

- `scripts/setup_single_node.py` (and the validator container entrypoint that
  calls it) uses `btcli wallet regen-coldkey --seed <DEV_...>` instead of
  `new_coldkey`.
- The wallet files land in the container's `/root/.bittensor`, backed by the
  `bittensor-wallets` **named docker volume** — isolated from the host, not a
  bind-mount of your `~/.bittensor`. They are regenerated from the pinned seeds
  on every `up` (`down -v` wipes the volume; the next `up` recreates them).
  Inspect them with `docker compose exec validator btcli wallet ...`.
- Funding still goes through Alice (regen from its seed) to the resolved owner
  address (or the known `DEV_OWNER_COLD_SS58`).

## Warnings

**These seeds are PUBLIC and only for local single-node testnet use.**

They control **nothing** on any real chain. Never use the resulting wallets
against testnet (`--network test`) or mainnet (`finney`).

If you need your own keys for a longer-lived local experiment, run with
different seeds or let the script create fresh ones (the code falls back
gracefully).

See also:
- `scripts/setup_single_node.py` (the constants + ensure_dev_wallet)
- `SUBNET.md` (how to run the stack)
- docker-compose.yml + Dockerfile (the self-setup flow)
- fdn-subnet's `scripts/register_live_subnet.py` and `docs/runbooks/key-management.md` for the source pattern.

## Optional: pre-placing key files

If you want a fdn-style `keys/` layout for bittensor:

- You can place mnemonic/seed files here.
- Or pre-populate the `bittensor-wallets` volume (e.g. via
  `docker compose exec validator ...`) from a known seed.
- Extend the entrypoint/setup to accept `KUBETEE_KEYS_DIR` and copy/import
  before running btcli.

For the basic pyramid the pinned seeds + regen-coldkey are sufficient and
match the "once setup exits, run validator" contract.
