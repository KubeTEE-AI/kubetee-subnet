# East-west attested mTLS (LiteLLM ↔ inference guests)

> **Merged document (2026-10-27):** the live spec (**Part I**) and the roadmap
> (**Part II**) now live in this one file. `EAST-WEST-ATTESTED-MTLS-PLAN.md` is
> retired — its content is Part II below. This **reverses** that file's earlier
> "do not collapse the two files" rule (2026-08-15: the split was live-spec vs
> roadmap); the split drifted and its tables contradicted each other, so one
> document is the source of truth now. **Rule going forward:** a sentence about
> current cluster behavior goes in Part I, unfinished work goes in Part II.

**Status:** deployed on staging `na-us-oakland-56` and production `na-us-michigan-97` (first cut 2026-08-15; rows synced 2026-10-16). East-west backends — live STS counts 2026-10-16: `glm-5-2-fp8-sglang-h200-oakland` (H200 FP8, na-us-oakland-56 since 2026-10-19, 2 replicas per-pod; michigan-97's 3-replica deployment **decommissioned 2026-10-20**, `mi-h200-161/164/165` freed; earlier B200 NVFP4 `glm-5-2-nvfp4-sglang` deleted 2026-10-13), `glm-5-3-radixark-nvfp4-sglang-b200-cc` (B200 **RadixArk NVFP4**, 2 replicas — the `z-ai/glm-5.3` backend since 2026-10-13), `ornith-1-5-397b-fp8-sglang-h200` (H200 FP8, michigan-97, 1 replica), `dsv41-flash-sglang-h200` (H200, 1 replica on am-h200-27 — scaled 2→1 2026-10-16, per-pod row `68b87577` → `dsv41-flash-sglang-h200-0`; group row `0a4c740e` deleted same day), `mimo-v2-6-pro-rl-sglang-b200-cc` (B200 CC, 2 replicas). `glm-5-3-sglang-b200-cc` (FP8) and `glm-5-3-nvfp4-sglang-b200-cc` (NVIDIA ModelOpt NVFP4) sit at 0 replicas as warm fallbacks. Nemotron-Omni / MiniMax-H3 / MiniMax-Music3 on michigan-97 run the same in-guest HAProxy terminator behind the east-west Gateway's L4/SNI passthrough (`*.na-us-michigan-97.inference.kubetee.ai`). Services expose `:8443` only. SGLang binds `127.0.0.1:8000` (pod IP `:8000` connection refused). Kubelet HTTPS probes use `:8443` `/health` and `/health_generate` (HAProxy `verify optional` on those GET paths only; all other paths need a verified client cert). LiteLLM presents the Trustee client cert via `sitecustomize.py` (httpx 0.28 ignores `ssl_certificate`). Public hop is still Let’s Encrypt + Traefik. KBS resource policy is the KubeTEE `resource-policy.rego` (**LIVE** since 2026-09-18, replacing upstream `default.rego`) — path×role + cpu0-affirming 401s after attest 200.  
**Date:** 2026-08-15 (rows synced 2026-10-16 — GLM-5.2 retargeted 2026-10-12/13, GLM-5.3 cut over to RadixArk NVFP4 2026-10-13)  
**Approach:** CoCo Confidential AI — Trustee issues TLS credentials after attestation. Apps speak ordinary mTLS. No quote parsing in LiteLLM or SGLang.  
**Roadmap:** remaining gaps (HTTPS KBS, gpu0/RVPS, sealed NGC, five-actor ops) — [Part II](#part-iistatus-table) below.

This is the implementation spec for [§2 Attestation-gated TLS](./NEMO-MICROSERVICES-AND-SUBNET-INTEGRATIONS.md#2-attestation-gated-tls-between-services).

## Contents

**Part I — live spec (what is deployed):** [Goal](#goal) · [Non-goals](#non-goals-this-cut) · [Threat model](#threat-model) · [Architecture](#architecture) · [First-cut workloads](#first-cut-workloads) · [Trustee / KBS](#trustee--kbs) · [Guest boot](#guest-boot) · [NIM guest (inbound)](#nim-guest-inbound) · [LiteLLM guest (outbound)](#liteLLM-guest-outbound) · [Rollout](#rollout) · [Tests](#tests) · [HAProxy sidecar (kata#11649) — DONE](#follow-up-restore-haproxy-sidecar-kata11649--done) · [Client-facing attestation — SHIPPED](#client-facing-attestation--shipped-2026-09-18) · [Public KBS endpoint — SHIPPED](#public-kbs-endpoint--shipped-2026-09-18-httpskbskubeteeai) · [Miner-cluster backends — SHIPPED](#miner-cluster-backends) · [Later (not this cut)](#later-not-this-cut)

**Part II — roadmap (gaps, phased work, what to adopt/adapt/ignore):** [Trustee state + gaps](#trustee-is-live-stale-docs-correction) · [Phase 0 built](#phase-0--already-built-do-not-redo) · [File map](#file-map) · [Hard constraints](#hard-constraints) · [Adopt / adapt / ignore](#steal-from-coco-nim-attestation-example-2026-08-15) · [Phase 1 durable storage](#phase-1-durable-trustee-storage) · [Phase 2 KBS HTTPS](#phase-2-kbs-https--cert-in-measured-initdata) · [Phase 3 resource policy](#phase-3-resource-policy-pathrole--cpu0-then-gpu0) · [Phase 4 sealed NGC/HF](#phase-4-sealed-ngchf-later-luks-keys) · [Phase 5 five-actor](#phase-5-five-actor-split) · [Phase 6 sidecar — DONE](#phase-6-restore-haproxy-sidecar--complete-2026-09-17) · [Phase 7 miner backends](#phase-7-miner-cluster-backends-blocked) · [Phase 8 client attestation — DONE](#phase-8-client-facing-attestation-of-inference--complete-2026-09-18) · [Status table](#part-iistatus-table)

---

# Part I — live spec (what is deployed)

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
- Miner-cluster backends (see [Miner-cluster backends](#miner-cluster-backends))

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

Live LiteLLM `api_base` rows (HTTPS `:8443`), synced 2026-10-16 against the `nemo` StatefulSets (GLM-5.2 row retargeted 2026-10-12/13; GLM-5.3 row cut over to RadixArk NVFP4 2026-10-13). Public names: `z-ai/glm-5.2`, `z-ai/glm-5.3`, `ornith/ornith-1.5-397b`, `deepseek/deepseek-v4.1-flash-1017` (since 2026-10-17; the older `deepseek/deepseek-v4.1-flash` name is kept as a working alias during the dual-name transition), `xiaomi/mimo-v2.6-pro-ultraspeed`. **This table is a point-in-time record** — the live catalog is the model-catalog header in `fleet-gitops/infrastructure/litellm/staging/values.yaml` + `nim/CLAUDE.md`.

| LiteLLM `model_name` | Service (TLS hostname) | Manifest | Public |
|--------------|------------------------|----------|--------|
| `z-ai/glm-5.2` | `glm-5-2-fp8-sglang-h200-{0,1}.nemo.svc.cluster.local` (per-pod rows) | `nim/glm-5-2-fp8-sglang-h200-oakland-cc.yaml` (H200 CC FP8, na-us-oakland-56, 2 replicas; since 2026-10-19. Michigan-97 `nim/glm-5-2-fp8-sglang-h200-cc.yaml` **decommissioned 2026-10-20**; B200 NVFP4 deleted 2026-10-13) | no (in-cluster rows) |
| `z-ai/glm-5.3-flash` | `glm-5-3-flash-sglang-h200.nemo.svc.cluster.local` | `nim/glm-5-3-flash-sglang-h200-cc.yaml` (H200 CC; was 5 replicas — 4→5 burst canary 2026-10-16, 2 since 2026-08-27) — **withdrawn 2026-10-26** (removed from the catalog) | no |
| `z-ai/glm-5.3` | `glm-5-3-radixark-nvfp4-sglang-b200-cc.nemo.svc.cluster.local` | `nim/glm-5-3-radixark-nvfp4-sglang-b200-cc.yaml` (B200 CC **RadixArk NVFP4**, 2 replicas; production since 2026-10-13. FP8 `nim/glm-5-3-sglang-b200-cc.yaml` + NVIDIA NVFP4 `nim/glm-5-3-nvfp4-sglang-b200-cc.yaml` parked at 0/1 replicas as fallback) | yes |
| `ornith/ornith-1.5-397b` | `ornith-1-5-397b-fp8-sglang-h200.nemo.svc.cluster.local` | `nim/ornith-1.5-397b-fp8-sglang-h200-cc.yaml` (H200 CC FP8, michigan-97, 1 replica; short name retargeted 2026-08-28) | yes (SayGM) |
| `deepseek/deepseek-v4.1-flash-1017` | `dsv41-flash-sglang-h200-0.nemo.svc.cluster.local` | `nim/deepseek-v4-1-flash-sglang-h200-cc.yaml` (H200 CC, 1 replica, **DeepSeek-V4.1-Flash-1017** weights since 2026-10-17 — Service `dsv41-flash-sglang-h200-0` on `statefulset.kubernetes.io/pod-name`; row `f0c2fc02-…`) | yes |
| `deepseek/deepseek-v4.1-flash` (ALIAS) | `dsv41-flash-sglang-h200-0.nemo.svc.cluster.local` | same backend + same pod (row `68b87577-…`, name kept for the SayGM dual-name transition, backend re-pointed to `DeepSeek-V4.1-Flash-1017` 2026-10-17) | yes |
| `xiaomi/mimo-v2.6-pro-ultraspeed` | `mimo-v2-6-pro-rl-sglang-b200-cc.nemo.svc.cluster.local` | `nim/mimo-v2-6-pro-rl-sglang-b200-cc.yaml` (B200 CC, 2 replicas since 2026-10-13; DFLASH spec decode) | yes (SayGM) |
| `mistralai/mistral-large-4` | `mistral-large-4.na-us-dallas-132.inference.kubetee.ai` | `nim/mistral-large-4-nvfp4-sglang-b200-cc.yaml` (B200 CC **NVFP4** SGLang, 1 replica on `na-us-dallas-132` / TEEmo `tx-b200-16` — **first dallas-132 miner-cluster model backend**; deployed 2026-10-30) | yes (SayGM) |
| `moonshotai/kimi-k3` | `kimi-k3-sglang-cc.nemo.svc.cluster.local:8000` | `nim/kimi-k3-sglang-b300.yaml` (B300, non-CC) — **row is stale: model row deleted 2026-10-05, Service deleted, backend gone; do not route to it** | no |

GLM HA uses the **existing Service**, not per-pod DNS. Each replica attests independently and receives the same NIM server cert (SAN = Service FQDN). ClusterIP load-balances TCP; a stream stays on one pod. Kubernetes readiness is pod-wide: a replica must not be Ready until HTTPS `:8443` `/health` succeeds (HAProxy up and SGLang healthy on loopback).

NVIDIA NIM containers would not change Trustee, LiteLLM sidecar, or Service SAN. They would only change NIM-side TLS (optional `NIM_SSL_MODE=mtls` if that LLM NIM implements it) and how a sidecar is injected (`NIMService` vs StatefulSet). Out of scope for this cut.

## Trustee / KBS

AS verifies TDX quotes with **CoCo AS builtin** (`coco_as_builtin`): Intel-signed TDX DCAP quotes, collateral from on-cluster PCCS. First-cut attestation policy (no RTMR pin until RVPS is filled): Intel TDX quote header, `td_attributes.debug == false`, TCB `UpToDate`. Intended KBS release conditions (not live — see Trustee `KubeTEE.md`):

- EAR cpu0 is affirming
- `td_attributes.debug == false`
- Initdata **role** matches the resource (`litellm` vs `nim-terminator`)

**Resource policy state:** the first cut ran upstream `default.rego` (path×role + cpu0-affirming 401s after attest 200, 2026-08-15) — **superseded 2026-09-18** by the KubeTEE `resource-policy.rego` (cpu0 affirming + path×role, [Phase 3a](#phase-3-resource-policy-pathrole--cpu0-then-gpu0)). The intended conditions above are **now live**, except gpu0/initdata-digest (Phase 3b, blocked on RVPS).

Resources (illustrative URIs; keep the `default` repository unless Trustee layout forces otherwise):

| URI | Contents | Who may fetch |
|-----|----------|----------------|
| `kbs:///default/eastwest-ca/ca.pem` | East-west CA cert (public) | `litellm` and `nim-terminator` |
| `kbs:///default/eastwest-litellm/tls.crt` | LiteLLM client cert | `litellm` only |
| `kbs:///default/eastwest-litellm/tls.key` | LiteLLM client key | `litellm` only |
| `kbs:///default/eastwest-nim/tls.crt` | NIM server cert | `nim-terminator` only |
| `kbs:///default/eastwest-nim/tls.key` | NIM server key | `nim-terminator` only |

NIM server cert SANs (explicit, not a wildcard):

- `glm-5-2-fp8-sglang-h200.nemo.svc.cluster.local` (STOPPED — michigan backend decommissioned 2026-10-20; SAN kept like `dsv4-0731` above; the oakland per-pod SANs `glm-5-2-fp8-sglang-h200-{0,1}.nemo.svc.cluster.local` carry serving since 2026-10-19)
- `dsv4-0731-sglang-h200.nemo.svc.cluster.local` (STOPPED — backend deleted, replaced by V4.1-Flash; SAN kept)
- `ornith-1-5-397b-fp8-sglang-h200.nemo.svc.cluster.local`
- `glm-5-3-sglang-b200-cc.nemo.svc.cluster.local` (added 2026-09-11)
- `dsv41-flash-sglang-h200.nemo.svc.cluster.local` (added 2026-09-10) + per-pod `-0` SAN (added 2026-10-16 for the per-pod LiteLLM row; `-1` follows the same recipe when scaled to 2)
- `mimo-v2-6-pro-rl-sglang-b200-cc.nemo.svc.cluster.local` (added for MiMo-V2.6-Pro, 2026-09-24)
- `glm-5-3-nvfp4-sglang-b200-cc.nemo.svc.cluster.local` + `glm-5-3-radixark-nvfp4-sglang-b200-cc.nemo.svc.cluster.local` (added 2026-10-13, the RadixArk production cutover)

The authoritative SAN list is `nim/eastwest/gen-certs.sh` — add a SAN there and re-sign `nim.crt` with the existing CA (never regenerate `ca.key`) whenever a new `:8443` Service is created. Legacy SANs for stopped backends (dsv4-pro-0813, glm-45-air, qwen38-flash-next, glm-5-2-nvfp4) remain in the cert but are not listed here.

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

<a id="nim-guest-inbound"></a>

## NIM guest (inbound)

Second container: HAProxy, `bind :8443 ssl crt … ca-file … verify optional alpn h2,http/1.1` (HTTP/2 negotiated by LiteLLM's httpx client; http/1.1 for kubelet probes), backend `127.0.0.1:8000` (HTTP). SGLang stays HTTP on loopback. `http-request deny` unless the path is `GET /health` or `GET /health_generate`, or the client presents a verified Trustee cert. Kubelet HTTPS probes (no client cert, skip server verify) use those two paths on `:8443`. Ready also requires the HAProxy sidecar TCP `:8443`.

**HTTP/2 on this hop (verified 2026-09-17):** in-cluster curl against both pod IPs negotiated `h2` and got `HTTP/2 200`. Note the explicit `alpn h2,http/1.1` is belt-and-suspenders — **HAProxy ≥2.8 already defaults the HTTPS bind ALPN to `h2,http/1.1`** when no `alpn`/`npn`/`no-alpn` is set (confirmed: pod-0, still on 3.4.3 + the pre-`alpn` config, negotiated h2 fine). The keyword pins the behavior against a future default change and self-documents intent; `no-alpn` would be needed to *disable* it.

Service: port `8443` only (`https`). Pod IP `:8000` is not listening.

## LiteLLM guest (outbound)

Public hop unchanged: Let’s Encrypt on `:4000`, Traefik TLS passthrough, Cloudflare grey-cloud.

LiteLLM `ssl_certificate` is ignored by httpx 0.28 (still true at 1.103.9). Live outbound mTLS is `sitecustomize.py` in ConfigMap `eastwest-fetch-certs`: it loads `/certs/tls.crt` + `/certs/tls.key` into the default `SSLContext`. `api_base` is the Service HTTPS URL (not loopback HAProxy):

| Upstream Service | Live `api_base` |
|------------------|-----------------|
| GLM | `https://glm-5-2-fp8-sglang-h200-{0,1}.nemo.svc.cluster.local:8443/v1` (per-pod, oakland; the michigan group Service was decommissioned 2026-10-20) |

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

- Chat completion + streaming via `llm.kubetee.ai` for `z-ai/glm-5.2` and `deepseek/deepseek-v4.1-flash-1017` (alias `deepseek/deepseek-v4.1-flash`) (the withdrawn `deepseek-v4-flash-0731` SKU was smoke-tested 2026-09-11 and retired 2026-08-27).
- Request to `:8443` without a client cert → HAProxy rejects (`403`) except `GET /health` and `/health_generate`.
- Guest with debug on or wrong initdata role → CDH denies; pod not Ready on `:8443`.
- One GLM replica not Ready → Service has the other; no 8443 traffic to the unready pod.

<a id="follow-up-restore-haproxy-sidecar-kata11649--done"></a>

## Follow-up: restore HAProxy sidecar (kata#11649) — DONE

**Status (2026-09-17): complete.** The sidecar is the **permanent inbound terminator** (decision 2026-09-16) and is rolled on all 10 CC pods on `na-us-oakland-56` — every confidential pod now runs `fetch-certs` init + `haproxy` sidecar + SGLang in the same sandbox, on the `v4.2.0-fix11649-fix16-tx` shim overlay (current since 2026-10-03; the MINIMAL `v4.2.0-fix11649` tag it replaced carried #11649 only).

History: live GLM-1 on `na-us-oakland-56` (2026-08-14) hit QEMU `Duplicate nodes with node-name='drive-5'` after an init/sidecar EROFS unplug — [kata-containers#11649](https://github.com/kata-containers/kata-containers/issues/11649). Root cause (not a parallel-Create race): `wait_for_device_deleted` reset QMP `SO_RCVTIMEO` to **250ms**; the next container's multi-layer EROFS `blockdev-add` then returned `WouldBlock` after QEMU had already created `drive-N`; CreateContainer retry → Duplicate. The sidecar was pulled out until the shim carried a fix.

**The fix is deployed (2026-09-17):** #11649 was reproduced **deterministically on stock kata 4.2.0** (ornith-1 on `am-h200-29`, glm-5-3-flash on `am-h200-23`: `duplicate QEMU block device ID drive-5` CrashLoopBackOff after every `fetch-certs` init unplug), and the MINIMAL `v4.2.0-fix11649` overlay (idempotent `blockdev-add` — pre-check `query_named_block_nodes`, delete orphaned backend, treat duplicate/timeout as success-or-continue, keep a 60s hotplug-sized QMP read timeout) went live on **both** oakland (staging) and michigan-97 (production) on 2026-09-17. Superseded 2026-10-03/13 by `v4.2.0-fix11649-fix16-tx` (adds #13641 + T15/T16 fix classes). With it, the init + sidecar + main-container sequence boots clean; both wedged pods recovered on the fixed shim. Upstream: [#13635](https://github.com/kata-containers/kata-containers/pull/13635) was **closed unmerged** (2026-09-13, issues-only policy); the issue is OPEN with our live-repro comment (2026-09-17) — no fix in flight. Keep the overlay until an official kata-deploy tag contains the fix.

Upstream fix status (as of 2026-09-17):

- [#13216](https://github.com/kata-containers/kata-containers/pull/13216) — hot-unplug block devices (merged 2026-06-22; in 4.0.0+; not sufficient)
- [#11650](https://github.com/kata-containers/kata-containers/pull/11650) — idempotent `blockdev-add` (`Fixes #11649`) — **closed without merge**
- [#13635](https://github.com/kata-containers/kata-containers/pull/13635) — idempotent `blockdev-add` after unplug timeout — **closed unmerged 2026-09-13** (AI-prose policy; all our runtime-rs PRs were withdrawn)

Check:

```bash
gh issue view 11649 --repo kata-containers/kata-containers --json state,closedAt,title
gh pr list --repo kata-containers/kata-containers --search "11649" --state all
```

When #11649, #13641, and T15/T16 are all fixed in the **stock** `containerd-shim-kata-v2` (a kata-deploy tag containing idempotent `blockdev-add`, the off-runtime inotify close, and the missing-task `stop_vm` handling), retire the `v4.2.0-fix11649-fix16-tx` overlay and re-verify a sidecar roll on stock. Until then the overlay is load-bearing for every CC pod with an init container.

<a id="client-facing-attestation--shipped-2026-09-18"></a>

## Client-facing attestation — SHIPPED (2026-09-18)

Clients of `llm.kubetee.ai` can request cryptographic proof that responses
come from a TDX confidential gateway guest. Full client contract (API surface,
nonce semantics, Intel Trust Authority + local DCAP verification paths):
[CLIENT-FACING-ATTESTATION.md](./CLIENT-FACING-ATTESTATION.md); the binding
construction and reference-value contract: [ATTESTATION-SPEC-v1.md](./ATTESTATION-SPEC-v1.md).

- `GET /v1/attestation?nonce=<64 hex>` — fresh TDX quote, the `keyset`/`bindings`/`evidence`/`appraisal` bundle (pod field pins the minting replica). **Since 2026-10-27 the wire default is the v1 JCS-statement binding** (`report_data = SHA-256(statement) + 32 zero bytes`, `report_data_input: "kubetee.attestation.v1"`); the original 2026-09-18 `SHA512(nonce)` construction is the **rollback shape only** (`report_data_input: "sha512(nonce)"`). Rollback = unset `KUBETEE_ATTESTATION_V1` — see [ATTESTATION-SPEC-v1.md §4](./ATTESTATION-SPEC-v1.md).
- `X-KubeTEE-Nonce: <64 hex>` request header on `/v1/chat/completions` —
  response carries `X-KubeTEE-Attestation-Quote` + backend identity headers
  on the same response (streaming and non-streaming).
- Gateway prompt logging is off (`turn_off_message_logging`); the guest runs
  a measured container allowlist (agent policy in `cc_init_data`).

Public-hop RA-TLS (quote bound to the terminator key) remains a later
hardening option on top of this.

<a id="public-kbs-endpoint--shipped-2026-09-18-httpskbskubeteeai"></a>

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
  kernel params at their first CC rollout (done for the michigan image-gen
  backends 2026-09-19: klein + cosmos3 both run the public-endpoint initdata,
  role `image-gen`). The measured agent-policy allowlist in
  `cc_init_data` is per-deployment (same encode-initdata.py flow).

<a id="miner-cluster-backends"></a>

## Miner-cluster backends — SHIPPED (2026-09-19): michigan-97 backends live

LiteLLM stays on the infra cluster (`na-us-oakland-56`). Miner clusters run models (e.g. DSV4-Flash-0731) in TEE and do **not** run LiteLLM. LiteLLM’s `api_base` points at the remote guest over the WAN. Same CoCo pattern as this cut: Trustee issues TLS after attestation; apps speak ordinary mTLS. The miner host, kubelet, and CNI stay untrusted.

**This is no longer hypothetical.** Remote backends run in production on `na-us-michigan-97` (production miner cluster, 7-node RKE2, TDX + PPCIE/native-CC H100/H200, kata 4.2.0). **Ops detail (node names, LB ports, and the per-backend DNS names) is deliberately NOT recorded here** — it lives in the private runbooks (`nim/eastwest/` history + the per-model manifests in the infra repo) and in the live LiteLLM `model_list` DB. The east-west gate is mTLS against the Trustee CA regardless: the URLs are L4 LoadBalancers with per-service certs, not secret-bearing.

| Backend | Placement | Runtime | LiteLLM path |
|---------|-----------|---------|--------------|
| `flux2-klein-4b-sglang-h100` (FLUX.2-klein-4B, SGLang diffusion) | 2× single-GPU native-CC H100 nodes | `kata-qemu-nvidia-gpu-tdx-runtime-rs` | `model_list` row (mode `image`), `/v1/images/generations` |
| `cosmos3-super` (Cosmos3-Super NIM, 8×H200 TP8) | 1 PPCIE H200 node | `kata-qemu-nvidia-gpu-tdx-runtime-rs` | `pass_through_endpoints` `/cosmos3` |
| `minimax-h3` (MiniMax-H3 FL2VA joint video+audio, SGLang diffusion, 8×H200 Ulysses8) | 1 PPCIE H200 node (+1 spare) | `kata-qemu-nvidia-gpu-tdx-runtime-rs` | `model_list` row `minimax/h3` (mode `video_generation`), `/v1/videos` |

Each backend uses a distinct ServiceLB port (one LB port per service per cluster — see the klipper lesson below) and a per-backend DNS name under the cluster's `inference.kubetee.ai` subdomain, resolvable to all node ExternalIPs.

Verified live 2026-09-19 end-to-end through `llm.kubetee.ai`: klein T2I 200 (b64_json delivery), cosmos3 T2I 200 (`b64_image`), mTLS client-cert gate 401s without a key (both paths), 3/3 LiteLLM replicas. Added 2026-09-21: minimax-h3 t2va 200 — 5s/1344×768 MP4 with native stereo audio (`avc1`+`mp4a`) generated in-TEE and delivered through the gateway's `/v1/videos` (create → poll → content), billed at $0.08/s on the row.

**MiniMax-H3 license authorization (2026-09-21).** The MiniMax H3 Community License Agreement excludes the US/EU/UK/KR from its Applicable Territory. MiniMax granted KubeTEE written authorization for US use via the license-application path on the model card. Confirmation received from minimax.io:

> "This email is to confirm that MiniMax authorizes KubeTEE AI LTD to use MiniMax H3 and MiniMax H3 Works, subject to and conditioned upon KubeTEE AI LTD's continued compliance with the commitments and representations set forth in its request email."

The deployment (`nim/minimax-h3-sglang-h200-cc.yaml`) relies on this authorization; if it lapses or is revoked, the pod and its LiteLLM row must be removed. The original email is kept out-of-band (not in git). Contrast: `qwen38-flash-next` was decommissioned 2026-09-04 for lacking an equivalent authorization (Qwen Community License 1.0 MaaS clause).

**klipper port lesson (hit deploying cosmos3):** each LoadBalancer Service claims its port on **every** node via `svclb` pods. Two Services with the same port on the same cluster collide — the second cannot schedule its `svclb` pod on the backend node ("node didn't have free ports") and all traffic on that port silently routes to the **first** service that claimed it. One LB port per service per cluster; firewall the extra ports accordingly. (Actual port assignments live in the private runbooks / live cluster state, not here.)

### Image-generation path (2026-09-19, two-path decision)

Two image models, two API shapes — the deliberate choice ("Option 1"):

- **klein** — OpenAI Images API compatible (`POST /v1/images/generations`, model `black-forest-labs/flux.2-klein-4b`). SGLang speaks this natively.
- **cosmos3** — native NIM API only (`POST /v1/infer`, `model_mode`-discriminated body; **not** OpenAI images/videos schema). Exposed via LiteLLM `pass_through_endpoints` at `https://llm.kubetee.ai/cosmos3`. The mTLS client cert is inherited automatically (passthrough handler uses `get_async_httpx_client()` → process-global `ssl_verify=/certs/ca.pem` → `sitecustomize.py` east-west chain — verified in vendored 1.97.0, still true at 1.103.9).

**klein b64 delivery fix (the row-level `response_format` trap):** SGLang's image protocol defaults `response_format: "url"` for models without a `default_image_response_format()` override (klein's `Flux2KleinSamplingParams` has none) → relative `/v1/images/<id>/content` URL that **404s through LiteLLM** (no such route; content lives in the SGLang pod). Worse, the row carried `additional_drop_params: ["response_format"]`, so even explicit client `response_format` was stripped. Fix (row-only, live `/model/update`): deployment `model: openai/dall-e-2` — the DALL-E 2 dialect whitelists `response_format` (the GPT-image config used for unknown models does not) — plus row default `response_format: b64_json`. SGLang ignores the `model` body field (protocol `Optional`), so the dialect choice is a pure LiteLLM-side param-validation selection. Result: param-less clients get b64 via the row default; explicit requests override; `url` dead-end impossible.

**Why not one endpoint for both:** Cosmos3's `/v1/infer` is a discriminated-union schema (`model_mode: text2image|text2video|image2video|video2video`) that a normal `model_list` row cannot route to, and LiteLLM has no config-driven request/response translation for image providers. Rejected alternatives: translation sidecar in the cosmos3 pod (full OpenAI-compat for `/v1/images`, custom code to maintain), SGLang re-serve of cosmos3 (native `/v1/images`, loses the NIM's pinned super/fp8/tp8 latency profile). If SDK clients that only speak `openai.images.generate()` need cosmos3 later, the sidecar is the upgrade path.

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

4. **Do not publish `:8443` to the open internet** while HAProxy allows unauthenticated `GET /health` and `GET /health_generate` (kubelet probes). Prefer an allowlist (oakland egress) or a WireGuard/IPsec **outer** tunnel, then mTLS inside. Host-level WG/IPsec alone is not enough — it has no per-workload attestation and leaves host↔pod in the clear ([§2](./NEMO-MICROSERVICES-AND-SUBNET-INTEGRATIONS.md#2-attestation-gated-tls-between-services)).

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

### LiteLLM cutover (a miner backend — proven 2026-09-19)

`/model/update` only — no LiteLLM deploy on the miner. Restate every `litellm_params` field. Same client cert, new server cert + passthrough. The klein and cosmos3 rows on michigan-97 are the worked examples (see the table above).

## Later (not this cut)

- Same mTLS pattern on remaining Oakland models (Qwen-class backends when deployed; MiMo already runs it — 2026-09-24).
- Public-hop RA-TLS for clients that attest `llm.kubetee.ai` — the
  **nonce-bound quote endpoint** (Phase 8) covers the client-facing need
  without a custom TLS stack; RA-TLS remains a later option.
- Per-request GPU quotes from inference backends (current contract: boot-time
  attestation + backend identity headers — see Phase 8 scope decisions).
- Short-lived certs with CDH refresh after model load.
- In-guest keygen + `report_data` binding if a future profile requires keys
  that never exist in Trustee.
- Guest-pull + nydus for TDX — only after Phase 2 + guest registry egress.
- NIM containers: reuse Trustee + LiteLLM client; add Operator sidecar or
  `NIM_SSL_MODE=mtls` only if that NIM requires client certs. Not a swap of
  GLM/DSV4 SGLang.

---

# Part II — roadmap (phased work, gaps, adopt / adapt / ignore)

> **For agentic workers:** implement task-by-task from Part II. Steps use
> checkbox (`- [ ]`) syntax. Do not invent cluster work that is not listed.
> Never `kubectl delete --force` on Kata pods.

**Goal (next):** steal the useful CoCo NIM confidential-GPU attestation
practices into KubeTEE’s already-shipped Trustee-issued east-west mTLS — sealed
NGC/HF, HTTPS KBS, gpu0+initdata policy, five-actor ops — without copying SNP
YAML or making guest-pull the TDX default. (Durable Trustee storage — Phase 1 —
is done.) **Cluster:** `--context na-us-oakland-56-direct`.

**Example we steal from (do not copy YAML):**
[NVIDIA confidential NIM deployment](https://confidentialcontainers.org/docs/examples/nvidia-nim-confidential-gpu-attestation/)
(2026-08-15 snapshot).

<a id="trustee-is-live-stale-docs-correction"></a>

## Trustee is live (stale-docs correction)

Root `CLAUDE.md` and `nim/CLAUDE.md` still say Trustee / KBS is **“NOT
deployed”** and that CC pods boot without attestation. **That is false.**

Trustee **is live** on `na-us-oakland-56`:

- Trustee microservices (v0.22.0 vendored chart — `kbs-service` + AS
  `coco-as-grpc` + RVPS), namespace `trustee-operator-system`
  (`fleet-gitops/infrastructure/CLAUDE.md` → `trustee/`). The earlier operator
  v0.21.0 + `KbsConfig` path is retired.
- Attestation: `coco_as_builtin`, Intel-signed TDX DCAP + on-cluster PCCS.
  Attestation policy requires `td_attributes.debug == false`.
- NVIDIA GPU verifier: **NRAS Remote** (chart default Local cannot attest
  B200). Keep the Oakland override. Needs egress to
  `nras.attestation.nvidia.com` and an NRAS license.
- East-west certs are already released through this KBS (`kbs:///default/eastwest-*`).
- Pin Trustee to the CoCo / Kata pair we run. **No `latest`.**

Remaining Trustee gaps (not “deploy Trustee”):

| Gap | Live today | Steal next |
|-----|------------|------------|
| Transport | `http://kbs-service.trustee-operator-system.svc.cluster.local:8080` — no `kbs_cert` in initdata | HTTPS KBS + cert in measured `aa.toml` / `cdh.toml` |
| Storage | **Durable** — LocalFs on `longhorn-v2` PVCs (`trustee-kbs-data`, `trustee-as-data`, `trustee-rvps-data`), since 2026-09-18 | (done — Postgres/Valkey only if HA is needed) |
| Resource policy | **LIVE (2026-09-18):** `nim/eastwest/resource-policy.rego` — cpu0 affirming + path×role (incl. `proxy-*` for alpha-recycler); attestation policy seeded as `default_cpu`. Wrong-role guests get attest 200 + resource 401 | gpu0 + initdata digest once RVPS has VBIOS/driver refs |
| Runtime keys | NGC/HF still host Kubernetes Secrets | Vault sealed secrets → `kbs:///default/…` so etcd never holds runtime keys |
| Ops model | One operator persona in practice | Five-actor split (Phase 5) |

Do not “fix” those CLAUDE files here. Call the lie here so agents stop
rediscovering Trustee.

<a id="phase-0--already-built-do-not-redo"></a>

## Phase 0 — already built (do not redo)

Trustee-issued east-west identity shipped 2026-08-15. Details live in
[Part I](#part-i--live-spec-what-is-deployed). This is what we **already built**;
the steal items below are what we do **next**.

- [x] Trustee + `coco_as_builtin` on Oakland
- [x] NRAS Remote override (B200)
- [x] Local CA + leaf certs seeded with `kbs-client` (`nim/eastwest/gen-certs.sh`)
- [x] Initdata roles `litellm` vs `nim-terminator` (`nim/eastwest/initdata-*.toml`)
- [x] `fetch-certs.sh` → `/certs` via CDH
- [x] GLM + DSV4 inbound HAProxy `:8443` (`verify required` except kubelet
      `GET /health` and `GET /health_generate`)
- [x] Services expose `:8443` only; SGLang binds `127.0.0.1:8000`
- [x] LiteLLM outbound mTLS via `sitecustomize.py` (httpx 0.28 ignores
      `ssl_certificate`); `api_base` is `https://<svc>:8443/v1`
- [x] Gateway chat **200** for `z-ai/glm-5.2` and
      `deepseek/deepseek-v4.1-flash` (the `deepseek-v4-flash-0731` SKU was
      withdrawn 2026-08-27 and its backend deleted; V4.1-Flash live 2026-09-21)
- [x] `nim/eastwest/resource-policy.rego` (cpu0 + path×role) — **LIVE
      since 2026-09-18** (seeded via the KBS admin API, replacing `default.rego`)
- [x] Durable Trustee storage (Phase 1, 2026-09-18)
- [x] HAProxy sidecar permanent terminator, rolled on all 10 CC pods (2026-09-17)

<a id="file-map"></a>

## File map

| Path | Role |
|------|------|
| `nim/eastwest/gen-certs.sh` | Local CA + leaf certs. Output stays on the operator machine; never commit. |
| `nim/eastwest/haproxy-inbound.cfg` | GLM/DSV4 guest: `:8443` mTLS → `127.0.0.1:8000` |
| `nim/eastwest/haproxy-outbound.cfg` | LiteLLM loopback (sidecar path; live outbound is sitecustomize) |
| `nim/eastwest/fetch-certs.sh` | CDH fetch → `/certs/*.pem` |
| `nim/eastwest/initdata-litellm.toml` | `role = "litellm"` + HTTP KBS URL (no `kbs_cert` yet) |
| `nim/eastwest/initdata-nim.toml` / `initdata-glm.toml` / `initdata-dsv4.toml` | `role = "nim-terminator"` + HTTP KBS URL |
| `nim/eastwest/encode-initdata.py` | Assembles the initdata TOML → gzip+base64 `cc_init_data` |
| `nim/eastwest/resource-policy.rego` | **LIVE** KBS policy (seeded 2026-09-18 via admin API): cpu0 affirming + path×role incl. `proxy-*` for the alpha-recycler. |
| `nim/eastwest/kubetee_attestation.py` | Client-facing attestation module (Phase 8): `GET /v1/attestation` + inline `X-KubeTEE-Nonce` evidence. Embedded in the litellm `eastwest-fetch-certs` ConfigMap. |
| `nim/eastwest/kubetee_binding.py` | The `kubetee.attestation.v1` JCS-statement construction (server side) |
| `nim/eastwest/kubetee_ear.py` / `kubetee_eastwest.py` / `kubetee_bootstrap.py` | Boot-time Trustee EAR mint (`appraisal`) + east-west key fetch |
| `nim/eastwest/release-litellm.sh` | The four-carrier release sync (image tag, rego allowlist, initdata, fleet values) |
| `nim/eastwest/RELEASE-RUNBOOK.md` | The gateway release runbook |
| `kubetee-subnet/docs/CLIENT-FACING-ATTESTATION.md` | Client guide (Phase 8): API surface, nonce semantics, ITA + local DCAP verification paths. |
| `kubetee-subnet/docs/ATTESTATION-SPEC-v1.md` | The partner contract: binding construction + reference-value publication |
| `nim/glm-5-2-fp8-sglang-h200-cc.yaml` | GLM STS + Service `:8443` (michigan-97; replaced `nim/glm-5-2-nvfp4-sglang-cc.yaml`, deleted 2026-10-13) |
| `nim/deepseek-v4-1-flash-sglang-h200-cc.yaml` | DSV41 STS + Service `:8443` (replaced the withdrawn `deepseek-v4-flash-0731` manifest, deleted) |
| `fleet-gitops/infrastructure/litellm/staging/values-litellm-na-us-oakland-56.yaml` | LiteLLM TDX overlay (LE public hop + east-west client cert) |
| `fleet-gitops/infrastructure/trustee/` | Trustee chart v0.22.0 + volumes (Fleet). Manual `kbs-auth-public-key`. |
| Live Trustee ConfigMaps / KBS resources | Policy + `set-resource`. No K8s Secrets for east-west private keys. |

<a id="hard-constraints"></a>

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
- Do not enable CoCo `kata-as-coco-runtime` (duplicates kata-deploy RuntimeClasses).
- Do not treat the CoCo tutorial as encrypted-weights. Its `/opt/nim/.cache`
  is a plaintext `emptyDir`.
- Hopper `cc.mode=off` is a PPCIE trap — not a baseline we run.

<a id="steal-from-coco-nim-attestation-example-2026-08-15"></a>

## Steal from CoCo NIM attestation example (2026-08-15)

Source:
[confidentialcontainers.org — NVIDIA confidential NIM deployment](https://confidentialcontainers.org/docs/examples/nvidia-nim-confidential-gpu-attestation/).

The tutorial is a single-node AMD SEV-SNP + 1 GPU + Llama 3.1 8B NIM Pod +
Docker Compose Trustee walkthrough. We steal **practices**, not YAML.

### Adopt (next work — not already done)

| # | Practice | Why it matters here | Phase |
|---|----------|---------------------|-------|
| 1 | **Sealed secrets** for NGC/HF (later LUKS keys) — vault sealed secret pointing at `kbs:///default/ngc-api-key/instruct` (and HF equivalent). Kubernetes sees only the sealed blob; CDH unseals inside the guest. | etcd never holds runtime keys. Today NGC/HF are host Secrets. | 4 |
| 2 | **KBS HTTPS + cert in measured initdata** (`aa.toml` / `cdh.toml` `kbs_cert` / `cert`). | Live GLM/LiteLLM still `http://kbs-service…:8080` with no cert — host-sniff risk on miner-WAN. Part I already blocks remote guests until this exists. | 2 |
| 3 | **Durable Trustee storage** — not Memory `emptyDir`. | **DONE 2026-09-18** (LocalFs `longhorn-v2` PVCs). Postgres/Valkey only if HA is needed. | 1 |
| 4 | **gpu0 + initdata in resource policy** once RVPS has VBIOS/driver refs. Tutorial requires `cpu0` and `gpu0` affirming plus pinned initdata digest. | Today gpu0-affirming **denies** after attest 200. Live is the KubeTEE `resource-policy.rego` (3a, 2026-09-18): cpu0 + path×role only. | 3 |
| 5 | **Five-actor split** (Outlook). Tutorial’s single persona is not our model. | Cluster team ≠ Trustee operator ≠ KBS admin ≠ release pipeline ≠ workload operator. | 5 |
| 6 | Keep **NRAS Remote**. | Local cannot attest B200. Chart default Local must stay overridden on Oakland. | (done — do not regress) |

### Adapt (do not copy YAML)

| Tutorial | KubeTEE |
|----------|---------|
| SNP `HOST_DATA` / `sev-snp-measure` / live QEMU scrape | TDX MRTD/RTMR + initdata claims. We already bind `role` in initdata (`litellm` vs `nim-terminator`). Pin digest in policy when RVPS is filled — do not scrape QEMU on the GPU node. |
| 1 GPU SNP (`nvidia.com/pgpu: "1"`, `kata-qemu-nvidia-gpu-snp`) | 8 GPU TDX + PPCIE + NVSwitch. Hopper: `nvidia.com/nvswitch: "4"`, `cc.mode=ppcie`. Blackwell: `cc.mode=on`. Runtime: `kata-qemu-nvidia-gpu-tdx-runtime-rs` only. |
| Guest-pull block PV (`/dev/trusted_store`, loop `/tmp`) | **kata-direct** for weights. Later CDH LUKS ([pamanseau/kubetee-ai#1](https://github.com/pamanseau/kubetee-ai/issues/1)). Agent `cdh_secure_mount` still hardcodes `sourceType: "empty"` and omits `key` — LUKS is **not** done. |
| Raw NIM Pod + `genpolicy` on the worker | NIMService / SGLang StatefulSet + `fetch-certs` + HAProxy `:8443`. LiteLLM is Helm (Fleet), not a Pod manifest. |
| Docker Compose Trustee on the GPU node | Fleet chart (already). Pin to the CoCo/Kata pair; no `latest`. Do not run Trustee on the workload node. |
| Bitnami Postgres subchart (if we pick SQL) | CloudNativePG is the KubeTEE Postgres standard. Do not add Bitnami. |
| Single NGC key for pull + runtime | Split: host `imagePullSecret` (CRI, host-pull/erofs) vs sealed runtime key in KBS (guest). |

### Do not copy from the tutorial

| Ignore | Why |
|--------|-----|
| `kata-qemu-nvidia-gpu-snp`, live QEMU scrape, `snphost`, `sev-snp-measure` | We are TDX + runtime-rs, not SNP. |
| Docker Compose Trustee on the GPU node | Trust separation is the point. Oakland already has the Fleet Trustee. |
| Loop `/tmp` PVs / `local-storage` | We have `kata-direct` + Longhorn V2. |
| `cc.mode=off` baseline on Hopper | PPCIE trap — label-only CC→non-CC does not clear the PPCIE register. |
| Enabling CoCo `kata-as-coco-runtime` | Duplicates kata-deploy RuntimeClasses. Keep `enabled: false`. |
| Guest-pull as the default TDX image path | Needs HTTPS KBS + guest registry egress. **erofs + host-pull + `IfNotPresent`** is the no-KBS-egress path. Keep nydus installed, do not select it for TDX shims until Phase 2 + egress exist. |
| Treating the tutorial as encrypted-weights | `/opt/nim/.cache` is a plaintext `emptyDir`. Encrypted weights are issue #1 + agent key plumbing — not this example. |
| Replacing SGLang with Llama 3.1 8B NIM | First-cut models stay GLM + DSV4 SGLang. NIM containers are a later reuse of Trustee + LiteLLM, not a swap. |

<a id="phase-1-durable-trustee-storage"></a>

## Phase 1: Durable Trustee storage — DONE (2026-09-18)

**Status:** **DONE** — Trustee migrated to the **v0.22.0 vendored Helm chart**
(microservices: `kbs-service` + AS `coco-as-grpc` + RVPS) with **LocalFs on
`longhorn-v2` PVCs** (`trustee-kbs-data`, `trustee-as-data`,
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
guests (wedge-prone GPU recreates) or an ExternalName bridge. Bundle it
with the next initdata-changing rollout.

**Why it mattered:** every later phase (HTTPS, policy, sealed NGC) writes KBS
state. Wiping that on a rollout is an outage.

**Chart knobs** (for a future HA backend, if ever needed): 
`storageBackend.localFs.persistence.kbs` / `.as` / `.rvps` — PVC claim; empty =
`emptyDir` · `storageBackend.type: Postgres` or `sessionStorageType: Redis`
(Valkey). Oakland: `longhorn-v2` / `longhorn-v2-ha`. If SQL, **CloudNativePG**,
not Bitnami. **Do not** share `redis-litellm`.

Do not start Phase 2 until a Trustee roll does **not** require re-seed —
**that condition holds since 2026-09-18**.

<a id="phase-2-kbs-https--cert-in-measured-initdata"></a>

## Phase 2: KBS HTTPS + cert in measured initdata — NOT DONE

**Status:** not done. Live `aa.toml` / `cdh.toml` (see
`nim/eastwest/initdata-litellm.toml`, `initdata-glm.toml`,
`initdata-dsv4.toml`):

```toml
url = "http://kbs-service.trustee-operator-system.svc.cluster.local:8080"
```

No `cert` / `kbs_cert`. `insecure_http = true` on the operator sample
`kbs-config.toml`.

**Why now:** on Oakland this is a host-sniff risk. Across a miner WAN it is
fatal (Miner-cluster backends, Part I). Close this **before** the first
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

<a id="phase-3-resource-policy-pathrole--cpu0-then-gpu0"></a>

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
*(Note 2026-10-27: the client-facing `evidence.vm_config.agent_policy_claims`
now carries those claims on the gateway's attestation bundle — but the
Trustee **EAR** still does not; the resource-policy gate is unaffected.)*

- Live attestation policy: first-cut relaxed (Intel-signed quote + debug off
  + TCB UpToDate; RVMS pins commented out, restore when RVPS is filled).
- 3b sketch (gpu0 + initdata digest) unchanged — blocked on RVPS.

Tutorial policy (SNP) required `cpu0` + `gpu0` affirming **and**
`annotated_evidence["init_data"] == expected_digest`. We adapt that to TDX
claims, not `HOST_DATA`.

### 3a — path×role + cpu0 (DONE)

- [x] **Step 1: Dump one token** (done 2026-09-18). AS `RUST_LOG=debug` for
      one roll (`debug!(ear =? ear, "Unsigned EAR Token")` in
      `ear_token/broker.rs`), one-off alpha-recycler probe Job with the real
      CronJob's `cc_init_data`. Confirmed:
      `submods.cpu0["ear.veraison.annotated-evidence"].init_data_claims.role`
      = `"alpha-recycler"` — matches the draft path exactly. Single cpu0
      submod on CPU-TDX guests (no GPU submods). Also confirmed the seeded
      `default` policy was inert (broker resolves `default_cpu`).
- [x] **Step 2: Apply** (done 2026-09-18, admin API — the chart stores
      policies in the PVC-backed KV store, no ConfigMap mount): attestation
      policy seeded as **`default_cpu`**; resource policy =
      `nim/eastwest/resource-policy.rego` + the `proxy-staking` /
      `proxy-nonfungible` paths. Both survive AS restarts (`overwrite: false`).
- [x] **Step 3: Prove** (done 2026-09-18; see the verification table above).

### 3b — gpu0 + initdata digest (after RVPS) — BLOCKED

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

<a id="phase-4-sealed-ngchf-later-luks-keys"></a>

## Phase 4: Sealed NGC/HF (later LUKS keys) — NOT DONE

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

<a id="phase-5-five-actor-split"></a>

## Phase 5: Five-actor split — NOT DONE

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
      KubeTEE KBS (Part I). A miner-local Trustee would make the miner the CA.

An organization can combine roles; each responsibility still needs a named
owner.

<a id="phase-6-restore-haproxy-sidecar--complete-2026-09-17"></a>

## Phase 6: Restore HAProxy sidecar — COMPLETE (2026-09-17)

**Status: COMPLETE.** Full evidence, the kata#11649 root cause, upstream fix
status, and the sidecar's permanent-terminator decision are in
[Part I → Follow-up: restore HAProxy sidecar](#follow-up-restore-haproxy-sidecar-kata11649--done)
and [Part I → NIM guest (inbound)](#nim-guest-inbound) (in-process TLS
rejection, image + resource standards, canary record).

Roll record:

- [x] `v4.2.0-fix11649` overlay on **every CC node of both clusters** (2026-09-17;
      oakland 10/10 + michigan 7/7) — init + sidecar rolls no longer hit
      `Duplicate nodes with node-name='drive-N'`. Superseded 2026-10-03/13 by
      `v4.2.0-fix11649-fix16-tx`.
- [x] Sidecar + `fetch-certs` init restored; in-process fetch/HAProxy dropped
      from `start-sglang.sh`.
- [x] Partition dropped to 0 (all 10 live CC pods).
- [x] Sidecar image+config roll canary-verified (2026-09-17, ornith pod-1).
- [x] Full rollout: **all 10 CC pods** on `na-us-oakland-56`.

This is independent of sealed NGC. Do not block Phase 2 on it.

<a id="phase-7-miner-cluster-backends-blocked"></a>

## Phase 7: Miner-cluster backends — SHIPPED (2026-09-19)

**Status: SHIPPED** — michigan-97 backends live; see
[Part I → Miner-cluster backends](#miner-cluster-backends) (the worked
example, the klipper port lesson, the image-generation two-path decision, and
the MiniMax-H3 authorization).

Standing rule from that work: **close KBS-over-HTTP (Phase 2) before the next
remote cluster** — CDH fetching `eastwest-nim/tls.key` over plaintext HTTP is
fatal across a miner WAN.

<a id="phase-8-client-facing-attestation-of-inference--complete-2026-09-18"></a>

## Phase 8: Client-facing attestation of inference — COMPLETE (2026-09-18)

**Client contract:** [CLIENT-FACING-ATTESTATION.md](./CLIENT-FACING-ATTESTATION.md)
(full guide with ITA + local verification paths); binding + reference-value
contract: [ATTESTATION-SPEC-v1.md](./ATTESTATION-SPEC-v1.md).

What shipped (all verified live 2026-09-18 on the 3-replica gateway, plus the
2026-10-27 v1 bundle work):

- [x] **Prompt logging off** — `turn_off_message_logging: true`
- [x] **Kata debug-off verified** — AS policy + live EAR `td_attributes.debug` check
- [x] **Trustee resource policy live** — path×role + cpu0 (Phase 3a)
- [x] **Measured agent-policy container allowlist** — pause + fetch-certs + litellm
      images/UIDs in `policy-litellm.rego`; `agent_policy_claims` extraction fixed
- [x] **In-guest attestation REST API** — `agent.guest_components_rest_api=all`
- [x] **`GET /v1/attestation?nonce=<64 hex>`** — fresh TDX quote, JSON payload,
      `pod` replica pinning. Verified 2026-09-18 (legacy `SHA512(nonce)` at
      offset 568); **re-verified 2026-10-27 on the v1 JCS-statement binding**.
- [x] **Inline evidence** — `X-KubeTEE-Nonce` → `X-KubeTEE-Attestation-Quote` +
      backend identity headers on the SAME response (streaming + non-streaming)
- [x] **v1 bundle + `appraisal` + `vm_config`** (2026-10-27) — `keyset` /
      `bindings` / `evidence` / `appraisal` live; boot-time Trustee EAR minted;
      `evidence.vm_config` carries role/files/`initdata_sha384` ==
      quote MRCONFIGID. 30 module unit tests.
- [x] **26 unit tests** for the original module (mocked httpx/litellm)

Implementation notes for future phases:

- The callback hook is `async_post_call_response_headers_hook` — NOT `async_post_call_success_hook`. The latter runs AFTER the streaming `StreamingResponse` is constructed (headers frozen); the headers hook fires before freeze on both paths.
- **Nonce/binding rule (corrected 2026-10-27):** the live v1 wire shape binds the
  JCS statement (nonce + keyset digest + purpose) into `REPORTDATA`; the older
  `SHA512(nonce)` rule is the rollback shape only. For Intel Trust Authority:
  ITA appraises the **quote** (crypto/TCB/debug) and the relying party verifies
  the **binding** itself — ITA's `tdx_report_data` check is a cumulative SHA-512
  and cannot match the v1 construction. Do **not** pass the raw nonce as
  `runtime_data` expecting it to match. (The 2026-09-18 "ITA re-hashes and
  matches REPORTDATA" note was wrong and is retracted.)
- `kubectl exec` into the gateway guest is **denied by the agent policy** — test via port-forward or a curl pod.
- Scope decisions (2026-09-17/18): gateway mints the per-request quote (cheap, CPU TDX); backends stay boot-time attested (per-request GPU quotes are a bigger lift — revisit if a profile requires them).

<a id="part-iistatus-table"></a>

## Status table

| Item | Phase | Status |
|------|-------|--------|
| Trustee-issued east-west mTLS | 0 | **Shipped** — Part I |
| Durable KBS store | 1 | **Done (2026-09-18)** — v0.22.0 chart, LocalFs `longhorn-v2` PVCs, roll-survival verified |
| HTTPS KBS + `kbs_cert` in initdata | 2 | **Not done** (HTTP, no cert) — blocks the next remote cluster |
| path×role + cpu0 policy | 3a | **LIVE (2026-09-18)** — `nim/eastwest/resource-policy.rego` seeded; positive/negative probes verified |
| gpu0 + initdata digest | 3b | **Blocked** on RVPS VBIOS/driver |
| Sealed NGC/HF | 4 | **Not done** |
| LUKS / encrypted weights | 4 / #1 | **Not done** — agent hardcodes `empty` |
| Five-actor ops | 5 | **Not done** |
| HAProxy sidecar restore | 6 | **COMPLETE (2026-09-17)** — all 10 CC pods |
| Client-facing attestation | 8 | **COMPLETE (2026-09-18)** + v1 bundle/appraisal/vm_config (2026-10-27) |
| Miner backends | 7 | **Shipped (2026-09-19)** — michigan-97 backends live |
| Reference-value publication (`/.well-known/…`) | — | **Publication in progress** (schema + contract published in `ATTESTATION-SPEC-v1.md`; endpoints not yet served) |
| NRAS Remote | — | **Shipped** — do not revert |
| Guest-pull as TDX default | — | **Ignored** |
| SNP YAML / Compose Trustee | — | **Ignored** |
