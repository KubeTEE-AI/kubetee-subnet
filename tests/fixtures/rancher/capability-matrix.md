# g004 V1 — Staging Rancher token capability matrix

Captured read-only against `staging-rancher.kubetee.ai` on 2026-07-16 with
the Early Access `.env` account API key (no scope). Response **classes**
only — no captured payload content is reproduced here.

**This matrix is non-authoritative for mutation authorization** (plan-MoA
finding, Terra 2 / Composer F4): link presence is an inference. Only the
AC12 operator-gated demo against a disposable cluster proves DELETE.

| Capability | Verdict | Confidence | Evidence class |
|---|---|---|---|
| `list_scope` | **all** — both clusters visible (miner-labeled + management), `pagination.total == 2` | proven | `GET /v3/clusters` → 200, full collection |
| `read_nodes` | **yes** — node collection for the miner cluster returns states | proven | `GET /v3/nodes?clusterId=…` → 200 |
| `delete_scope` | **cross-cluster (inferred)** — `links.remove` present on both cluster objects | inferred | link presence on GET responses; never probed destructively |
| `read_identity` | yes — `/v3/users?me=true` → 200 | proven | identity endpoint |
| conditional DELETE preconditions | **unsupported** — norman v3 exposes `uuid` but no `resourceVersion`; pre-delete recheck must be a GET identity/uuid/label comparison | proven | object field inventory |
| pagination | marker-based; `pagination.next` URL until absent; `partial: true` flags incomplete pages; server max limit 10000 | proven | `limit=1` probe |

## Operational findings

- **Cloudflare WAF** fronts the endpoint and rejects the default
  python-urllib User-Agent with `error code: 1010` before Rancher is
  reached. A custom UA (`kubetee-validator/0.1`) and curl both pass
  (HTTP 200). The production client MUST send an explicit User-Agent
  (pinned in `contract.json`).
- **Cluster-scoped API keys are unusable for this design**: they are
  rejected (401) on the entire `/v3` management API by Rancher design and
  are only valid on `/k8s/clusters/<id>/…`. The Early Access key must be a
  **No Scope** account key; least-privilege comes from the account's role
  bindings, not token scoping. (Verified empirically during V1 bring-up.)
- The account behind the current key is an operator/admin account — the
  D6 debt as recorded in the spec. A `cluster-readonly` RoleTemplate
  exists on this Rancher (observed in role-template bindings) and is the
  designated future least-privilege binding for a dedicated validator
  user.
- Secret-bearing fields observed on live objects and therefore dropped by
  the fixture allowlist: cluster `caCert`, `clusterSecrets`,
  `importedConfig`, `appliedSpec`, `annotations`; node `ipAddress`,
  `hostname`, `customConfig`, `info`, `annotations`.
- Live label observation (recorded for V9 UAT prep, no values here): the
  miner cluster's `kubetee.ai/miner-hotkey` label currently holds the
  **Alice** dev address while `miner-coldkey` holds **Bob's** — per the
  approved spec, bob is the miner, so the operator must relabel
  `miner-hotkey` to bob's hotkey before the AC9(a) healthy demo.
