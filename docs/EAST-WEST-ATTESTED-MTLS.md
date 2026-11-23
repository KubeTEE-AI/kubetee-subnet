# Attested mTLS between the KubeTEE gateway and model backends

**Current deployment:** an **AMD SEV-SNP** LiteLLM
`1.110.2-kubetee.1` gateway on the Subnet-Owner-controlled `kubetee` cluster,
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
| `moonshotai/kimi-k3.1-pro` | External-miner TDX B300-CC guest | `https://kimi-k3-1-pro.eu-lu-luxembourg-133.inference.kubetee.ai:443/v1` |
| `xiaomi/mimo-v2.6-pro` | External-miner TDX B200-CC guest | `https://mimo-v2-6-pro.na-us-dallas-132.inference.kubetee.ai/v1` |

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

### Model backend

On the Granian frontend (the 2026-11-23 standard), the measured SGLang
process itself binds `:8443` and enforces strict client-certificate mTLS with
HTTP/2 — no transport proxy sits in the trust path, and the mTLS TLS state and
serving key live in the same measured process as the inference engine. Kubelet
probes use a separate loopback-only HTTP listener (`/health`,
`/health_generate` only; all other routes return 404) so probe traffic never
traverses the mTLS surface.

On the legacy HAProxy frontend (still serving MiMo on Dallas and the K3.1
production cell as their images rebuild), HAProxy and the inference process
are containers in one confidential VM: they are not separate VMs. SGLang
listens on `127.0.0.1:8000`; HAProxy binds `:8443` and performs certificate
verification before allowing inference requests. Its health-check exception
is limited to probe paths; other API traffic requires a verified client
identity.

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

Backend headers report `X-KubeTEE-Backend-Attested` as
`boot-time (Trustee EAR; east-west mTLS)`. That is **not an assertion of
fresh GPU evidence per request**. Fresh SNP evidence proves the live
client-to-gateway hop. Backend boot appraisal and mTLS establish a separate,
different evidence/control chain.

The designed per-backend fresh-evidence contract — a scheduled (~every 5 min)
composite CPU + all-8-GPU appraisal through the stock CoCo attestation-agent
and Trustee AS, plus a cheap per-request CPU quote binding the caller's
`X-KubeTEE-Nonce` to the serving key and the latest cached appraisal — is in
implementation and will supersede the `boot-time` boundary statement on
backends that deploy it. It is **not deployed**; today's header value is the
honest current limit. Under that contract, customer nonce rotation never
triggers GPU evidence work (deliberately — a freshness decision must not be
throttleable by a DoS caller), and a measurement mismatch or stale evidence
circuit-breaks **new verified routing on the customer side** while KubeTEE
alerts operators and never auto-kills a serving pod.

`signing_keys: []` is intentional in this deployment. The public
measurement-signing key is obtained independently from the registry's
`key_url`.

## 7. Current verification and remaining gaps

The released source is
`KubeTEE-AI/litellm@836124e8830c51c8f07ccfe013e21cfaedfac420`,
produced by GitHub Actions [run `44991222190`](https://github.com/KubeTEE-AI/litellm/actions/runs/44991222190),
with image
`ghcr.io/kubetee-ai/litellm-database:1.110.2-kubetee.1@sha256:2f47378d242aba5d4a73d4f6b7853e3fa1160e1c6020545960fa4a04cd651a96`.

The signed measurement record identifies the exact guest launch measurement,
InitData `HOST_DATA` derivation, images, firmware and kernel. All three
captured gateway replicas were checked using native AMD verification.
Independent SNP consumer work is being reviewed in
[SayGM/gm-miner PR #419](https://github.com/taostat/gm-miner/pull/419); that
pull request is not a claim of an already-merged worker migration.

Acceptance still requires native client verification rather than only a
chat 200. Remaining hardening includes the per-backend fresh-evidence
contract described in section 6 (designed, not deployed) and fresh
in-guest-generated serving identities. Reproducible-build equivalence is published
source-commit → CI-run → image-digest provenance today; bit-for-bit
reproducibility is not claimed. None of these is advertised as deployed here.
