# East-west attested mTLS plan

> **Roadmap** (phased work, gaps, adopt/adapt/ignore). The live contract is
> [EAST-WEST-ATTESTED-MTLS.md](./EAST-WEST-ATTESTED-MTLS.md). Do not collapse
> the two files.

> **For agentic workers:** implement task-by-task from this plan. Steps use
> checkbox (`- [ ]`) syntax. Do not invent cluster work that is not listed.
> Never `kubectl delete --force` on Kata pods.

**Goal (next):** steal the useful CoCo NIM confidential-GPU attestation
practices into KubeTEE’s already-shipped Trustee-issued east-west mTLS — sealed
NGC/HF, HTTPS KBS, durable Trustee storage, gpu0+initdata policy, five-actor
ops — without copying SNP YAML or making guest-pull the TDX default.

**Already built:** Trustee-issued mTLS on LiteLLM → GLM-5.2 and LiteLLM →
DeepSeek-V4-Flash-0731 on `na-us-oakland-56`. Spec:
[EAST-WEST-ATTESTED-MTLS.md](./EAST-WEST-ATTESTED-MTLS.md).

**Cluster:** `--context na-us-oakland-56-direct`

**Example we steal from (do not copy YAML):**
[NVIDIA confidential NIM deployment](https://confidentialcontainers.org/docs/examples/nvidia-nim-confidential-gpu-attestation/)
(2026-08-15 snapshot).

---

## What this file is vs the live spec

| File | Role |
|------|------|
| [EAST-WEST-ATTESTED-MTLS.md](./EAST-WEST-ATTESTED-MTLS.md) | **Live spec** — current contract on staging (what is deployed, threat model, SANs, rollout that already happened). |
| This PLAN | **Roadmap** — remaining gaps, phased next work, and what to adopt / adapt / ignore from the CoCo example. |

If a sentence describes current cluster behavior, it belongs in the spec. If it
is work we have not done, it belongs here.

---

## Trustee is live (stale-docs correction)

Root `CLAUDE.md` and `nim/CLAUDE.md` still say Trustee / KBS is **“NOT
deployed”** and that CC pods boot without attestation. **That is false.**

Trustee **is live** on `na-us-oakland-56`:

- Fleet: Trustee operator **v0.21.0**, AllInOne KBS, namespace
  `trustee-operator-system` (`fleet-gitops/infrastructure/CLAUDE.md` →
  `trustee/`). Two GitRepos: `trustee-crds-staging` then `trustee-staging`.
- Attestation: `coco_as_builtin`, Intel-signed TDX DCAP + on-cluster PCCS.
  Attestation policy requires `td_attributes.debug == false`.
- NVIDIA GPU verifier: **NRAS Remote** (chart default Local cannot attest
  B200). Keep the Oakland override. Needs egress to
  `nras.attestation.nvidia.com` and an NRAS license.
- East-west certs are already released through this KBS (`kbs:///default/eastwest-*`).
- Pin Trustee to the CoCo / Kata pair we run. **No `latest`.**

Remaining Trustee gaps (this plan — not “deploy Trustee”):

| Gap | Live today | Steal next |
|-----|------------|------------|
| Transport | `http://kbs-service.trustee-operator-system.svc.cluster.local:8080` — no `kbs_cert` in initdata | HTTPS KBS + cert in measured `aa.toml` / `cdh.toml` |
| Storage | Memory / `emptyDir` LocalFs — rolls wipe east-west certs (admin re-seed) | PVC or Postgres/Valkey (chart already supports this) |
| Resource policy | **LIVE (2026-09-18):** `nim/eastwest/resource-policy.rego` — cpu0 affirming + path×role (incl. `proxy-*` for alpha-recycler); attestation policy seeded as `default_cpu`. Wrong-role guests get attest 200 + resource 401 | gpu0 + initdata digest once RVPS has VBIOS/driver refs |
| Runtime keys | NGC/HF still host Kubernetes Secrets | Vault sealed secrets → `kbs:///default/…` so etcd never holds runtime keys |
| Ops model | One operator persona in practice | Five-actor split (below) |

Do not “fix” those CLAUDE files in this commit. Call the lie here so agents
stop rediscovering Trustee.

---

## Phase 0 — already built (do not redo)

Trustee-issued east-west identity shipped 2026-08-15. Details live in the
[spec](./EAST-WEST-ATTESTED-MTLS.md). This is what we **already built**; the
steal items below are what we do **next**.

- [x] Trustee operator v0.21.0 + `coco_as_builtin` on Oakland
- [x] NRAS Remote override (B200)
- [x] Local CA + leaf certs seeded with `kbs-client` (`nim/eastwest/gen-certs.sh`)
- [x] Initdata roles `litellm` vs `nim-terminator` (`nim/eastwest/initdata-*.toml`)
- [x] `fetch-certs.sh` → `/certs` via CDH
- [x] GLM + DSV4 inbound HAProxy `:8443` (`verify required` except kubelet
      `GET /health` and `/health_generate`)
- [x] Services expose `:8443` only; SGLang binds `127.0.0.1:8000`
- [x] LiteLLM outbound mTLS via `sitecustomize.py` (httpx 0.28 ignores
      `ssl_certificate`); `api_base` is `https://<svc>:8443/v1`
- [x] Gateway chat **200** for `z-ai/glm-5.2` and
      `deepseek/deepseek-v4-flash-0731`
- [x] Draft `nim/eastwest/resource-policy.rego` (cpu0 + path×role) — **not
      applied**; live is still `default.rego`

Inbound terminator: the **HAProxy sidecar is rolled on all 10 CC pods** (2026-09-17,
kata#11649 fixed via the MINIMAL `v4.2.0-fix11649` shim overlay on both clusters —
decision 2026-09-16: permanent terminator, image `haproxy:3.4.4-alpine`)

---

## File map

| Path | Role |
|------|------|
| `nim/eastwest/gen-certs.sh` | Local CA + leaf certs. Output stays on the operator machine; never commit. |
| `nim/eastwest/haproxy-inbound.cfg` | GLM/DSV4 guest: `:8443` mTLS → `127.0.0.1:8000` |
| `nim/eastwest/haproxy-outbound.cfg` | LiteLLM loopback (sidecar path; live outbound is sitecustomize) |
| `nim/eastwest/fetch-certs.sh` | CDH fetch → `/certs/*.pem` |
| `nim/eastwest/initdata-litellm.toml` | `role = "litellm"` + HTTP KBS URL (no `kbs_cert` yet) |
| `nim/eastwest/initdata-nim.toml` / `initdata-glm.toml` / `initdata-dsv4.toml` | `role = "nim-terminator"` + HTTP KBS URL |
| `nim/eastwest/resource-policy.rego` | **LIVE** KBS policy (seeded 2026-09-18 via admin API): cpu0 affirming + path×role incl. `proxy-*` for the alpha-recycler. |
| `nim/glm-5-2-nvfp4-sglang-cc.yaml` | GLM STS + Service `:8443` |
| `nim/deepseek-v4-flash-0731-sglang-h200-cc.yaml` | DSV4 STS + Service `:8443` |
| `fleet-gitops/infrastructure/litellm/staging/values-litellm-na-us-oakland-56.yaml` | LiteLLM TDX overlay (LE public hop + east-west client cert) |
| `fleet-gitops/infrastructure/trustee/` | Operator v0.21.0 + KbsConfig (Fleet). Manual `kbs-auth-public-key`. |
| Live Trustee ConfigMaps / KBS resources | Policy + `set-resource`. No K8s Secrets for east-west private keys. |

---

## Hard constraints

- Never `kubectl delete --force --grace-period=0` on `kata-*` pods.
- GLM/DSV4 rolling update recreates TDX GPU sandboxes (tens of minutes to
  hours). Apply one StatefulSet, wait Ready, then the next.
- Do not enable `agent.image_registry_auth` on these pods while images stay
  public host-pull (`IfNotPresent` + erofs). Guest-pull is **not** the TDX
  default (Phase 4 / ignore box).
- Private keys: generate on the operator machine, `kbs-client set-resource`
  into Trustee. Do not `kubectl create secret` for `tls.key`. Do not git-add
  `*.pem` / `*.key`.
- Do not kubectl-patch Fleet-managed Deployments (Fleet SSA).
- Keep **NRAS Remote** on Oakland. Do not revert the NVIDIA verifier to Local.
- Do not enable CoCo `kata-as-coco-runtime` (duplicates kata-deploy 4.2.0 RuntimeClasses).
- Do not treat the CoCo tutorial as encrypted-weights. Its `/opt/nim/.cache`
  is a plaintext `emptyDir`.
- Hopper `cc.mode=off` is a PPCIE trap — not a baseline we run.

---

## Steal from CoCo NIM attestation example (2026-08-15)

Source:
[confidentialcontainers.org — NVIDIA confidential NIM deployment](https://confidentialcontainers.org/docs/examples/nvidia-nim-confidential-gpu-attestation/).

The tutorial is a single-node AMD SEV-SNP + 1 GPU + Llama 3.1 8B NIM Pod +
Docker Compose Trustee walkthrough. We steal **practices**, not YAML.

### Adopt (next work — not already done)

| # | Practice | Why it matters here | Phase |
|---|----------|---------------------|-------|
| 1 | **Sealed secrets** for NGC/HF (later LUKS keys) — vault sealed secret pointing at `kbs:///default/ngc-api-key/instruct` (and HF equivalent). Kubernetes sees only the sealed blob; CDH unseals inside the guest. | etcd never holds runtime keys. Today NGC/HF are host Secrets. | 4 |
| 2 | **KBS HTTPS + cert in measured initdata** (`aa.toml` / `cdh.toml` `kbs_cert` / `cert`). | Live GLM/LiteLLM still `http://kbs-service…:8080` with no cert — host-sniff risk on miner-WAN. Spec already blocks remote guests until this exists. | 2 |
| 3 | **Durable Trustee storage** — not Memory `emptyDir`. PVC, or Postgres / Valkey. Helm chart already supports `storageBackend.localFs.persistence.*`, `Postgres`, and Valkey sessions. | Restarts wipe east-west certs; admin must re-seed. | 1 |
| 4 | **gpu0 + initdata in resource policy** once RVPS has VBIOS/driver refs. Tutorial requires `cpu0` and `gpu0` affirming plus pinned initdata digest. | Today gpu0-affirming **denies** after attest 200. Draft rego is cpu0 + path×role only. Live is still upstream `default.rego`. | 3 |
| 5 | **Five-actor split** (Outlook). Tutorial’s single persona is not our model. | Cluster team ≠ Trustee operator ≠ KBS admin ≠ release pipeline ≠ workload operator. | 5 |
| 6 | Keep **NRAS Remote**. | Local cannot attest B200. Chart default Local must stay overridden on Oakland. | (done — do not regress) |

### Adapt (do not copy YAML)

| Tutorial | KubeTEE |
|----------|---------|
| SNP `HOST_DATA` / `sev-snp-measure` / live QEMU scrape | TDX MRTD/RTMR + initdata claims. We already bind `role` in initdata (`litellm` vs `nim-terminator`). Pin digest in policy when RVPS is filled — do not scrape QEMU on the GPU node. |
| 1 GPU SNP (`nvidia.com/pgpu: "1"`, `kata-qemu-nvidia-gpu-snp`) | 8 GPU TDX + PPCIE + NVSwitch. Hopper: `nvidia.com/nvswitch: "4"`, `cc.mode=ppcie`. Blackwell: `cc.mode=on`. Runtime: `kata-qemu-nvidia-gpu-tdx-runtime-rs` only. |
| Guest-pull block PV (`/dev/trusted_store`, loop `/tmp`) | **kata-direct** for weights. Later CDH LUKS ([pamanseau/kubetee-ai#1](https://github.com/pamanseau/kubetee-ai/issues/1)). Agent `cdh_secure_mount` still hardcodes `sourceType: "empty"` and omits `key` — LUKS is **not** done. |
| Raw NIM Pod + `genpolicy` on the worker | NIMService / SGLang StatefulSet + `fetch-certs` + HAProxy `:8443`. LiteLLM is Helm 1.96.2 (Fleet), not a Pod manifest. |
| Docker Compose Trustee on the GPU node | Fleet operator v0.21.0 (already). Pin to the CoCo/Kata pair; no `latest`. Do not run Trustee on the workload node. |
| Bitnami Postgres subchart (if we pick SQL) | CloudNativePG is the KubeTEE Postgres standard. Do not add Bitnami. |
| Single NGC key for pull + runtime | Split: host `imagePullSecret` (CRI, host-pull/erofs) vs sealed runtime key in KBS (guest). |

### Do not copy from the tutorial

| Ignore | Why |
|--------|-----|
| `kata-qemu-nvidia-gpu-snp`, live QEMU scrape, `snphost`, `sev-snp-measure` | We are TDX + runtime-rs, not SNP. |
| Docker Compose Trustee on the GPU node | Trust separation is the point. Oakland already has Fleet operator. |
| Loop `/tmp` PVs / `local-storage` | We have `kata-direct` + Longhorn V2. |
| `cc.mode=off` baseline on Hopper | PPCIE trap — label-only CC→non-CC does not clear the PPCIE register. |
| Enabling CoCo `kata-as-coco-runtime` | Duplicates kata-deploy 4.2.0 RuntimeClasses. Keep `enabled: false`. |
| Guest-pull as the default TDX image path | Needs HTTPS KBS + guest registry egress. **erofs + host-pull + `IfNotPresent`** is the no-KBS-egress path. Keep nydus installed, do not select it for TDX shims until Phase 2 + egress exist. |
| Treating the tutorial as encrypted-weights | `/opt/nim/.cache` is a plaintext `emptyDir`. Encrypted weights are issue #1 + agent key plumbing — not this example. |
| Replacing SGLang with Llama 3.1 8B NIM | First-cut models stay GLM + DSV4 SGLang. NIM containers are a later reuse of Trustee + LiteLLM, not a swap. |

---

## Phase 1: Durable Trustee storage

**Status:** **DONE (2026-09-18)** — Trustee migrated to the **v0.22.0 vendored
Helm chart** (microservices: `kbs-service` + AS `coco-as-grpc` + RVPS) with
**LocalFs on `longhorn-v2` PVCs** (`trustee-kbs-data`, `trustee-as-data`,
`trustee-rvps-data`). The operator + `KbsConfig` path is retired (operator
v0.21.0 hardcoded `emptyDir medium: Memory`). Resources + both policies
re-seeded once and verified persistent across a KBS `rollout restart`
(east-west certs, alpha-recycler proxy seeds, attestation policy,
`resource-policy` all survived — note: the migration seeded the relaxed
attestation policy under id `default`, which the broker never resolves; it
was re-seeded as `default_cpu` on 2026-09-18 with Phase 3a). A fresh alpha-recycler guest attested
end-to-end on the new stack (MRCONFIGID + EventLog checks passed,
`AttestationEvaluate succeeded`, seeds fetched, recycle done). Chart patches
+ migration runbook: `fleet-gitops/infrastructure/trustee/staging/chart/KUBETEE-PATCHES.md`
and `staging/migration/MIGRATION-OPERATOR-TO-CHART.md`.

**Namespace note (deferred):** pods remain in `trustee-operator-system`; move
to `trustee-system` later — the KBS URL is measured into every guest's
`cc_init_data`, so the rename requires re-encoding initdata + rolling all
13 guests (wedge-prone GPU recreates) or an ExternalName bridge. Bundle it
with the next initdata-changing rollout.

**Why it mattered:** every later phase (HTTPS, policy, sealed NGC) writes KBS
state. Wiping that on a rollout is an outage.

**Files:** `fleet-gitops/infrastructure/trustee/` (KbsConfig + volumes). Chart
knobs for reference (operator must express the same outcome):

- `storageBackend.localFs.persistence.kbs` / `.as` / `.rvps` — PVC claim;
  empty = `emptyDir`
- `storageBackend.type: Postgres` or `sessionStorageType: Redis` (Valkey)
- Oakland: `longhorn-v2` / `longhorn-v2-ha`. If SQL, **CloudNativePG**, not
  Bitnami.

- [ ] **Step 1: Confirm live volume**

```bash
kubectl --context na-us-oakland-56-direct -n trustee-operator-system \
  get kbsconfig,deploy,pvc
kubectl --context na-us-oakland-56-direct -n trustee-operator-system \
  get deploy -o jsonpath='{range .items[*]}{.metadata.name}{"\n"}{range .spec.template.spec.volumes[*]}  {.name} {.emptyDir}{"\n"}{end}{end}'
```

Expected: resource/AS/RVPS dirs are `emptyDir` (or Memory). Record the
ConfigMap paths (`dir_path`, `policy_path`).

- [ ] **Step 2: Choose one durable backend** (do not implement all three)

  1. **PVC LocalFs** (smallest change) — `longhorn-v2` PVC mounted at
     `/opt/confidential-containers/storage`.
  2. **CloudNativePG** — if we want HA KV; new `Cluster` in
     `trustee-operator-system`, `longhorn-v2-ha`.
  3. **Valkey / Redis-protocol** — sessions + optional KV; do not stand up a
     second Redis if we can reuse a dedicated Trustee instance (do **not**
     share `redis-litellm`).

- [ ] **Step 3: Express it in Fleet** (git, not `kubectl patch`). Roll Trustee
      **gracefully**. Re-seed east-west resources once.

- [ ] **Step 4: Prove survival**

```bash
kubectl --context na-us-oakland-56-direct -n trustee-operator-system \
  rollout restart deploy/trustee-deployment
# after Ready: get-resource without attestation still fails; attested
# fetch-certs on a new LiteLLM/GLM boot still gets the same PEMs without
# a second set-resource.
```

Do not start Phase 2 until a Trustee roll does **not** require re-seed.

---

## Phase 2: KBS HTTPS + cert in measured initdata

**Status:** not done. Live `aa.toml` / `cdh.toml` (see
`nim/eastwest/initdata-litellm.toml`, `initdata-glm.toml`,
`initdata-dsv4.toml`):

```toml
url = "http://kbs-service.trustee-operator-system.svc.cluster.local:8080"
```

No `cert` / `kbs_cert`. `insecure_http = true` on the operator sample
`kbs-config.toml`.

**Why now:** on Oakland this is a host-sniff risk. Across a miner WAN it is
fatal (spec § Later: miner-cluster backends). Close this **before** the first
remote guest.

Tutorial practice to steal: generate KBS HTTPS material, set
`insecure_http = false`, embed the **same** cert in both `aa.toml` and
`cdh.toml` so AA and CDH pin the endpoint. SAN must match the URL guests use
(`kbs-service.trustee-operator-system.svc.cluster.local`).

- [ ] **Step 1: Issue a KBS server cert** (operator machine or org CA). SAN =
      Service FQDN (+ `127.0.0.1` for port-forward admin). Do not commit the
      key. Load via a manual Secret / operator TLS field — not a git Secret.

- [ ] **Step 2: Flip KBS to HTTPS** in the Fleet KbsConfig
      (`insecure_http = false`, `certificate` + `private_key` paths). Keep
      `AuthenticatedAuthorization`. Roll Trustee.

- [ ] **Step 3: Put the cert in initdata** — both `aa.toml`
      (`token_configs.kbs.cert`) and `cdh.toml` (`kbc.kbs_cert`). URL becomes
      `https://kbs-service.trustee-operator-system.svc.cluster.local:8080`
      (or whatever port the Service keeps). Re-base64
      `io.katacontainers.config.hypervisor.cc_init_data`.

- [ ] **Step 4: Point kernel AA at HTTPS**
      (`agent.aa_kbc_params=cc_kbc::https://kbs-service…`). Apply LiteLLM
      overlay first (CPU TDX, faster), then GLM, then DSV4. Wait Ready each
      time.

- [ ] **Step 5: Prove** `fetch-certs` still works; `kbs-client --cert-file`
      admin path works; plaintext HTTP to `:8080` no longer serves resources.

Blocked: miner-cluster backends (Phase 7). Guest-pull (ignored as default).

---

## Phase 3: Resource policy (path×role + cpu0, then gpu0)

**Status:** **3a DONE (2026-09-18)** — path×role + cpu0-affirming resource
policy is **live** on the v0.22.0 chart KBS, seeded via the admin API.
**3b (gpu0 + initdata digest) remains blocked** on RVPS reference values.

Root cause of the old "cpu0-affirming 401s after attest 200" (2026-08-15):
the EAR broker looks up `{policy_id}_{tee_class}` (guests send no selector →
KBS default `default` → storage key `default_cpu.rego`). The relaxed
first-cut attestation policy had been seeded under the id `default`, which
the broker never consults — the **built-in** `default_cpu` (with active
`query_reference_value` checks against an empty RVPS) kept winning, so cpu0
appraised Contraindicated (hardware 97 / executables 33 / configuration 36).
Fixed 2026-09-18 by seeding the relaxed policy as `default_cpu` (admin API
`POST /kbs/v0/attestation-policy`, `overwrite: true`; the built-in seeds
with `overwrite: false` at AS startup, so our seed survives AS restarts —
verified by a probe attestation after an AS roll).

Live resource policy (`nim/eastwest/resource-policy.rego`): cpu0 affirming +
path×role over `eastwest-ca` (litellm|nim-terminator), `eastwest-litellm`
(litellm), `eastwest-nim` (nim-terminator), `proxy-staking` +
`proxy-nonfungible` (alpha-recycler — added 2026-09-18; the draft would have
broken the CronJob's seed fetch).

Verification (2026-09-18, KBS access log evidence):

| Probe | Role | attest | eastwest-ca | own paths | foreign paths |
|-------|------|--------|-------------|-----------|---------------|
| fresh alpha-recycler Job | `alpha-recycler` | 200 | 200 | seeds 200 | `eastwest-litellm/tls.crt` **401** |
| recreated LiteLLM pod | `litellm` | 200 | 200 | `eastwest-litellm` pair 200 | — |
| CPU probe w/ nim initdata | `nim-terminator` | 200 | 200 | `eastwest-nim` pair 200 | — |

`agent_policy_claims` is **absent** from the live EAR (init-data is only
digest-measured; the containers field is not parsed into claims) — that is
todo "measured agent-policy container allowlist" (Phase 4-class, not 3b).

- Live attestation policy: first-cut relaxed (Intel-signed quote + debug off
  + TCB UpToDate; RVMS pins commented out, restore when RVPS is filled).
- 3b sketch (gpu0 + initdata digest) unchanged — blocked on RVPS.

Tutorial policy (SNP) required `cpu0` + `gpu0` affirming **and**
`annotated_evidence["init_data"] == expected_digest`. We adapt that to TDX
claims, not `HOST_DATA`.

### 3a — path×role + cpu0 (apply the draft)

- [x] **Step 1: Dump one token** (done 2026-09-18). AS `RUST_LOG=debug` for
      one roll (`debug!(ear =? ear, "Unsigned EAR Token")` in
      `ear_token/broker.rs`), one-off alpha-recycler probe Job with the real
      CronJob's `cc_init_data`. Confirmed:
      `submods.cpu0["ear.veraison.annotated-evidence"].init_data_claims.role`
      = `"alpha-recycler"` — matches the draft path exactly. Single cpu0
      submod on CPU-TDX guests (no GPU submods). Also confirmed the seeded
      `default` policy was inert (broker resolves `default_cpu`) — see
      Phase 3 status note. Log level reverted after capture.

- [x] **Step 2: Apply** (done 2026-09-18, admin API — the chart stores
      policies in the PVC-backed KV store, no ConfigMap mount):
      1. attestation policy seeded as **`default_cpu`** (the storage key the
         broker actually resolves) — relaxed first-cut TDX checks;
      2. resource policy = `nim/eastwest/resource-policy.rego` + the
         `proxy-staking`/`proxy-nonfungible` paths for the alpha-recycler
         role (missing from the draft — would have broken the CronJob).
      Both survive AS restarts (built-ins seed with `overwrite: false`).

- [x] **Step 3: Prove** (done 2026-09-18; see the verification table above):
      recreated LiteLLM pod fetched all three eastwest resources 200; a
      fresh alpha-recycler guest fetched its seeds 200 and was **401-denied**
      `eastwest-litellm/tls.crt` (wrong role); a `nim-terminator`-role CPU
      probe fetched the `eastwest-nim` pair 200. Post-AS-roll probe still
      passes (policies persisted).

### 3b — gpu0 + initdata digest (after RVPS)

**Blocked on** RVPS reference values for NVIDIA VBIOS / driver (and TDX
MRTD/RTMR when we pin them). Empty RVPS → gpu0 stays non-affirming →
gpu0-affirming denies a healthy 8-GPU guest.

- [ ] **Step 1: Fill RVPS** with production measurements after debug-off
      recreate. Never allowlist `*-debug` measurements
      (`fleet-gitops/infrastructure/CLAUDE.md` trustee section).

- [ ] **Step 2: Extend** `resource-policy.rego`:

```rego
# sketch only — verify claim names against a live EAR before applying
allow if {
	data.plugin == "resource"
	cpu0_affirming
	gpu0_affirming
	path_ok
	initdata_ok
}

gpu0_affirming if {
	input.submods.gpu0["ear.status"] == "affirming"
}
```

  Bind initdata digest (TDX equivalent of the tutorial’s
  `annotated_evidence["init_data"]`) once we know the live field. Keep
  path×role — gpu0 does not replace the role split.

- [ ] **Step 3: Prove** Hopper (PPCIE + NVSwitch) and Blackwell (`cc.mode=on`)
      both affirm gpu0. A guest missing `nvidia.com/nvswitch: "4"` on Hopper
      must not get keys.

---

## Phase 4: Sealed NGC/HF (later LUKS keys)

**Status:** not done. Do **not** claim guest-pull or LUKS is done.

Tutorial: P-256 signing JWK; vault sealed secret
`kbs:///default/ngc-api-key/instruct`; public JWK at
`kbs:///default/signing-key/sealed-secret`; Kubernetes Secret holds only
`sealed.…`. CDH verifies the JWS then fetches plaintext from KBS.

KubeTEE mapping:

| Secret | Today | Target |
|--------|-------|--------|
| East-west TLS keys | Already KBS `set-resource` (not etcd) | Keep. Optional: wrap as sealed if a workload env var must reference them. |
| NGC runtime API key | Host Secret `ngc-api` | `kbs:///default/ngc-api-key/<workload>` + sealed Secret in the pod |
| HF token | Host Secret `hf-token` | `kbs:///default/hf-token/<workload>` + sealed Secret |
| LUKS volume key | Not deployed | `kbs:///default/luks/<vol>` after agent `cdh_secure_mount` grows a `key` + `sourceType` ([pamanseau/kubetee-ai#1](https://github.com/pamanseau/kubetee-ai/issues/1)) |

Host `imagePullSecret` for **host-pull** (erofs) may stay a dockerconfig —
that is CRI on the host, not a guest runtime key. Do not conflate the two.

- [ ] **Step 1: Generate** sealed-secret signing JWK on the operator /
      release machine. Upload **public** JWK only. Private JWK never enters
      the cluster or git.

- [ ] **Step 2: `set-resource`** plaintext NGC/HF into KBS (after Phase 1 so
      it survives a roll). Paths under `default/`.

- [ ] **Step 3: Emit vault sealed blobs** in the trusted release path (CoCo
      `secret` CLI when we have it; do not treat the tutorial’s Python helper
      as production tooling). Commit only the sealed value if it must live
      next to a manifest — never the plaintext.

- [ ] **Step 4: Point one non-serving consumer first** (a throwaway TDX pod
      or LiteLLM extra env), not GLM. Prove CDH unseals and the host Secret
      dump is `sealed.`… not `nvapi-`.

- [ ] **Step 5: LUKS** stays blocked on the Kata agent patch
      (`sourceType: "empty"` hardcoded, no `key`). Track issue #1. Do not
      advertise encrypted weights until that lands.

Guest-pull (`agent.image_registry_auth=kbs:///default/credentials/nvcr`) is
**optional later**, and only after Phase 2 + guest egress. erofs remains the
default TDX image path.

---

## Phase 5: Five-actor split

**Status:** not done as an ops model. Tutorial Outlook (production actors):

| Actor | Tutorial | KubeTEE owner |
|-------|----------|----------------|
| Cluster platform team | Kata, GPU Operator, RuntimeClass | Fleet `kata-deploy` + `gpu-operator` + RKE2 cluster manifests |
| Trustee operator | Run Trustee in a trusted environment | Fleet `trustee/` on Oakland (not on miner GPU nodes) |
| KBS administrator | Resources, policy, reference values | `kbs-client` + admin JWT; RVPS fill; Phase 1–3 |
| Release pipeline | Sealed secrets, initdata, agent policy | `nim/eastwest/initdata-*.toml`, sealed NGC/HF, image pins, `cc_init_data` |
| Workload operator | Submit the approved manifest | SGLang STS / NIMService / LiteLLM overlay — no host-side QEMU scrape |

- [ ] **Step 1: Write the owner column** into
      `fleet-gitops/infrastructure/trustee/KubeTEE.md` (or a short
      `nim/eastwest/README.md`) so the next human does not run `genpolicy` /
      `set-resource` on the GPU node.

- [ ] **Step 2: Stop generating initdata interactively on GPU nodes.**
      `encode-initdata.py` + committed TOML stay in the release path.

- [ ] **Step 3: Miners never run Trustee.** Remote guests attest to the
      KubeTEE KBS (spec). A miner-local Trustee would make the miner the CA.

An organization can combine roles; each responsibility still needs a named
owner.

---

## Phase 6: Restore HAProxy sidecar — COMPLETE (2026-09-17)

**Status (2026-09-17): COMPLETE.** #11649 was reproduced deterministically on
stock kata 4.2.0 (ornith-1 `am-h200-29`, glm-5-3-flash `am-h200-23`) and the
MINIMAL `v4.2.0-fix11649` overlay (idempotent `blockdev-add` only) is live on
**both** clusters (oakland staging, michigan production; fleet commits
`7c2defe`/`9f765e2`). The sidecar roll then completed: **all 10 CC pods** on
`na-us-oakland-56` run `fetch-certs` init + `haproxy` sidecar + SGLang,
0 restarts, no `Duplicate nodes` events. Inbound TLS terminates in the
sidecar; the in-process terminator is retired. Upstream
[#13635](https://github.com/kata-containers/kata-containers/pull/13635) was
**closed unmerged** (2026-09-13); [the issue](https://github.com/kata-containers/kata-containers/issues/11649)
is OPEN with our live-repro comment — keep the overlay until an official tag
carries the fix.

**Decision (2026-09-16): the sidecar is the permanent terminator, not a stopgap.**
In-process TLS inside SGLang was evaluated and **rejected** — see the spec's
[decision record](./EAST-WEST-ATTESTED-MTLS.md#inbound) for the evidence
(Granian `ssl_verify=False` hardcoded at both call sites; uvicorn
`CERT_NONE`; rustls `allow_unauthenticated()` unreachable without patching
the image, which KubeTEE policy forbids). The sidecar is stack-agnostic: the
same config serves SGLang any version, vLLM (`glm-45-air`), and any future
inference stack, with zero per-version image maintenance.

Image standard for the sidecar (all 12 `nim/*-cc.yaml` manifests, 2026-09-16):
`docker.io/library/haproxy:3.4.4-alpine`, digest-pinned, running as
`USER haproxy` (uid 99) with caps dropped and read-only rootfs. HTTP/2 enabled
on the bind (`alpn h2,http/1.1`). DHI hardened-FIPS variant rejected — it
requires authenticated `dhi.io` pulls and our CC guest-pull is anonymous.
See spec [image standard](./EAST-WEST-ATTESTED-MTLS.md).

The sidecar is a second container in the same sandbox. See spec
[Follow-up: restore HAProxy sidecar](./EAST-WEST-ATTESTED-MTLS.md#follow-up-restore-haproxy-sidecar-kata11649).

- [x] `v4.2.0-fix11649` overlay on **every CC node of both clusters** (2026-09-17;
      oakland 10/10 + michigan 7/7, shim sha `15d32291507e…` verified per node) —
      init + sidecar rolls no longer hit `Duplicate nodes with node-name='drive-N'`.
- [x] Sidecar + `fetch-certs` init restored; in-process fetch/HAProxy dropped
      from `start-sglang.sh`.
- [x] Partition dropped to 0 (all 10 live CC pods, no `partition` set).
- [x] Sidecar image+config roll **canary-verified** (2026-09-17, ornith
      pod-1, `am-h200-29`): 2/2, 0 restarts, `nbthread 2` over 19 guest
      CPUs, 4× gateway 200s, ALPN `h2` negotiated (3.4.3 pod-0 also
      negotiated h2 — HAProxy ≥2.8 defaults bind ALPN to `h2,http/1.1`).
- [x] Full rollout: **all 10 CC pods** on `na-us-oakland-56` run
      init + haproxy + sglang (verified 2026-09-17) — the two pods that
      wedged on stock during the roll (ornith-1 h200-1, glm-5-3-flash h200-1)
      recovered clean on the fixed shim.

This is independent of sealed NGC. Do not block Phase 1–2 on it.

---

## Phase 7: Miner-cluster backends (blocked)

**Blocked on Phase 2** (HTTPS KBS or attested KBS channel). Spec:
[Later: miner-cluster backends](./EAST-WEST-ATTESTED-MTLS.md#later-miner-cluster-backends).

Do not start until CDH no longer fetches `eastwest-nim/tls.key` over plaintext
HTTP. One Trustee (KubeTEE). Per-cluster server cert + initdata `cluster`.
L4 passthrough only.

---

## Spec coverage (next work)

| Item | Phase | Status |
|------|-------|--------|
| Trustee-issued east-west mTLS | 0 | **Shipped** — live spec |
| Durable KBS store | 1 | **Done (2026-09-18)** — v0.22.0 chart, LocalFs `longhorn-v2` PVCs, roll-survival verified |
| HTTPS KBS + `kbs_cert` in initdata | 2 | Not done (HTTP, no cert) |
| path×role + cpu0 policy | 3a | Draft only; live `default.rego` |
| gpu0 + initdata digest | 3b | Blocked on RVPS VBIOS/driver |
| Sealed NGC/HF | 4 | Not done |
| LUKS / encrypted weights | 4 / #1 | Not done — agent hardcodes `empty` |
| Five-actor ops | 5 | Not done |
| HAProxy sidecar restore | 6 | **COMPLETE (2026-09-17)** — rolled on all 10 CC pods, `3.4.4-alpine` + h2, on the `fix11649` shim overlay |
| Miner backends | 7 | Blocked on Phase 2 |
| NRAS Remote | — | **Shipped** — do not revert |
| Guest-pull as TDX default | — | **Ignored** |
| SNP YAML / Compose Trustee | — | **Ignored** |

---

## Later (not this plan)

- Same mTLS pattern on remaining Oakland models (Kimi, Qwen, MiMo).
- Public-hop RA-TLS for clients that attest `llm.kubetee.ai`.
- Short-lived certs with CDH refresh after model load.
- In-guest keygen + `report_data` binding if a future profile requires keys
  that never exist in Trustee.
- Guest-pull + nydus for TDX — only after Phase 2 + guest registry egress.
- NIM containers: reuse Trustee + LiteLLM client; add Operator sidecar or
  `NIM_SSL_MODE=mtls` only if that NIM requires client certs. Not a swap of
  GLM/DSV4 SGLang.
