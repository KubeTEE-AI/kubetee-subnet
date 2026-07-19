# basic_validator.py
One validator loop, one chain connection, one Rancher session: metagraph -> Rancher enumeration -> reconciliation -> scoring -> weights -> log + metrics.
**Technology:** Python process (foreground)
## Purpose
(fill)
## Components
- load_config / ValidatorConfig (Fail-fast validation of all static config (share, poll interval, skip cap, reconcile params, hotkeys, RANCHER_URL/RANCHER_BEARER_TOKEN); refuses to start on any violation without echoing secrets.)
- BasicValidator cycle loop (Per-cycle: read metagraph, enumerate Rancher, run reconciliation, score miners, set alice-signed weights, log + export metrics. Never exits on runtime error; skips set_weights on Rancher outage; degraded mode after KUBETEE_MAX_CONSECUTIVE_SKIPS.)
- miner_scoring.py (Binary fail-closed liveness score: 1 iff exactly one labelled active cluster with an active node; weight split KUBETEE_MINER_SHARE to scoring miners, rest to owner recycle UID.)
- chain_state.py (Chain query helpers: subnet ownership, wallet stake, coldkey/hotkey SS58 resolution.)
- ReconciliationEngine (Single guarded Rancher mutation: deletes labelled clusters whose hotkey left the metagraph, after persistence bounds and a same-cycle pre-delete recheck; 404/409 idempotent; unauthorized fails closed.)
- RancherClient (Structurally GET-only client apart from the guarded DELETE; one pinned https origin, no redirects, complete pagination, never logs the token.)
- ValidatorMetrics (Prometheus text metrics on KUBETEE_METRICS_PORT 9100 (compose-internal only): rancher errors, set_weights results, skips, degraded flag, reconciliation counters.)

## Data Flow
-> bittensorChain: Reads metagraph; submits set_weights

## Invariants
(fill)
