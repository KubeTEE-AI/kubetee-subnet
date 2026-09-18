# East-west attested mTLS (LiteLLM ↔ inference guests)

**Status:** deployed on staging `na-us-oakland-56` (2026-08-15; rows synced 2026-09-11). Five east-west backends, all 2 replicas: `glm-5-2-nvfp4-sglang` (B200), `glm-5-3-flash-sglang-h200`, `ornith-1-5-397b-fp8-sglang-h200`, `dsv41-flash-sglang-h200` (H200), `glm-5-3-sglang-b200-cc` (B200). Services expose `:8443` only. SGLang binds `127.0.0.1:8000` (pod IP `:8000` connection refused). Kubelet HTTPS probes use `:8443` `/health` and `/health_generate` (HAProxy `verify optional` on those GET paths only; all other paths need a verified client cert). LiteLLM presents the Trustee client cert via `sitecustomize.py` (httpx 0.28 ignores `ssl_certificate`). Public hop is still Let’s Encrypt + Traefik. KBS resource policy is still upstream `default.rego` — path×role + cpu0-affirming 401s after attest 200.  
**Date:** 2026-08-15 (rows synced 2026-09-11)  
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

Live LiteLLM `api_base` rows (HTTPS `:8443`), synced 2026-09-11 against `GET /v1/model/info` + the `nemo` StatefulSets. Public names: `z-ai/glm-5.2`, `z-ai/glm-5.3`, `z-ai/glm-5.3-flash`, `ornith/ornith-1.5-397b`, `deepseek/deepseek-v4.1-flash`.

| LiteLLM `model_name` | Service (TLS hostname) | Manifest | Public |
|--------------|------------------------|----------|--------|
| `z-ai/glm-5.2` | `glm-5-2-nvfp4-sglang.nemo.svc.cluster.local` | `nim/glm-5-2-nvfp4-sglang-cc.yaml` (StatefulSet, 2 replicas, one Service) | yes |
| `z-ai/glm-5.3-flash` | `glm-5-3-flash-sglang-h200.nemo.svc.cluster.local` | `nim/glm-5-3-flash-sglang-h200-cc.yaml` (H200 CC, 2 replicas, 2026-08-27) | yes |
| `z-ai/glm-5.3` | `glm-5-3-sglang-b200-cc.nemo.svc.cluster.local` | `nim/glm-5-3-sglang-b200-cc.yaml` (B200 CC, 2 replicas; retargeted from non-CC `:8000` 2026-09-11) | yes |
| `ornith/ornith-1.5-397b` | `ornith-1-5-397b-fp8-sglang-h200.nemo.svc.cluster.local` | `nim/ornith-1.5-397b-fp8-sglang-h200-cc.yaml` (H200 CC, 2 replicas; short name retargeted 2026-08-28) | yes (SayGM) |
| `deepseek/deepseek-v4.1-flash` | `dsv41-flash-sglang-h200.nemo.svc.cluster.local` | `nim/deepseek-v4-1-flash-sglang-h200-cc.yaml` (H200 CC, 2 replicas 2026-09-11) | yes |
| `moonshotai/kimi-k3` | `kimi-k3-sglang-cc.nemo.svc.cluster.local:8000` | `nim/kimi-k3-sglang-b300.yaml` (B300, non-CC) — **row is stale: Service deleted, backend gone; do not route to it** | no |

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
- `dsv4-0731-sglang-h200.nemo.svc.cluster.local` (STOPPED — backend deleted, replaced by V4.1-Flash; SAN kept)
- `ornith-1-5-397b-fp8-sglang-h200.nemo.svc.cluster.local`
- `glm-5-3-flash-sglang-h200.nemo.svc.cluster.local` (added 2026-08-27)
- `glm-5-3-sglang-b200-cc.nemo.svc.cluster.local` (added 2026-09-11)
- `dsv41-flash-sglang-h200.nemo.svc.cluster.local` (added 2026-09-10)

Generate the CA and leaf certs once, load them into Trustee with `kbs-client` and an admin JWT. Admin mode is `AuthenticatedAuthorization`; rotate and Fleet config live in the Trustee bundle `infrastructure/trustee/KubeTEE.md` (`kubetee-fleet`). Never commit the keys. Cert lifetime for this cut: ~90 days. Rotate by replacing KBS material and rolling guests. Short-lived refresh is a later cut (GLM/DSV4 boots take hours).

Initdata: a CoCo/Kata initdata document with `role: litellm` or `role: nim-terminator`, bound into the quote so KBS policy can distinguish the two guests. Exact annotation/TOML is an implementation detail; the role split is not.

## Guest boot

1. Enable AA/KBS on first-cut pods (`agent.aa_kbc_params=cc_kbc::http://kbs-service.trustee-operator-system.svc.cluster.local:8080`). Those kernel args are commented on the SGLang manifests today.
2. Init container in the **same** Kata sandbox: CDH `get_resource` for the role’s URIs → write to a shared `emptyDir`.
3. If fetch fails, do not start HAProxy on `:8443`. Fail closed. Do not fall back to HTTP for LiteLLM after cutover.
4. Main containers: SGLang binds `127.0.0.1:8000`; HAProxy uses the files on `emptyDir` (init concatenates `tls.crt`+`tls.key` into a `.pem` — HAProxy’s usual `crt` form).

Images stay public + `imagePullPolicy: IfNotPresent` (host pull). HAProxy is an extra container in the sandbox, not a second VM. Same image inbound and outbound. Not nginx (SSE buffering footgun), not Envoy/Traefik (mesh-sized TCB in the measured guest).

**2026-09-16 — HAProxy sidecar is the permanent terminator; in-process TLS rejected.** We evaluated replacing the sidecar with SGLang's embedded servers (Granian via `--enable-http2`, or the default uvicorn path) and keeping no proxy at all. Rejected on verified stock-code evidence (v0.5.19):

- SGLang hardcodes `ssl_verify=False  # MTls is not supported` at both Granian call sites — no flag or env reaches it.
- The uvicorn path passes `--ssl-ca-certs` but never `ssl_cert_reqs` (uvicorn default `CERT_NONE`); `load_verify_locations` does **not** flip `verify_mode`, so client certs are never verified — anyone with pod-network access calls the API.
- Granian's rustls layer *does* have perfect `verify optional` semantics (`WebPkiClientVerifier::allow_unauthenticated()` when `ssl_ca` set, `client_verify` false — verified in granian `src/workers.rs`), but it is unreachable without patching the SGLang image, and the embedded server mode has no app-visible client-cert path to enforce the probe-vs-API split at the app layer.

KubeTEE policy: **no patched SGLang images for mTLS** — the sidecar is stack-agnostic (same config for SGLang any version, vLLM `glm-45-air`, and any future stack), needs zero per-version image maintenance, and its ACL already encodes the exact probe/client split. LiteLLM's own in-process granian TLS (northbound, server-side only, no client certs) is unaffected.

**Image standard (2026-09-16, rev 2):** `docker.io/library/haproxy:3.4.4-alpine` (digest-pinned, amd64 sha256 `745c6d0c1d54…`) — the official `docker-library/haproxy` 3.4 LTS build. **Runs as `USER haproxy` (uid 99) by default** (Dockerfile ends `USER haproxy`, `STOPSIGNAL SIGUSR1`), so the container is non-root out of the box; manifests add `runAsUser: 99` + `runAsGroup: 99` explicitly, `allowPrivilegeEscalation: false`, `readOnlyRootFilesystem: true`, all caps dropped. Port 8443 > 1024 needs no privileged bind. **Why not Docker Hardened Images (DHI):** the DHI FIPS variant (`haproxy/debian-13/3.4-fips`) requires **authenticated `dhi.io` pulls** — a permanent auth dependency in the supply chain that breaks our anonymous CC guest-pulls. Re-evaluate only if dhi.io introduces anonymous pulls or a public mirror. Our PKI (RSA 2048/4096 + SHA-256) is FIPS-approved — no cert changes either way. Version floor: HAProxy ≥ 3.4.x (3.4 LTS, active support to Apr 2031); was `docker.io/library/haproxy:3.4.3-alpine` before this cut.

**Canary verified (2026-09-17, ornith pod-1 on `am-h200-29`):** 2/2 Running, 0 restarts, logs clean (`nbthread` forced to 2 over 19 detected guest CPUs — matches the ceil(16+2+0.5)=19 vCPU sizing), 4× gateway 200s for `ornith/ornith-1.5-397b`. The pod survived both the node's cold reboot (iommufd wedge) and the RKE2 1.36.4 upgrade. Fleet roll = recreate each remaining replica through the standard cordon-cycle-at-the-ready plan; never `--force`.

**Resource standard (2026-09-16):** `requests == limits` — **2 CPU / 512Mi**. With the sglang/vllm container already requests==limits, this makes the **pod Guaranteed QoS** (verified Burstable on the canary only because the `fetch-certs` init container carries no resources block — add one on the fleet roll if Guaranteed is wanted; the throttle/OOMKill goals are met regardless): no CFS throttling (the 500m cap caused watchdog "stopped processing traffic" warnings during weight-load phases — fixed in the cfg with `nbthread 2` + `warn-blocked-traffic-after 1000ms` on 2026-09-12, now backed by a full core per thread), and no OOMKill gamble (512Mi = maxconn 4096 × 2×16KiB buffers ≈ 128Mi + TLS state + 2 threads; an OOMKill here means the cordon + cold-reboot iommufd-wedge cycle, so over-provision). Guest vCPU cost: ceil(16 + 2 + 0.5) = 19 vs 17 — negligible. Never size this sidecar "small" — it is the pod's only network path.

Never `kubectl delete --force` on these pods.

## NIM guest (inbound)

Second container: HAProxy, `bind :8443 ssl crt … ca-file … verify optional alpn h2,http/1.1` (HTTP/2 negotiated by LiteLLM's httpx client; http/1.1 for kubelet probes), backend `127.0.0.1:8000` (HTTP). SGLang stays HTTP on loopback. `http-request deny` unless the path is `GET /health` or `/health_generate`, or the client presents a verified Trustee cert. Kubelet HTTPS probes (no client cert, skip server verify) use those two paths on `:8443`. Ready also requires the HAProxy sidecar TCP `:8443`.

**HTTP/2 on this hop (verified 2026-09-17):** in-cluster curl against both pod IPs negotiated `h2` and got `HTTP/2 200`. Note the explicit `alpn h2,http/1.1` is belt-and-suspenders — **HAProxy ≥2.8 already defaults the HTTPS bind ALPN to `h2,http/1.1`** when no `alpn`/`npn`/`no-alpn` is set (confirmed: pod-0, still on 3.4.3 + the pre-`alpn` config, negotiated h2 fine). The keyword pins the behavior against a future default change and self-documents intent; `no-alpn` would be needed to *disable* it.

Service: port `8443` only (`https`). Pod IP `:8000` is not listening.

## LiteLLM guest (outbound)

Public hop unchanged: Let’s Encrypt on `:4000`, Traefik TLS passthrough, Cloudflare grey-cloud.

LiteLLM 1.96 `ssl_certificate` is ignored by httpx 0.28. Live outbound mTLS is `sitecustomize.py` in ConfigMap `eastwest-fetch-certs`: it loads `/certs/tls.crt` + `/certs/tls.key` into the default `SSLContext`. `api_base` is the Service HTTPS URL (not loopback HAProxy):

| Upstream Service | Live `api_base` |
|------------------|-----------------|
| GLM | `https://glm-5-2-nvfp4-sglang.nemo.svc.cluster.local:8443/v1` |

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

## Follow-up: restore HAProxy sidecar (kata#11649) — DONE

**Status (2026-09-17): complete.** The sidecar is the **permanent inbound terminator** (decision 2026-09-16) and is rolled on all 10 CC pods on `na-us-oakland-56` — every confidential pod now runs `fetch-certs` init + `haproxy` sidecar + SGLang in the same sandbox, on the MINIMAL `v4.2.0-fix11649` shim overlay.

History: live GLM-1 on `na-us-oakland-56` (2026-08-14) hit QEMU `Duplicate nodes with node-name='drive-5'` after an init/sidecar EROFS unplug — [kata-containers#11649](https://github.com/kata-containers/kata-containers/issues/11649). Root cause (not a parallel-Create race): `wait_for_device_deleted` reset QMP `SO_RCVTIMEO` to **250ms**; the next container's multi-layer EROFS `blockdev-add` then returned `WouldBlock` after QEMU had already created `drive-N`; CreateContainer retry → Duplicate. The sidecar was pulled out until the shim carried a fix.

**The fix is deployed (2026-09-17):** #11649 was reproduced **deterministically on stock kata 4.2.0** (ornith-1 on `am-h200-29`, glm-5-3-flash on `am-h200-23`: `duplicate QEMU block device ID drive-5` CrashLoopBackOff after every `fetch-certs` init unplug), and the MINIMAL `v4.2.0-fix11649` overlay (idempotent `blockdev-add` — pre-check `query_named_block_nodes`, delete orphaned backend, treat duplicate/timeout as success-or-continue, keep a 60s hotplug-sized QMP read timeout) is live on **both** oakland (staging) and michigan-97 (production). With it, the init + sidecar + main-container sequence boots clean; both wedged pods recovered on the fixed shim. Upstream: [#13635](https://github.com/kata-containers/kata-containers/pull/13635) was **closed unmerged** (2026-09-13, issues-only policy); the issue is OPEN with our live-repro comment (2026-09-17) — no fix in flight. Keep the overlay until an official kata-deploy tag contains the fix.

Upstream fix status (as of 2026-09-17):

- [#13216](https://github.com/kata-containers/kata-containers/pull/13216) — hot-unplug block devices (merged 2026-06-22; in 4.0.0+; not sufficient)
- [#11650](https://github.com/kata-containers/kata-containers/pull/11650) — idempotent `blockdev-add` (`Fixes #11649`) — **closed without merge**
- [#13635](https://github.com/kata-containers/kata-containers/pull/13635) — idempotent `blockdev-add` after unplug timeout — **closed unmerged 2026-09-13** (AI-prose policy; all our runtime-rs PRs were withdrawn)

Check:

```bash
gh issue view 11649 --repo kata-containers/kata-containers --json state,closedAt,title
gh pr list --repo kata-containers/kata-containers --search "11649" --state all
```

When #11649 is actually fixed in the **stock** `containerd-shim-kata-v2` (a kata-deploy tag containing the idempotent `blockdev-add`), retire the `v4.2.0-fix11649` overlay and re-verify a sidecar roll on stock. Until then the overlay is load-bearing for every CC pod with an init container.

## Later (not this cut)

- Same pattern on remaining models on `na-us-oakland-56`.
- Miner-cluster backends — spec below. Do not start this until KBS resource fetch is attested or TLS-pinned.
- NIM containers: reuse Trustee + LiteLLM sidecar; add Operator sidecar or native `NIM_SSL_MODE=mtls` only if that NIM actually requires client certs.
- Per-request GPU quotes from inference backends (current contract: boot-time attestation + backend identity headers).
- Short-lived certs with CDH refresh after model load.
- In-guest keygen + `report_data` binding if a future profile requires keys that never exist in Trustee.

## Client-facing attestation — SHIPPED (2026-09-18)

Clients of `llm.kubetee.ai` can request cryptographic proof that responses
come from a TDX confidential gateway guest. Full client contract (API surface,
nonce semantics, Intel Trust Authority + local DCAP verification paths):
[CLIENT-FACING-ATTESTATION.md](./CLIENT-FACING-ATTESTATION.md).

- `GET /v1/attestation?nonce=<64 hex>` — fresh TDX quote with `SHA512(nonce)`
  bound into `REPORTDATA` (pod field pins the minting replica).
- `X-KubeTEE-Nonce: <64 hex>` request header on `/v1/chat/completions` —
  response carries `X-KubeTEE-Attestation-Quote` + backend identity headers
  on the same response (streaming and non-streaming).
- Gateway prompt logging is off (`turn_off_message_logging`); the guest runs
  a measured container allowlist (agent policy in `cc_init_data`).

Public-hop RA-TLS (quote bound to the terminator key) remains a later
hardening option on top of this.

## Public KBS endpoint — SHIPPED (2026-09-18): `https://kbs.kubetee.ai`

Production-cluster guests (michigan-97 today, miner production clusters
later) attest against the oakland Trustee over a public endpoint instead
of the in-cluster ClusterIP URL. Fleet bundle
`fleet-gitops/infrastructure/kbs-gateway/` (GitRepo
`kbs-gateway-staging`, oakland only):

- **Traefik Gateway API** (not IngressRoute): `Gateway kbs-gateway`
  (HTTPS listener on **entrypoint** port 8443 — the traefik #11842 gotcha:
  listener ports match entrypoints, not the LB Service port 443), TLS
  Terminate with `Certificate kbs-tls` (Let's Encrypt DNS-01 via
  `letsencrypt-prod`), `HTTPRoute kbs-route` → `kbs-service:8080` (HTTP).
- **Exact-path allowlist**: `/kbs/v0/auth`, `/kbs/v0/attest` (Exact) +
  `/kbs/v0/resource/` (PathPrefix). A first cut with `PathPrefix /kbs/v0/`
  leaked the admin endpoints (found live: `/kbs/v0/resource-policy` 401
  instead of 404) — admin, `/metrics`, `/healthz` now 404 at the Gateway.
- **DNS**: external-dns `gateway-httproute` source (added to the shared
  bundle 2026-09-18) publishes from the HTTPRoute hostname + Gateway
  status.addresses (= traefik `statusaddress` → rke2-traefik LB Service →
  all node ExternalIPs, grey cloud).
- **Guest side needs zero changes**: `cc_kbc` is reqwest + rustls +
  webpki-roots (ISRG Root X1) — the public LE chain validates with no
  `KBS_CERT`. Verified end-to-end 2026-09-18: a mirror of the LiteLLM
  CPU-TDX guest with `aa_kbc_params=cc_kbc::https://kbs.kubetee.ai`
  completed the **full RCAR handshake through the public Gateway**
  (auth → attest → resource: fetched the 1854-byte east-west CA over TLS).
  Oakland's own guests keep the in-cluster URL (no hairpin through traefik).
- Production guests bake `https://kbs.kubetee.ai` into `cc_init_data` /
  kernel params at their first CC rollout (michigan has zero CC pods today,
  so nothing to re-encode yet). The measured agent-policy allowlist in
  `cc_init_data` is per-deployment (same encode-initdata.py flow).

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

1. **One Trustee KubeTEE operates.** Remote guests attest to *this* KBS (CoCo AS, `td_attributes.debug == false`, initdata role `nim-terminator`) over the public endpoint `https://kbs.kubetee.ai` (see "Public KBS endpoint" above — live since 2026-09-18, full RCAR verified through it). Do not trust a Trustee the miner runs — that makes the miner the CA.

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
