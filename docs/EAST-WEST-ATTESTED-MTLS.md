# East-west attested mTLS (LiteLLM ↔ inference guests)

**Status:** deployed on staging `na-us-oakland-56` (2026-08-15). All four replicas `2/2` (`glm-0`/`glm-1`, `dsv4-0`/`dsv4-1`). GLM + DSV4 inbound HAProxy `:8443`; Services expose `:8443` only. SGLang binds `127.0.0.1:8000` (pod IP `:8000` connection refused). Kubelet HTTPS probes use `:8443` `/health` and `/health_generate` (HAProxy `verify optional` on those GET paths only; all other paths need a verified client cert). LiteLLM presents the Trustee client cert via `sitecustomize.py` (httpx 0.28 ignores `ssl_certificate`). Public hop is still Let’s Encrypt + Traefik. Gateway chat **200** for both public models. KBS resource policy is still upstream `default.rego` — path×role + cpu0-affirming 401s after attest 200.  
**Date:** 2026-08-15  
**Approach:** CoCo Confidential AI — Trustee issues TLS credentials after attestation. Apps speak ordinary mTLS. No quote parsing in LiteLLM or SGLang.  
**Roadmap:** remaining gaps (HTTPS KBS, durable Trustee, gpu0/RVPS, sealed NGC) live in [EAST-WEST-ATTESTED-MTLS-PLAN.md](./EAST-WEST-ATTESTED-MTLS-PLAN.md).

This is the implementation spec for [§2 Attestation-gated TLS](./NEMO-MICROSERVICES-AND-SUBNET-INTEGRATIONS.md#2-attestation-gated-tls-between-services).

## Goal

Encrypt LiteLLM → inference traffic so cleartext never exists on the host or the CNI. A peer gets a certificate only after CoCo Trustee (KBS) accepts a TDX quote verified by the built-in CoCo Attestation Service (Intel-signed DCAP, PCCS collateral), with guest debug off. The host operator cannot mint a valid east-west cert from a Kubernetes Secret. Intel Trust Authority is deferred.

## Non-goals (this cut)

- Quote-in-handshake RA-TLS (TLS extensions / custom stacks)
- Keypairs generated inside the guest (older §2 text; superseded)
- Public-hop RA-TLS (`llm.kubetee.ai` stays Let’s Encrypt + Traefik passthrough)
- Kimi, Qwen, MiMo, or other models
- Switching GLM / DSV4 from SGLang to NVIDIA NIM containers
- Short-lived cert refresh during a multi-hour model boot
- Trustee-held data-encryption keys for the weight path
- Miner-cluster backends (see [Later: miner-cluster backends](#later-miner-cluster-backends))

## Threat model

The host, kubelet, and CNI are untrusted for confidentiality of LiteLLM↔NIM tokens. Trustee (KBS + AS + RVPS) is the relying party and lives in a trusted zone. Kubernetes Secrets and cert-manager are not used for east-west keys.

Guest debug on, or `runtimeClassName` that is not TDX, must not receive the keys. Trustee policy already intends `td_attributes.debug == false`.

## Architecture

```text
Client --HTTPS Let’s Encrypt--> Traefik passthrough --> LiteLLM guest :4000
                                                         |
                                                         | https://<svc>:8443 (httpx + sitecustomize)
                                                         | mTLS (Trustee certs)
                                                         v
                         Service DNS :8443 --> inbound HAProxy (same sandbox as SGLang)
                                                         |
                                                         | HTTP 127.0.0.1:8000
                                                         v
                                                       SGLang
```

Trustee holds the CA and the issued certs. After a guest attests, CDH copies the matching material into that CVM. TLS private keys are never stored in Git or in host-visible Kubernetes Secrets.

CoCo reference: [Confidential AI / federated learning](https://confidentialcontainers.org/docs/use-cases/confidential-ai) — clients receive TLS certificates from Trustee upon successful attestation instead of embedding verification in each app.

## First-cut workloads

Live LiteLLM `api_base` rows (HTTPS `:8443`). First cut covers these two public model names:

| Public model | Service (TLS hostname) | Manifest |
|--------------|------------------------|----------|
| `z-ai/glm-5.2` | `glm-5-2-nvfp4-sglang.nemo.svc.cluster.local` | `nim/glm-5-2-nvfp4-sglang-cc.yaml` (StatefulSet, 2 replicas, one Service) |
| `deepseek/deepseek-v4-flash-0731` | `dsv4-0731-sglang-h200.nemo.svc.cluster.local` | `nim/deepseek-v4-flash-0731-sglang-h200-cc.yaml` |

GLM HA uses the **existing Service**, not per-pod DNS. Both replicas attest independently and receive the same NIM server cert (SAN = Service FQDN). ClusterIP load-balances TCP; a stream stays on one pod. Kubernetes readiness is pod-wide: a replica must not be Ready until HTTPS `:8443` `/health` succeeds (HAProxy up and SGLang healthy on loopback).

NVIDIA NIM containers would not change Trustee, LiteLLM sidecar, or Service SAN. They would only change NIM-side TLS (optional `NIM_SSL_MODE=mtls` if that LLM NIM implements it) and how a sidecar is injected (`NIMService` vs StatefulSet). Out of scope for this cut.

## Trustee / KBS

AS verifies TDX quotes with **CoCo AS builtin** (`coco_as_builtin`): Intel-signed TDX DCAP quotes, collateral from on-cluster PCCS. First-cut attestation policy (no RTMR pin until RVPS is filled): Intel TDX quote header, `td_attributes.debug == false`, TCB `UpToDate`. Intended KBS release conditions (not live — see Trustee `KubeTEE.md`):

- EAR cpu0 is affirming
- `td_attributes.debug == false`
- Initdata **role** matches the resource (`litellm` vs `nim-terminator`)

Live policy is still upstream `default.rego` (resource plugin, not sample). Path×role + cpu0-affirming 401s after attest 200 (2026-08-15).

Resources (illustrative URIs; keep the `default` repository unless Trustee layout forces otherwise):

| URI | Contents | Who may fetch |
|-----|----------|----------------|
| `kbs:///default/eastwest-ca/ca.pem` | East-west CA cert (public) | `litellm` and `nim-terminator` |
| `kbs:///default/eastwest-litellm/tls.crt` | LiteLLM client cert | `litellm` only |
| `kbs:///default/eastwest-litellm/tls.key` | LiteLLM client key | `litellm` only |
| `kbs:///default/eastwest-nim/tls.crt` | NIM server cert | `nim-terminator` only |
| `kbs:///default/eastwest-nim/tls.key` | NIM server key | `nim-terminator` only |

NIM server cert SANs (explicit, not a wildcard):

- `glm-5-2-nvfp4-sglang.nemo.svc.cluster.local`
- `dsv4-0731-sglang-h200.nemo.svc.cluster.local`

Generate the CA and leaf certs once, load them into Trustee with `kbs-client` and an admin JWT. Admin mode is `AuthenticatedAuthorization`; rotate and Fleet config live in the Trustee bundle `infrastructure/trustee/KubeTEE.md` (`kubetee-fleet`). Never commit the keys. Cert lifetime for this cut: ~90 days. Rotate by replacing KBS material and rolling guests. Short-lived refresh is a later cut (GLM/DSV4 boots take hours).

Initdata: a CoCo/Kata initdata document with `role: litellm` or `role: nim-terminator`, bound into the quote so KBS policy can distinguish the two guests. Exact annotation/TOML is an implementation detail; the role split is not.

## Guest boot

1. Enable AA/KBS on first-cut pods (`agent.aa_kbc_params=cc_kbc::http://kbs-service.trustee-operator-system.svc.cluster.local:8080`). Those kernel args are commented on the SGLang manifests today.
2. Init container in the **same** Kata sandbox: CDH `get_resource` for the role’s URIs → write to a shared `emptyDir`.
3. If fetch fails, do not start HAProxy on `:8443`. Fail closed. Do not fall back to HTTP for LiteLLM after cutover.
4. Main containers: SGLang binds `127.0.0.1:8000`; HAProxy uses the files on `emptyDir` (init concatenates `tls.crt`+`tls.key` into a `.pem` — HAProxy’s usual `crt` form).

Images stay public + `imagePullPolicy: IfNotPresent` (host pull). HAProxy (`docker.io/library/haproxy:3.4.3-alpine`, 3.4 LTS) is an extra container in the sandbox, not a second VM. Same image inbound and outbound. Not nginx (SSE buffering footgun), not Envoy/Traefik (mesh-sized TCB in the measured guest).

Never `kubectl delete --force` on these pods.

## NIM guest (inbound)

Second container: HAProxy, `bind :8443 ssl crt … ca-file … verify optional`, backend `127.0.0.1:8000` (HTTP). SGLang stays HTTP on loopback. `http-request deny` unless the path is `GET /health` or `/health_generate`, or the client presents a verified Trustee cert. Kubelet HTTPS probes (no client cert, skip server verify) use those two paths on `:8443`. Ready also requires the HAProxy sidecar TCP `:8443`.

Service: port `8443` only (`https`). Pod IP `:8000` is not listening.

## LiteLLM guest (outbound)

Public hop unchanged: Let’s Encrypt on `:4000`, Traefik TLS passthrough, Cloudflare grey-cloud.

LiteLLM 1.96 `ssl_certificate` is ignored by httpx 0.28. Live outbound mTLS is `sitecustomize.py` in ConfigMap `eastwest-fetch-certs`: it loads `/certs/tls.crt` + `/certs/tls.key` into the default `SSLContext`. `api_base` is the Service HTTPS URL (not loopback HAProxy):

| Upstream Service | Live `api_base` |
|------------------|-----------------|
| GLM | `https://glm-5-2-nvfp4-sglang.nemo.svc.cluster.local:8443/v1` |
| DSV4 H200 | `https://dsv4-0731-sglang-h200.nemo.svc.cluster.local:8443/v1` |

`model_list` in the ConfigMap stays `[]`. Flip `api_base` via `/model/update` and **re-include** every `litellm_params` field (known gotcha: unspecified list fields are nulled). Scripts: `nim/scripts/litellm-glm52-https-8443.py`, `nim/scripts/litellm-dsv4-https-8443.py`.

## Rollout

1. Seed Trustee resources. Confirm CoCo AS (`coco_as_builtin`) is the verifier. Confirm policy denies debug-on guests.
2. GLM + DSV4: enable AA/KBS, add init + HAProxy, add Service `:8443`, readiness includes `:8443`. Graceful apply/rollout only. Wait for Kata teardown; do not `--force`.
3. Prove `openssl s_client` / curl mTLS to each Service `:8443` from a throwaway in-cluster client **before** touching LiteLLM (or from a debug guest that is allowed to hold the client cert).
4. LiteLLM: add init + outbound HAProxy. Do not flip `api_base` until loopback proxies are up.
5. Flip GLM and DSV4 `api_base` rows to loopback. Chat + streaming through `llm.kubetee.ai`.
6. Drop Service `:8000` after LiteLLM `api_base` is `:8443`. Bind SGLang to `127.0.0.1` and move kubelet probes to HTTPS `:8443`.

A leftover Terminating LiteLLM pod from an earlier sidecar experiment must be left to finish or the node rebooted — never `--force`.

## Tests

- Chat completion + streaming via `llm.kubetee.ai` for `z-ai/glm-5.2` and `deepseek/deepseek-v4-flash-0731`.
- Request to `:8443` without a client cert → HAProxy rejects (`403`) except `GET /health` and `/health_generate`.
- Guest with debug on or wrong initdata role → CDH denies; pod not Ready on `:8443`.
- One GLM replica not Ready → Service has the other; no 8443 traffic to the unready pod.

## Follow-up: restore HAProxy sidecar (kata#11649)

**Intended shape is still a second container** in the same Kata sandbox (`docker.io/library/haproxy:3.4.3-alpine`). Live GLM-1 on `na-us-oakland-56` (2026-08-14) hit QEMU `Duplicate nodes with node-name='drive-5'` after an init/sidecar EROFS unplug.

Root cause (not a parallel-Create race): `wait_for_device_deleted` reset QMP `SO_RCVTIMEO` to **250ms**. The next container's multi-layer EROFS `blockdev-add` then returned `WouldBlock` after QEMU had already created `drive-N`. CreateContainer retry → Duplicate. That is [kata-containers#11649](https://github.com/kata-containers/kata-containers/issues/11649). Overlay **fix15** (now in current `v4.0.0-nvswitch-fix17`) keeps a 60s hotplug timeout and treats Duplicate / in-use / timed-out-but-present as success. That shim is on the node (2026-08-15). Restore the sidecar when ready; upstream [#13635](https://github.com/kata-containers/kata-containers/pull/13635) is still OPEN.

Already in kata-deploy **4.0.0** (not enough for this race):

- [#13216](https://github.com/kata-containers/kata-containers/pull/13216) — hot-unplug block devices (merged 2026-06-22, related to #11649)

Still missing (do **not** put the sidecar back until this is in a tag we run, or in the shim overlay):

- [#11650](https://github.com/kata-containers/kata-containers/pull/11650) — idempotent `blockdev-add` (`Fixes #11649`) — **closed without merge**
- Or any later PR that serializes / uniquifies `drive-N` across parallel `CreateContainer`

Check:

```bash
gh issue view 11649 --repo kata-containers/kata-containers --json state,closedAt,title
gh pr list --repo kata-containers/kata-containers --search "11649" --state all
```

When #11649 is actually fixed in the running `containerd-shim-kata-v2` (next kata-deploy tag **> 4.0.0**, or a shim-overlay slice that includes the atomicity patch — not merely #13216):

1. Restore the HAProxy sidecar on GLM/DSV4 (`nim/glm-5-2-nvfp4-sglang-cc.yaml` and the DSV4 manifest). A `fetch-certs` init is the same class of extra EROFS — do not add it back either.
2. Drop in-process fetch + HAProxy from `start-sglang.sh` (keep `fetch-certs.sh` for the sidecar/init once #11649 is actually fixed).
3. Keep `partition: 1` until glm-0 is ready to roll; never `--force` CC pods.

Until then, inbound terminator stays in-process in the SGLang container.

## Later (not this cut)

- Same pattern on remaining models on `na-us-oakland-56`.
- Miner-cluster backends — spec below. Do not start this until KBS resource fetch is attested or TLS-pinned.
- NIM containers: reuse Trustee + LiteLLM sidecar; add Operator sidecar or native `NIM_SSL_MODE=mtls` only if that NIM actually requires client certs.
- Public-hop RA-TLS (quote bound to the Let’s Encrypt / terminator key) for clients that attest `llm.kubetee.ai`.
- Short-lived certs with CDH refresh after model load.
- In-guest keygen + `report_data` binding if a future profile requires keys that never exist in Trustee.

## Later: miner-cluster backends

LiteLLM stays on the infra cluster (`na-us-oakland-56`). Miner clusters run models (e.g. DSV4-Flash-0731) in TEE and do **not** run LiteLLM. LiteLLM’s `api_base` points at the remote guest over the WAN. Same CoCo pattern as this cut: Trustee issues TLS after attestation; apps speak ordinary mTLS. The miner host, kubelet, and CNI stay untrusted.

```text
LiteLLM guest (oakland, TEE)
    |  mTLS  (Trustee CA + LiteLLM client cert)
    |  SNI = dsv4-0731.<cluster>.inference.kubetee.ai
    v
L4 only  (allowlist or WG — no HTTP terminate)
    v
Miner Traefik / ServiceLB  TCP passthrough
    v
DSV4 guest HAProxy :8443  (same sandbox as SGLang)
    |  HTTP 127.0.0.1:8000
    v
SGLang
```

### Do this

1. **One Trustee KubeTEE operates.** Remote guests attest to *this* KBS (CoCo AS, `td_attributes.debug == false`, initdata role `nim-terminator`). Do not trust a Trustee the miner runs — that makes the miner the CA.

2. **Per-cluster server cert, KubeTEE DNS.** Explicit SAN, not a wildcard, e.g. `dsv4-0731.as-in-delhi-staging-0.inference.kubetee.ai`. Bind `[data] cluster` in initdata so KBS releases only that cluster’s key (`kbs:///default/eastwest-nim-<cluster>/…`). LiteLLM `api_base` is that HTTPS URL. Hostname verify is the binding: the miner can point DNS at a fake; without the attested key, TLS fails.

3. **L4 passthrough only.** Same as `llm.kubetee.ai`: Traefik/ServiceLB TCP → Service `:8443` → guest HAProxy. No Cloudflare HTTP, no ingress TLS, no nginx in front. If the miner terminates TLS, that hop is not TEE-in-transit.

4. **Do not publish `:8443` to the open internet** while HAProxy allows unauthenticated `GET /health` and `/health_generate` (kubelet probes). Prefer an allowlist (oakland egress) or a WireGuard/IPsec **outer** tunnel, then mTLS inside. Host-level WG/IPsec alone is not enough — it has no per-workload attestation and leaves host↔pod in the clear ([§2](./NEMO-MICROSERVICES-AND-SUBNET-INTEGRATIONS.md#2-attestation-gated-tls-between-services)).

5. **Close KBS-over-HTTP before the first remote guest.** CDH fetches `eastwest-nim/tls.key` over `http://kbs-service…:8080`. On oakland that is already a host-sniff risk. Across a miner WAN it is fatal: the miner can take the server key on first boot and impersonate the TEE. Guests must reach KBS on an attested or TLS-pinned channel (CoCo RA-TLS to Trustee, or HTTPS with the KBS CA in measured initdata). Until that exists, do not release east-west keys to a remote cluster.

### Do not use

| Approach | Why it fails |
|----------|----------------|
| LiteLLM on every miner | Puts API keys, routing, and spend on untrusted hardware |
| Istio / Linkerd / Cilium cluster mesh | Identity is a ServiceAccount; miner flips `runtimeClassName` and keeps a valid cert |
| cert-manager / Let’s Encrypt on the miner ingress | Key lives in etcd or at the terminator |
| Miner-local Trustee | Miner issues certs to non-TEE pods |
| Cloudflare / HTTP ingress | L7 sees plaintext |
| WireGuard or cluster mesh *instead of* Trustee mTLS | No “this peer attested” |

Quote-in-handshake RA-TLS on LiteLLM→DSV4 is a later hardening (stolen Trustee leaf would not matter). Not required for the first remote backend if KBS release is attested and the leaf key never exists outside a guest.

### LiteLLM cutover (when a miner is ready)

`/model/update` only — no LiteLLM deploy on the miner. Restate every `litellm_params` field. Same client cert, new server cert + passthrough:

`https://dsv4-0731.<cluster>.inference.kubetee.ai/v1`
