# KubeTEE attestation specification — `kubetee.attestation.v1`

**Deployment described:** KubeTEE's public **AMD SEV-SNP** gateway on the
Subnet-Owner-controlled `kubetee` cluster, running **LiteLLM
`1.110.2-kubetee.1`** from source commit
`836124e8830c51c8f07ccfe013e21cfaedfac420`. Three gateway replicas are
deployed with `kata-qemu-snp-runtime-rs`.

**Audience:** clients and partner verifiers integrating with
`https://llm.kubetee.ai`. This is the partner contract for the current
producer, signed reference registry, report-data binding, TLS possession and
key custody. [CLIENT-FACING-ATTESTATION.md](./CLIENT-FACING-ATTESTATION.md)
is its endpoint guide. [EAST-WEST-ATTESTED-MTLS.md](./EAST-WEST-ATTESTED-MTLS.md)
describes the separate backend hop.

---

## 1. Evidence and scope

The gateway exposes a fresh standard **AMD SEV-SNP attestation report** in
CoCo's structured `attestation_report` / `cert_chain` representation beneath
`evidence.snp`. A verifier must use AMD's VCEK certificate path, not Intel
DCAP/ITA, and must not apply image or measurement fields of a different TEE.

The optional `appraisal` object carries a Trustee EAR with AR4SI
trustworthiness claims. This is **boot appraisal**, supplementary to the
fresh report for the caller's nonce. If `appraisal` is absent, the report,
its request binding and TLS possession still stand independently.

The production confidentiality boundary has two distinct hops:

1. The public request terminates in an SNP LiteLLM guest. Its current report
   and TLS-possession signature can be verified by the client.
2. The gateway calls a TDX/NVIDIA-CC model backend through mTLS. That backend
   is appraised at boot before Trustee releases its identity. It does **not**
   return a fresh per-request GPU report in this deployment. A scheduled
   composite CPU + 8-GPU appraisal with a per-nonce CPU-quote binding is
   designed and in implementation (see [EAST-WEST-ATTESTED-MTLS.md](./EAST-WEST-ATTESTED-MTLS.md)
   §6); it is not deployed.

Trustee v0.23.0 accepts both platforms in their own evidence formats. CoCo,
Trustee and KBS remain standard upstream components; the gateway is not
presented as a miner or as a replacement for either party's independent
hardware appraisal.

---

## 2. SNP measurement composition

| SNP report field | Current contract |
|---|---|
| `measurement` | 48-byte SHA-384 launch measurement covering the declared guest composition. Compare against the independent published reference, not a value supplied only by the serving guest. |
| `host_data` | 32-byte prefix of the SHA-384 digest of the exact **uncompressed InitData TOML**. Kata 4.4 computes that digest and truncates it to 32 bytes for `HOST_DATA`. It is not a SHA-256 digest. |
| `report_data` | The exact 64-byte v1 request binding defined in §4. |
| `policy` | Require `debug_allowed=false`, `migrate_ma_allowed=false`, the documented guest ABI/policy, VMPL0 and report version 3–5. |
| `tcb` | Validate the AMD VCEK chip/TCB relationship and approve the reported platform TCB independently. A TLS success is not TCB verification. |
| `cert_chain` | Cryptographically validate ARK/ASK/VCEK by certificate roles, AMD roots and processor generation. CoCo's `cert_type` strings are serialization labels, not trust decisions. |
| `signature` | Verify the report using the processor's verified VCEK. VLEK is not supported by this release contract. |

The published launch measurement for this release is:

`20f0e183b7844cc835118d804699ab8b6cdab297414d8f54d70331378ff0d7fdd8a7548a0253ba561bec21e13a0dcc67`

The full uncompressed InitData digest is:

`sha384:5bd1fe028a632b9efc6eceedcbf5a344b13ed1dab6c1b3a8295f0ff20aebe3aa3cd773703afb77f5ee2c2fbe567b50ab`

Its first 32 bytes, `5bd1fe028a632b9efc6eceedcbf5a344b13ed1dab6c1b3a8295f0ff20aebe3aa`,
must equal the report's `HOST_DATA`.

The signed registry supplies the exact firmware, kernel, kernel command line
and image inputs that define this release. Guests are verified individually;
`all_replicas_verified` in the registry records verification observations,
not a substitute for checking the caller's current session.

---

## 3. Signed reference publication

The current production registry consists of exactly these public documents:

| Document | Purpose |
|---|---|
| [`/.well-known/tee-measurements.json`](https://kubetee.ai/.well-known/tee-measurements.json) | Signed, immutable **schema `kubetee.tee-measurements/2`**, SNP role `litellm` reference record. |
| [`/.well-known/tee-measurements-signing-key-2026.json`](https://kubetee.ai/.well-known/tee-measurements-signing-key-2026.json) | Independently published Ed25519 public verification key. |
| [`/.well-known/tee-measurements.schema.json`](https://kubetee.ai/.well-known/tee-measurements.schema.json) | Machine-readable schema for the record and its verification expectations. |

The registry schema is authoritative. It includes `schema`, `version`,
`role`, `tee`, `runtime_class`, `status`, `not_before`, `key_id`, `subject`,
`provenance`, `snp` and `signature`, plus an `attestation` observation block.

### Provenance

This release identifies:

| Field | Value |
|---|---|
| Source | `KubeTEE-AI/litellm`, `kubetee-prod@{836124e8830c51c8f07ccfe013e21cfaedfac420}` |
| Image | `ghcr.io/kubetee-ai/litellm-database:1.110.2-kubetee.1@sha256:2f47378d242aba5d4a73d4f6b7853e3fa1160e1c6020545960fa4a04cd651a96` |
| GitHub build | [run `44991222190`](https://github.com/KubeTEE-AI/litellm/actions/runs/44991222190) |
| Guest | Kata 4.4.0, AMD EPYC-v4, 9 effective vCPUs; measured agent policy denies `ExecProcessRequest` and guest evidence write streams. |
| Measurement derivation | Independently recomputed with `sev-snp-measure` and compared with live signed reports |

The exact image is digest-pinned in the deployment and measured InitData
policy. Provenance links source, signed build and digest. This does **not**
by itself promise bit-for-bit reproducibility of every upstream base image
or build dependency; verifiers use the signed measurement reference and live
hardware report to establish the running composition.

### Signature and lifecycle

Verify `signature.sig` as **Ed25519 over RFC 8785 (JCS) canonicalized JSON
with the `signature` member removed**. The record's `key_id` and `key_url`
identify the independent HTTPS public key.

Versions are append-only and monotonic within their role-scoped stream.
Status is `upcoming`, `active` or `revoked`; a prior immutable record is not
silently reused or rewritten. Retention is what lets a verifier establish
that a measured release is approved; it does not establish that a different
live replica has the same identity without appraisal.

The optional `attestation.observed_pod_identities` records which running
replicas were verified, at what time and against which verifier reference.
Verifier [PR #419](https://github.com/taostat/gm-miner/pull/419) is the
separate SayGM consumer contribution awaiting its maintainers' review. It is
not presented as a merged worker release.

The publication is signed JSON, not a claim that CoRIM/COSE ingestion is
part of this release.

---

## 4. Request binding — `kubetee.attestation.v1`

Both the complete endpoint and inline chat evidence use exactly this
64-byte value for SNP `report_data`:

```text
SHA256(exact bindings.report_data_statement bytes) || 32 zero bytes
```

The served statement is RFC 8785 JCS with this fixed template:

```json
{"keyset_digest":"sha256:<hex>","nonce":"<64-hex>","purpose":"kubetee.attestation.v1"}
```

- `nonce` is the caller's 64 lowercase hexadecimal characters.
- `keyset_digest` is SHA-256 over the served `keyset` after RFC 8785
  canonicalization, written as `sha256:<hex>`.
- `purpose` is the literal `kubetee.attestation.v1`.
- `bindings.report_data_statement` carries the exact string to hash. Do not
  substitute or reserialize it.

### Conformance vector

For fixture keyset:

```json
{"not_after":"2030-01-01T00:00:00Z","subject":"kubetee.attestation.v1/test-vector","tls_public_keys":[{"domain":"llm.kubetee.ai","spki_sha256":"0000000000000000000000000000000000000000000000000000000000000000"}]}
```

the keyset digest must be:

`sha256:693868b5f94f4dad208e8e37fe93ebf1be212f3451462b079dc9ba828b8d33ea`

For the nonce made by repeating `0123456789abcdef` four times, the complete
statement is

`{"keyset_digest":"sha256:693868b5f94f4dad208e8e37fe93ebf1be212f3451462b079dc9ba828b8d33ea","nonce":"0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef","purpose":"kubetee.attestation.v1"}`

The statement digest must be
`755d36ae1b2ea98e9bdb32350b7356b75515e4ecae711a198ade29ec325b14f4`. Its 32
bytes followed by 32 zero bytes must equal the report's 64-byte `report_data`.

---

## 5. Keyset and key custody

The current endpoint serves this keyset shape:

```json
{
  "subject": "kubetee.attestation.v1/llm.kubetee.ai",
  "not_after": "RFC3339 timestamp",
  "tls_public_keys": [{"spki_sha256": "hex:64", "domain": "llm.kubetee.ai"}],
  "signing_keys": [],
  "e2ee_keys": []
}
```

The SPKI digest is SHA-256 of the TLS leaf certificate's DER
SubjectPublicKeyInfo. The same serving key signs the nonce for
`tls_possession`. A client must compare it with the certificate of **its own
TLS connection**, not accept a certificate supplied only inside a response.

| Key | Production custody | Trust boundary |
|---|---|---|
| Public gateway TLS identity | Measured gateway bootstrap retrieves `default/litellm-confidential/{tls.crt,tls.key}` over CDH loopback `127.0.0.1:8006` into Memory `emptyDir` `/etc/tls`. LiteLLM serves `:4000`; Traefik TLS passthrough and DNS-only Cloudflare do not terminate it. This is not a direct conventional Kubernetes TLS Secret projection. | At every guest start the current identity is loaded after KBS appraisal—the registry's `fresh_certificate_per_boot` convention describes this retrieval, **not generation of a new keypair per boot**. The identity can persist across boots. Trustee/KBS and its authorized storage/admin boundary remain trusted key-release parties. |
| Gateway east-west identity | `kubetee_bootstrap` retrieves the approved CA and gateway leaf over CDH loopback into container-local `/run/kubetee-eastwest`. Startup fails closed if unavailable. This path is not a declared pod-shared host-visible volume. | It is protected by guest/policy custody and role-scoped key release, not a claim that privileged KBS administrators cannot access escrowed identity material. |
| Kimi/MiMo backend identities | A measured CDH-fetch init container inside each backend Kata CVM retrieves its role-specific cert/key, CA and HF resource into disk-backed `emptyDir: {}` `/certs`. On the Granian frontend the measured SGLang process reads `/certs` and terminates strict mTLS directly; on the legacy frontend an in-CVM HAProxy container reads `/certs` and fronts loopback SGLang. | The volume is in-sandbox guest storage, not a mounted ordinary Kubernetes TLS Secret; it is also not Memory tmpfs. The backend key is released to an appraised guest, not proved generated only inside it. |
| Measurement signing key | Offline Ed25519 private key. Only its public document is served over HTTPS; it is separate from the gateway keyset. | Compromise of that public document/HTTPS publication path is a distinct reference-distribution risk from compromise of a serving guest. |

`signing_keys: []` is intentional for this deployment. The offline
measurement public key is not embedded in this keyset. The gateway processes
requests and responses in its confidential guest.

---

## 6. Required client verification

Accept a gateway only after all of these succeed on the caller's connection:

1. Require explicit `tee` and `tee_type` equal to `snp`,
   `runtime_class=kata-qemu-snp-runtime-rs` and
   `evidence.snp.schema=kubetee.snp-evidence/1`.
2. Decode CoCo's unsigned-byte JSON fields with their native sizes. Require
   the supported report version, VMPL0 and valid certificate roles.
3. Verify the AMD ARK/ASK/VCEK chain, processor/chip identity and report
   signature independently using stock SNP tooling such as `sev 7.1.0`.
4. Compare launch `MEASUREMENT`, `HOST_DATA`, TCB and guest policy with the
   signed registry and the verifier's own policy. Validate the measured
   InitData/image composition and denied guest control operations.
5. Recompute `SHA256(JCS(keyset))`, hash the exact statement bytes and check
   the report's 64-byte `report_data` equals digest plus 32 zero bytes.
6. Require keyset validity, correct `llm.kubetee.ai` scope and match of the
   reported SPKI/certificate fingerprint to the caller's TLS session.
7. Verify the nonce possession signature with the session certificate. This
   is separate from the AMD report signature and from any optional boot EAR.
8. If `appraisal` exists, verify its native Trustee evidence and approval;
   never substitute a boot EAR for the current request binding.

A response declaring "attested", an ordinary HTTP 200, image text, pod name
or permitted API route is not evidence of any of those checks.

---

## 7. Deployment boundaries

| Question | Current answer |
|---|---|
| Is the public TLS session inside the confidential gateway? | **Yes.** TLS passthrough reaches LiteLLM in the SNP guest; neither Traefik nor Cloudflare terminates the payload. |
| Is client-to-gateway evidence fresh and nonce-bound? | **Yes.** The current connection receives an SNP report with the v1 statement binding and TLS possession. |
| Are measurements publicly available? | **Yes.** The signed SNP registry, schema and independent Ed25519 public key are live at the links in §3. |
| Is the backend GPU quote fresh per inference request? | **No.** The backend is boot-attested for mTLS key release. Per-request backend GPU evidence is designed (scheduled composite appraisal + per-nonce CPU-quote binding) but not deployed. |
| Are all three gateway instances exactly the released image? | The deployment pins the exact image and measured policy; all three captured replicas passed independent SNP verification. Each session still requires its own possession check. |
| Does this establish zero-operator trust? | **No.** Trustee/KBS release authority, protected administration/storage, infrastructure control and reusable identities remain explicit trust boundaries. |

This contract does not invent per-request GPU freshness, encrypted weights,
in-guest-only key generation, a completed consumer rollout or full
reproducible-build equivalence.
