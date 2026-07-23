# Running a KubeTEE Validator

This manual runs an already registered KubeTEE validator on Finney. It does
not create a subnet, hold stake custody, or administer Rancher. Keep those
responsibilities with the operator and their approved Bittensor and
infrastructure workflows.

## Enrollment operating mode

The subnet may operate in **permissionless** mode, where registered miners use
the supported enrollment flow, or **operator-bound** mode, where the operator
binds clusters before validation. This validator manual assumes the cluster is
already bound. Existing operator-bound clusters remain eligible for the same
validator checks; private platform endpoints and binding credentials are not
part of this public guide.

## Security model

Run the validator host with only the signing hotkey it needs. The mounted
wallet root contains only the signing hotkey and public coldkey metadata. Do not mount a normal/operator wallet root, private coldkey or recovery material.
Do not copy wallet recovery material, Rancher credentials, CA material, or
production configuration into Git, issues, shell history, or logs.

Use a Rancher credential with only the authority the validator requires:
cluster and node GET/list plus the guarded cluster DELETE used for
deregistration reconciliation. It must not have admin, create, update, patch,
or unrelated-resource authority. Missing or ambiguous trust data fails closed;
it is not a reason to broaden permissions.

## Finney mainnet

This is a public snapshot of the KubeTEE mainnet defaults recorded on
2026-07-23 with BTCLI v11 at block 8680289. Create a private environment file at `/secure/path/validator.env` outside the
repository. Use this one block and replace every angle-bracketed operator placeholder before starting:

```dotenv
KUBETEE_VALIDATION_PROFILE=production
BT_NETWORK=finney
KUBETEE_SUBNET_NETUID=90
KUBETEE_OWNER_HOTKEY=5EKtGWqskt8qBqdAZ78pSWRCYRuYmDc5XbwJPDqH1EpiSTEE
KUBETEE_CHAIN_NETWORK=finney
RANCHER_URL=https://rancher.kubetee.ai
RANCHER_CA_FILE=/shared/rancher-ca.crt
BT_WALLET=<operator wallet name>
BT_WALLET_HOTKEY=<operator wallet hotkey name>
KUBETEE_VALIDATOR_HOTKEY=<registered validator hotkey>
RANCHER_BEARER_TOKEN=<operator-supplied Rancher API token>
```

`https://rancher.kubetee.ai` is provisional and not DNS-resolvable. It cannot
be used to start the validator. Replace `https://rancher.kubetee.ai` with the operator's active Rancher HTTPS origin before starting the container. The owner hotkey above is a public recycle identity, not a credential. The token row is a placeholder, not a token value.

`RANCHER_CA_FILE` is the in-container CA path that corresponds to the
read-only host mount in the start command. Keep wallet names, credentials, CA
details, and image selection private. Protect the file before use:

```bash
chmod 600 /secure/path/validator.env
```

Start the named container with the reviewed published image digest:

```bash
docker run -d --name kubetee-validator --restart unless-stopped --env-file /secure/path/validator.env -v /secure/path/validator-wallet:/root/.bittensor:ro -v /secure/path/rancher-ca.crt:/shared/rancher-ca.crt:ro -p 127.0.0.1:9100:9100 ghcr.io/kubetee-ai/kubetee-subnet@sha256:6ee1381b131885cdc65256845fb264bd51d0fe14dd675b742c9d33998cf63008 python -u scripts/validator.py
```

This command overrides the local bootstrap entrypoint and never creates a subnet, registers a key, stakes, or changes Finney state. It only starts the validator process using an existing registration and the operator's inputs.

Developer-only local environments are not production evidence and do not
substitute for this Finney procedure.

## Observe and stop the container

Inspect named-container logs without printing credentials:

```bash
docker logs --tail=200 kubetee-validator
```

Check locally bound metrics from the validator host:

```bash
curl --fail --silent http://127.0.0.1:9100/metrics
```

If startup fails or trust data is missing, stale, ambiguous, or unverifiable,
investigate and retain the prior safe state. Do not force weights, change chain
state, or widen Rancher access.

Stop the named container when the operator has decided to take it out of
service:

```bash
docker stop kubetee-validator
```

## Upgrade and rollback

For an upgrade, review and record a replacement immutable digest before
stopping the container. Recreate the named container with the approved digest
and the same read-only mounts, loopback metrics binding, and environment file:

```bash
docker stop kubetee-validator
docker rm kubetee-validator
docker run -d --name kubetee-validator --restart unless-stopped --env-file /secure/path/validator.env -v /secure/path/validator-wallet:/root/.bittensor:ro -v /secure/path/rancher-ca.crt:/shared/rancher-ca.crt:ro -p 127.0.0.1:9100:9100 ghcr.io/kubetee-ai/kubetee-subnet@sha256:6ee1381b131885cdc65256845fb264bd51d0fe14dd675b742c9d33998cf63008 python -u scripts/validator.py
```

Substitute only the reviewed replacement digest in that command; do not use a
moving tag. To roll back, record and use the exact prior reviewed digest, then
perform the same named-container recreate sequence:

```bash
# Prior reviewed digest: ghcr.io/kubetee-ai/kubetee-subnet@sha256:<prior-reviewed-digest>
docker stop kubetee-validator
docker rm kubetee-validator
docker run -d --name kubetee-validator --restart unless-stopped --env-file /secure/path/validator.env -v /secure/path/validator-wallet:/root/.bittensor:ro -v /secure/path/rancher-ca.crt:/shared/rancher-ca.crt:ro -p 127.0.0.1:9100:9100 ghcr.io/kubetee-ai/kubetee-subnet@sha256:<prior-reviewed-digest> python -u scripts/validator.py
```

This manual intentionally gives no generic destructive chain or Rancher
recovery commands.

## Official Bittensor references

- [Validating in Bittensor](https://docs.learnbittensor.org/validators)
- [Managing your stakes](https://docs.learnbittensor.org/staking-and-delegation/managing-stake-btcli/)
- [Working with proxies](https://docs.learnbittensor.org/keys/proxies/working-with-proxies)
- [BTCLI reference](https://docs.learnbittensor.org/btcli)
