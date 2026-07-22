# Running a KubeTEE Validator

This guide covers the validator runtime only. It does not create a real
subnet, hold stake custody, or deploy Rancher. Keep those responsibilities
with the operator and their approved Bittensor and infrastructure workflows.

## Security model

Run the validator host with only the signing hotkey it needs. Keep the coldkey
and any staking proxy outside that host, preferably in cold storage or on a
separately controlled signing system. Do not copy wallet recovery material,
Rancher credentials, CA material, or production configuration into Git, issues,
shell history, or logs.

Use a Rancher credential with only the authority the validator requires:
cluster and node GET/list plus the guarded cluster DELETE used for
deregistration reconciliation. It must not have admin, create, update, patch,
or unrelated-resource authority. Missing or ambiguous trust data fails closed;
it is not a reason to broaden permissions.

## Select an image

The external runtime defaults to
`ghcr.io/kubetee-ai/kubetee-subnet:latest`. Pull and inspect that tag before a
planned deployment window:

```bash
docker pull ghcr.io/kubetee-ai/kubetee-subnet:latest
docker image inspect --format '{{index .RepoDigests 0}}' \
  ghcr.io/kubetee-ai/kubetee-subnet:latest
```

For a long-running Finney deployment, set `KUBETEE_VALIDATOR_IMAGE` in the
private environment file to the discovered immutable digest. Review and choose
that digest before restarting; do not rely on a moving tag for an unattended
mainnet process.

## Localnet only

From the root KubeTEE workspace, start the disposable learning stack:

```bash
make subnet
```

It creates a local chain and a disposable Rancher environment. The seeded
`owner / alice / bob` identities are disposable localnet identities only. You
must never use those identities on Finney.

Inspect the local subnet through the compose network and follow validator logs:

```bash
docker compose -p kubetee-subnet exec validator \
  btcli subnets list --network ws://chain:9944
docker compose -p kubetee-subnet logs -f validator
```

`make clean` is a destructive local reset: it removes the local stack's
volumes and returns the learning environment to a fresh state. It is not a
Finney recovery procedure.

## Finney mainnet

Use the external runtime only with an existing Finney subnet, registered
validator hotkey, operator-managed Rancher, and explicit production inputs.
KubeTEE documents no public KubeTEE testnet. Do not carry localnet values,
wallets, or assumptions into this environment.

Create a private `validator.env` outside the repository. The file contains
these names only; source each value from the appropriate operator-controlled
system.

| Variable | Purpose |
| --- | --- |
| `KUBETEE_VALIDATOR_IMAGE` | Immutable published validator image digest. |
| `BT_NETWORK` | Finney network or operator-approved RPC endpoint. |
| `BT_WALLET` | Existing validator wallet name. |
| `BT_WALLET_HOTKEY` | Existing validator signing hotkey name. |
| `BITTENSOR_WALLET_DIR` | Host directory holding the validator wallet. |
| `KUBETEE_SUBNET_NETUID` | Existing KubeTEE subnet identifier. |
| `KUBETEE_OWNER_HOTKEY` | Registered subnet-owner hotkey. |
| `KUBETEE_VALIDATOR_HOTKEY` | Registered validator hotkey. |
| `RANCHER_URL` | HTTPS origin of the operator-managed Rancher service. |
| `RANCHER_BEARER_TOKEN` | Least-privilege Rancher credential. |
| `RANCHER_CA_FILE` | Operator-controlled Rancher CA file path, if required. |
| `KUBETEE_CHAIN_NETWORK` | Exact network identity in the enrollment binding. |

Before starting, protect the file and validate the rendered configuration.
Run these commands from the root KubeTEE workspace, where the external compose
files live:

```bash
chmod 600 validator.env
docker compose --env-file validator.env \
  -f docker-compose.subnet.external.yml \
  -f docker-compose.rancher.external.yml config -q
```

When the configuration review is complete, start only the external runtime:

```bash
docker compose --env-file validator.env -p kubetee-subnet-ext \
  -f docker-compose.subnet.external.yml \
  -f docker-compose.rancher.external.yml up -d --wait
```

`make subnet-external` runs the same external composition when its required
environment is already supplied. The explicit compose command above makes the
private environment file and the two production-shaped files visible for
preflight review.

Verify observable behavior without printing credentials:

```bash
docker compose -p kubetee-subnet-ext \
  -f docker-compose.subnet.external.yml \
  -f docker-compose.rancher.external.yml logs --tail=200 validator
docker compose -p kubetee-subnet-ext \
  -f docker-compose.subnet.external.yml \
  -f docker-compose.rancher.external.yml exec validator \
  curl --fail --silent http://127.0.0.1:9100/metrics
```

A startup error, missing validator permit, or uncertainty reaching Rancher is
fail-closed: investigate the cause and retain the prior safe state rather than
forcing weights, changing chain state, or widening Rancher access.

## Stop, upgrade, and rollback

Stop the external runtime without removing unrelated infrastructure:

```bash
docker compose --env-file validator.env -p kubetee-subnet-ext \
  -f docker-compose.subnet.external.yml \
  -f docker-compose.rancher.external.yml down
```

For an upgrade, choose and record the new image digest before the restart.
Retain the prior digest so that a rollback is an explicit configuration change
followed by the same preflight and start steps. This guide intentionally gives
no generic destructive chain or Rancher recovery commands.

## Official Bittensor references

- [Validating in Bittensor](https://docs.learnbittensor.org/validators)
- [Managing your stakes](https://docs.learnbittensor.org/staking-and-delegation/managing-stake-btcli/)
- [Working with proxies](https://docs.learnbittensor.org/keys/proxies/working-with-proxies)
- [BTCLI reference](https://docs.learnbittensor.org/btcli)
