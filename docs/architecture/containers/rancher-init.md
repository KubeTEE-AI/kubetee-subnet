# rancher-init
One-shot provisioner: logs in to Rancher, mints the validator API token, imports and labels the miner-cluster, publishes token + CA to a shared volume.
**Technology:** scripts/rancher_provision.sh (alpine)
## Purpose
(fill)
## Components
(fill)

## Data Flow
-> rancher: Mints token; imports miner-cluster
-> minerCluster: Labels with miner hotkey

## Invariants
(fill)
