# Attested mTLS between the KubeTEE gateway and model backends

**Current deployment:** an **AMD SEV-SNP** LiteLLM
`1.110.2-kubetee.8` gateway on the Subnet-Owner-controlled `kubetee` cluster,
calling **Intel TDX + NVIDIA-CC** model guests on external-miner clusters.
The gateway uses `kata-qemu-snp-runtime-rs`; the GPU backends use
`kata-qemu-nvidia-gpu-tdx-runtime-rs`.

This document describes the serving topology and its evidence boundaries.
The public request contract is
[ATTESTATION-SPEC-v1.md](./ATTESTATION-SPEC-v1.md); its endpoint guide is
[CLIENT-FACING-ATTESTATION.md](./CLIENT-FACING-ATTESTATION.md).

---

## 1. Serving topology

```text
Caller
  │ HTTPS, llm.kubetee.ai
  │ Cloudflare DNS-only; Gateway API TLS passthrough
  ▼
Traefik listener :8443
  │ no payload decryption
  ▼
LiteLLM :4000 inside SNP Kata guest
  │ fresh nonce-bound SNP evidence + TLS possession
  │ mTLS using gateway leaf + east-west CA
  ▼
Remote public mTLS endpoint inside backend Kata CVM
  │ verified gateway client identity
  │
  ├─► Granian frontend (new standard): strict mTLS + HTTP/2
  │   terminated by the measured SGLang process on :8443;
  │   separate loopback health listener on :8000
  │
  └─► HAProxy :8443 (legacy frontend, migrating): mTLS terminated
      by in-CVM HAProxy → SGLang on 127.0.0.1:8000
```

The application payloads are decrypted by LiteLLM inside its measured
guest, not by Cloudflare or the Traefik listener. They are encrypted again
on the backend mTLS hop and terminate in the same confidential VM as the
inference engine.

| Hop | Current implementation | Evidence contract |
|---|---|---|
| Client → gateway | Three SNP gateway replicas; immutable `1.110.2-kubetee.1` image and measured guest policy; Traefik passes TLS to LiteLLM. | Fresh AMD SNP report bound to the request statement plus TLS possession. The signed gateway measurement registry is public. |
| Gateway → backend | Trustee-gated mTLS to the backend's public DNS hostname. The measured inference process (Granian frontend) or an in-CVM HAProxy (legacy frontend) presents the server identity and checks the gateway client certificate. | Backend platform appraisal occurs at boot before its identity is released. No fresh per-request GPU report is supplied to the client today. |

The SNP gateway and TDX backend measurements are independent. Neither type
of report proves the other hop; an independent verifier must use the right
native evidence for each platform.

## 2. Current backend routes

| Public model family | Backend placement | Gateway URL |
|---|---|---|
| `moonshotai/kimi-k3.1-pro` | External-miner TDX B300-CC guest (Granian frontend) | `https://kimi-k3-1-pro39.eu-lu-luxembourg-133.inference.kubetee.ai:443/v1` |
| `xiaomi/mimo-v2.6-pro` | External-miner TDX B300-CC guest (Granian frontend) | `https://mimo-v2-6-pro.eu-lu-luxembourg-133.inference.kubetee.ai/v1` |
| `xiaomi/mimo-v2.6-pro` (second row) | External-miner TDX B200-CC guest (Granian frontend) | `https://mimo-v2-6-pro.na-us-dallas-132.inference.kubetee.ai/v1` |

The backend hostname, certificate SAN, serving certificate and appraised
workload identity must agree. A public hostname resolving successfully or
returning HTTP 200 does not itself prove confidential-compute custody.

Each backend uses its measured CDH fetch configuration and a role-specific
server leaf. The gateway uses its approved outbound identity; it does not
ask an operator or a miner-local certificate authority to accept arbitrary
non-confidential workloads.

## 3. Trustee and key release

CoCo Trustee v0.23.0 appraises platform evidence and releases resources via
CDH only after its configured policy and role/path checks allow them.
KBS exposes the HTTPS endpoint `https://kbs.kubetee.ai`. Its public surface
does not expose the administrative API; protected administration and
Trustee storage are explicitly trusted.

The gateway and each backend identify themselves through native guest
attestation and measured InitData. A role label without approved guest
composition is not authorization. The two sides obtain only the resources
required for their role, such as:

```text
Gateway:   default/eastwest-ca/ca.pem
           default/eastwest-litellm/{tls.crt,tls.key}
           default/litellm-confidential/{tls.crt,tls.key}
Backends:  default/eastwest-ca/ca.pem
           default/eastwest-nim-<approved-backend>/{tls.crt,tls.key}
           default/hf-token/token
```

The public CA certificate can be verified independently. Private-key and
protected-resource content must never be printed, logged or committed.

Trustee and KBS follow standard upstream confidential-containers behavior.
The workload validates its own measured InitData and scoped resource paths
rather than relying on default-allow key delivery or legacy SEV
compatibility. AMD gateway guests use SEV-SNP; legacy SEV/SEV-ES is not an
acceptable substitute.

## 4. Key custody in the deployed pods

| Identity | Delivery and storage | Scope of the boundary |
|---|---|---|
| `llm.kubetee.ai` TLS certificate/key | The measured gateway bootstrap reads `default/litellm-confidential/{tls.crt,tls.key}` over CDH loopback `127.0.0.1:8006`, writing them to `/etc/tls` on **Memory `emptyDir`** with restricted permissions. LiteLLM receives the corresponding TLS file arguments. | The identity is loaded after appraisal on each start and can be reusable across starts. `fresh_certificate_per_boot: true` in the registry describes retrieval, not a newly generated per-boot keypair. This is not direct mounting of a conventional K8s TLS Secret. |
| Gateway mTLS client identity | The image-local `kubetee_bootstrap` retrieves the CA and client certificate before normal LiteLLM startup into container-local `/run/kubetee-eastwest`, failing closed if unavailable. Production does not declare a shared host-visible volume for this directory. | The key is confined to container guest storage after attested release. There is no claim that it must have been generated inside this particular VM. |
| Backend mTLS server identity | A measured init container fetches its resources through in-guest CDH into `/certs` on `emptyDir: {}`. On the Granian frontend the measured SGLang process reads that material and terminates mTLS directly; on the legacy frontend an in-CVM HAProxy container reads the same `/certs` and fronts loopback SGLang. | This is disk-backed storage **inside the CVM**, not Memory tmpfs and not a direct mount of an ordinary K8s TLS Secret. |
| Offline measurement-signing key | Kept outside the gateway; its Ed25519 public key is separately published at [`kubetee.ai/.well-known/tee-measurements-signing-key-2026.json`](https://kubetee.ai/.well-known/tee-measurements-signing-key-2026.json). | Its private counterpart is not delivered to a serving pod. This is independent of the registry-signature, SNP-report-signature and TLS-possession operations. |

All three gateway replicas use the exact image pinned in the signed registry.
The measured agent policy denies `ExecProcessRequest`. This strengthens
custody by rejecting ordinary `kubectl exec` access; it does not prove every
possible kernel or privileged management read path is absent. Trustee's
key-release escrow and privileged administration also remain explicit trust
boundaries rather than a zero-operator-trust mechanism.

## 5. How the two workloads consume their keys

### Public gateway

The current release's callback and bootstrap code is baked into the measured
image, not injected from an unmeasured ConfigMap. It obtains the gateway's
client identity before handing execution to normal LiteLLM startup.

```text
LiteLLM configured east-west ssl_verify CA
  → scoped measured sitecustomize.py SSLContext hook
  → /run/kubetee-eastwest/ca.pem matches exactly
  → load /run/kubetee-eastwest/{tls.crt,tls.key}
  → LiteLLM backend HTTPS request carries the client certificate
```

The context hook is explicitly keyed to the east-west CA so the gateway
client identity is not attached to public HTTPS upstreams. Failure to load
an approved east-west identity fails startup rather than reverting to an
unauthenticated backend path.

### Model backend

On the Granian frontend (the 2026-11-23 standard, now the **only** frontend in
deployed backends — MiMo on Dallas and Luxembourg and the K3.1-Pro B300 cells),
the measured SGLang process itself binds `:8443` and enforces strict
client-certificate mTLS with HTTP/2 — no transport proxy sits in the trust path,
and the mTLS TLS state and serving key live in the same measured process as the
inference engine. Kubelet probes use a separate loopback-only HTTP listener
(`/health`, `/health_generate` only; all other routes return 404) so probe
traffic never traverses the mTLS surface.

On the legacy HAProxy frontend (one HAProxy container + SGLang in one CVM — now
retained only in the not-yet-migrated K3.1 cell, `0/0` today), HAProxy binds
`:8443` and performs certificate verification before allowing inference
requests, fronting loopback SGLang on `127.0.0.1:8000`. Its health-check
exception is limited to probe paths; other API traffic requires a verified
client identity.

Both frontends keep the serving image's native protocol behind the same
measured mTLS boundary. The server certificate is built inside the guest from
CDH-delivered material and is not read from a host filesystem mount.

## 6. Client-visible evidence

A `GET /v1/attestation?nonce=<64hex>` request returns a complete gateway
bundle; `X-KubeTEE-Nonce` adds inline evidence to a chat response.

Gateway evidence includes:

- native CoCo SNP report and certificate chain;
- exact `kubetee.attestation.v1` statement and keyset;
- launch and InitData reference values in the independently signed registry;
- nonce signature made with the TLS possession key;
- optional boot Trustee appraisal.

Backend headers report `X-KubeTEE-Backend-Attested` as one of three **evidence
boundary** labels: `boot-time (Trustee EAR; east-west mTLS)` (freshness gap /
degraded), `hardware-evidence (shared epoch cache)` (the default cached epoch
path), or `hardware-evidence (fresh cpu+gpu, nonce-bound)` (a fresh mint on
`X-KubeTEE-Nonce`). The label is the **evidence boundary**, not an assertion
that model-output bytes are signed. Fresh SNP evidence proves the live
client-to-gateway hop; backend evidence establishes a separate, different
evidence chain.

The deployed per-backend fresh-evidence contract (Phase 4b + release `.8`) is:
on `X-KubeTEE-Nonce: <64-hex>`, the routed backend mints a **fresh composite** —
one CPU TDX quote (caller nonce bound in `report_data`) plus 8× GPU SPDM
`GET_MEASUREMENTS` NVAT frames (each echoing the nonce) — surfacing a compact
`gpu` summary + `evidence_digest` in the relayed envelope and the full 8-GPU
set on the backend's own east-west-mTLS evidence service. The mint is
rate-limited to 1 per minute per API key with a self-documenting `429` beyond.
`X-KubeTEE-Proof` (unlimited) attaches the routed pod's cached evidence plus a
gateway signature binding it to the response. Ordinary completions ride the
shared cached epoch (one hardware quote per ≤5 min per replica). A measurement
mismatch trips the circuit breaker (fail-closed, sticky: new verified routing is
blocked client-side while KubeTEE alerts operators and never auto-kills a
serving pod).

`signing_keys: []` is intentional in this deployment. The public
measurement-signing key is obtained independently from the registry's
`key_url`.

## 7. Current verification and remaining gaps

The released source is
`KubeTEE-AI/litellm@e763bb83ebf6f9f711199a58760235911bb1d6e1`,
produced by GitHub Actions [run `45909231309`](https://github.com/KubeTEE-AI/litellm/actions/runs/45909231309),
with image
`ghcr.io/kubetee-ai/litellm-database:1.110.2-kubetee.8@sha256:5d6c4c88bbca792909a91f14df4dde3fbc4e132e530adfc88e8514d3a8400fed`.

The signed measurement record identifies the exact guest launch measurement,
InitData `HOST_DATA` derivation, images, firmware and kernel. All three
captured gateway replicas were checked using native AMD verification.
Independent SNP consumer work (AMD SEV-SNP appraisal of the current
`kubetee.attestation.v2` binding) is under review in
[SayGM/gm-miner PR #430](https://github.com/taostat/gm-miner/pull/430) (its
predecessor #419 was closed unmerged and superseded); that pull request is not
a claim of an already-merged worker migration.

Acceptance still requires native client verification rather than only a
chat 200. Remaining hardening includes fresh in-guest-generated serving
identities (the zero-operator step) and byte-reproducible builds. The
per-backend fresh-evidence contract is deployed (Phase 4b + release `.8`).

**Registry anti-rollback (Phase 6 §3.2) is implemented and enforced** in the
gateway matcher and the reference verifier (chain + monotonic `version` floor);
the first chained registry publish is pending (see
[ATTESTATION-SPEC-v1.md §5](./ATTESTATION-SPEC-v1.md) "Registry anti-rollback").
The general rule it embodies — *a verifier never accepts material older than the
newest it has already trusted* — is the same one this doc recommends for the
east-west mesh-CA rotation in §3: the measurement-registry floor delivers that
for measurement approval today, and a chained mesh-CA history would deliver it
for per-boot identities once §3 is built.
Reproducible-build equivalence is published source-commit → CI-run →
image-digest provenance today; bit-for-bit reproducibility is not claimed.
