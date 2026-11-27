# KubeTEE attestation specification — `kubetee.attestation.v1`

**Deployment described:** KubeTEE's public gateway at `https://llm.kubetee.ai`
on the Subnet-Owner-controlled `kubetee` cluster — three **AMD SEV-SNP** Kata
replicas of LiteLLM `1.110.2-kubetee.8` (`kata-qemu-snp-runtime-rs`) routing to
**Intel TDX** SGLang backends (`kata-qemu-nvidia-gpu-tdx-runtime-rs`).

**Audience:** clients and partner verifiers integrating with
`https://llm.kubetee.ai`. This document is the protocol contract: roles and
evidence framing, measurement composition, request binding, key custody, the
published reference documents, and the required verification.
[CLIENT-FACING-ATTESTATION.md](./CLIENT-FACING-ATTESTATION.md) is the endpoint
how-to, [ATTESTATION-REFERENCE-MEASURES-SGLANG.md](./ATTESTATION-REFERENCE-MEASURES-SGLANG.md)
holds the backend reference values, and
[EAST-WEST-ATTESTED-MTLS.md](./EAST-WEST-ATTESTED-MTLS.md) describes the
backend hop.

---

## 1. Roles, TEEs and evidence framing

| Role | Guest | TEE | Populated evidence |
|---|---|---|---|
| `litellm` | public gateway | AMD SEV-SNP | `evidence.snp` (native `attestation_report` + `cert_chain`) |
| `nim-terminator` | SGLang model backend | Intel TDX | `quote` (Intel DCAP) + `event_log` (TCC) + `evidence.tdx` |

Roles and TEEs are independent; the evidence half is **disjoint per TEE**. An
SNP report is not an Intel quote and an Intel quote is not an SNP report: AMD
evidence is verified through AMD's VCEK certificate path, TDX evidence through
Intel DCAP. Never apply one TEE's image or measurement fields to the other, and
reject any response whose `tee` / `tee_type` / `runtime_class` disagree with the
populated half.

The optional `appraisal` object carries a Trustee EAR with AR4SI
trustworthiness claims. It is **boot appraisal**, supplementary to the fresh
report for the caller's nonce. If `appraisal` is absent, the report, its
request binding and TLS possession stand independently. A successful hardware
appraisal does not establish resource authorization or per-request freshness.

The production confidentiality boundary has two hops:

1. The public request terminates in an SNP LiteLLM guest. Its current report
   and TLS-possession signature are verifiable by the client.
2. The gateway calls the TDX backend over strict mTLS. That backend is
   appraised at boot before Trustee releases its identity, and serves its own
   fresh in-guest evidence envelope (§3.2). A composite **CPU + 8-GPU** mint
   with the caller's nonce bound into the CPU quote's `report_data` is
   **deployed** on the rate-limited `X-KubeTEE-Nonce` tier (1 per minute per
   key); the unlimited `X-KubeTEE-Proof` tier attaches the routed pod's cached
   evidence plus a gateway signature binding it to the response (§3.3, and
   [CLIENT-FACING-ATTESTATION.md](./CLIENT-FACING-ATTESTATION.md) §3A).

CoCo, Trustee and KBS remain standard upstream components in their own evidence
formats. The gateway is not presented as a miner or as a replacement for either
party's independent hardware appraisal.

---

## 2. Measurement composition

### 2.1 SNP report fields (gateway)

| SNP report field | Contract |
|---|---|
| `measurement` | 48-byte SHA-384 launch measurement covering the declared guest composition. Compare against the independent published reference, not a value supplied only by the serving guest. |
| `host_data` | 32-byte prefix of the SHA-384 digest of the exact **uncompressed InitData TOML**. Kata 4.4 computes that digest and truncates it to 32 bytes for `HOST_DATA`. It is not a SHA-256 digest. |
| `report_data` | The exact 64-byte v1 request binding defined in §3. |
| `policy` | Require `debug_allowed=false`, `migrate_ma_allowed=false`, the documented guest ABI/policy, VMPL0 and report version 3–5. |
| `tcb` | Validate the AMD VCEK chip/TCB relationship and approve the reported platform TCB independently. A TLS success is not TCB verification. |
| `cert_chain` | Cryptographically validate ARK/ASK/VCEK by certificate roles, AMD roots and processor generation. CoCo's `cert_type` strings are serialization labels, not trust decisions. |
| `signature` | Verify the report using the processor's verified VCEK. VLEK is not supported by this release contract. |

The published launch measurement for the gateway is:

`20f0e183b7844cc835118d804699ab8b6cdab297414d8f54d70331378ff0d7fdd8a7548a0253ba561bec21e13a0dcc67`

The full uncompressed InitData digest is:

`sha384:e2b14e15f4cfd73d489881134ef1d1bd12a822e3d7ad0421b668336da37e50e60447b2629c461b804291dad719686eb2`

Its first 32 bytes, `e2b14e15f4cfd73d489881134ef1d1bd12a822e3d7ad0421b668336da37e50e6`,
must equal the report's `HOST_DATA`.

### 2.2 TDX launch registers (backend)

| TDX register | Contract |
|---|---|
| `MRTD` | 48-byte SHA-384 measured by the TDX module over the initial TD (OVMF + kernel + initrd + cmdline). Captured from the quote's TDINFO and cross-checked by CC event-log replay. |
| `MRCONFIGID` | 48-byte SHA-384 of the exact **uncompressed InitData TOML** — the TDX sibling of SNP `host_data` at full digest length. |
| `RTMR0` | Firmware / CCEL measurement. **Node-specific**: it legitimately differs per host and is one reason matching is any-active-record (§5). |
| `RTMR1` | Kernel command line. |
| `RTMR2` | Initrd / OS. |
| `RTMR3` | Unused (zero) in this deployment. |
| `MROWNER` / `MROWNERCONFIG` | Unset (zero), as expected. |

Launch registers measure firmware + kernel + initrd + cmdline and InitData, **not
application code**: an image roll that changes only application code keeps the
same registers. The reference values for the deployed backends are in
[ATTESTATION-REFERENCE-MEASURES-SGLANG.md](./ATTESTATION-REFERENCE-MEASURES-SGLANG.md)
§2–3 and in the registry records (§5).

The measured **agent policy** is inside InitData: changing it changes
`MRCONFIGID`, so enabling a denied capability is a measurement change a verifier
rejects. The deployed posture denies `ExecProcessRequest` and
`WriteStreamRequest` (the host cannot exec into the guest or write to its
processes) while allowing the standard container-lifecycle and read surface.

---

## 3. Request binding — `kubetee.attestation.v1`

Both evidence formats use one 64-byte `report_data` convention whose **head**
is always the statement digest and whose **tail** is form-dependent:

```text
SHA256(exact bindings.report_data_statement bytes)  ||  tail(32 bytes)
```

| Form | Tail (last 32 bytes) |
|---|---|
| Gateway nonce-bound (§3.1) | 32 zero bytes |
| Backend shared epoch (§3.2) | 32 zero bytes |
| Backend **fresh composite** (`X-KubeTEE-Nonce`, §3.2) | the caller's 32-byte nonce (raw bytes of the 64-hex nonce) |

Do not assume the zero-pad on the fresh composite: it is `digest ‖ nonce`,
verified live (2026-11-27, MiMo lu-b300-40). A verifier keys the check off the
served statement + nonce it sent: `report_data[:32] == SHA-256(statement)` and
`report_data[32:]` must equal either 32 zero bytes or the nonce bytes.

Three statement forms exist. Each is RFC 8785 JCS; `bindings.report_data_statement`
carries the exact string to hash — do not substitute or reserialize it.

### 3.1 Nonce-bound form (gateway, and direct backend requests)

```json
{"keyset_digest":"sha256:<hex>","nonce":"<64-hex>","purpose":"kubetee.attestation.v1"}
```

- `nonce` is the caller's 64 lowercase hexadecimal characters.
- `keyset_digest` is SHA-256 over the served `keyset` after RFC 8785
  canonicalization, written as `sha256:<hex>`.
- `purpose` is the literal `kubetee.attestation.v1`.

**Conformance vector.** For fixture keyset:

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
bytes followed by 32 zero bytes must equal the report's 64-byte `report_data`
(zero-padded tail — this is the gateway form).

### 3.2 Epoch form (backend, shared across callers)

A hardware report is sealed at mint, so one quote cannot bind many callers'
nonces. The backend therefore mints **one quote per epoch** (≤ 1 per 5 minutes
per replica) whose `report_data` binds an epoch statement:

```json
{"epoch_id":"<id>","issued_at":"<RFC3339>","valid_until":"<RFC3339>","keyset_digest":"sha256:<hex>","purpose":"kubetee.attestation.v1"}
```

Two epochs (current + previous) are retained so a caller can resolve its
`epoch_id` across rotation. Freshness is layered:

1. **Hardware freshness (epoch)** — always present, always enforced: the epoch
   window bounds freshness in time.
2. **Caller freshness (per-request, optional)** — when the backend mints one,
   `signature` is the backend's per-epoch Ed25519 evidence-signing key
   (`tee-pubkey`) over
   `SHA-256(quote) ‖ SHA-256(nonce) ‖ epoch_id ‖ counter`, where `counter` is a
   monotonic per-epoch request counter. The nonce defeats quote reuse at a
   different caller; the counter defeats within-epoch replay. The `tee-pubkey`
   public half is committed via the epoch statement's `keyset_digest`, so it is
   covered by the hardware quote. Verify Layer 2 strictly when present; a
   missing Layer 2 is a weaker binding, not an invalid envelope.

**Fresh nonce-bound mint.** `X-KubeTEE-Nonce: <64-hex>` (one of the two client
opt-in headers) requests a **fresh CPU + 8-GPU composite** and bypasses the
epoch cache. The CPU quote's statement binds the caller's nonce directly and
adds epoch context (a third statement form — the nonce form of §3.1 plus
`epoch_id`/`issued_at`):

```json
{"epoch_id":"<epoch>-fresh","issued_at":"<RFC3339>","keyset_digest":"sha256:<hex>","nonce":"<64-hex>","purpose":"kubetee.attestation.v1"}
```

and its `report_data` is `SHA-256(statement) ‖ nonce bytes` — the zero-pad tail
becomes the caller's nonce (verified live 2026-11-27). Each of the 8 GPU SPDM
`GET_MEASUREMENTS` frames echoes the same nonce. The envelope carries a compact
`gpu` summary (count / arch / `evidence_digest` / timing / `nonce_echoed`); the
8 full GPU reports + certificate chains stay on the backend's own
east-west-mTLS evidence service (operator surface), with `evidence_digest` the
commitment to the full set. The mint is sealed to one nonce — deliberately
uncacheable — and rate-limited to **1 per minute per API key** (`429` with
`Retry-After` and a self-documenting `use_instead` beyond that). A second
opt-in header, `X-KubeTEE-Proof`, is the unlimited proof-of-inference tier
(§3.3). Ordinary completions ride the cached epoch.

**Residual limit.** A hardware report carries no timestamp, and serving keys are
KBS-released rather than proved generated in-guest per boot (§4). The epoch
window bounds freshness in time, not per boot. Closing that gap requires a
keypair generated in-guest per boot and named in `report_data`; it is not
claimed until implemented.

### 3.3 Proof statement — `kubetee.proof.v1` (gateway signature over response)

`X-KubeTEE-Proof` is the unlimited proof-of-inference tier. The gateway signs a
canonical (RFC 8785 JCS) statement with its **serving key** — the key committed
into its own SNP quote via `keyset_digest` (the same key as `tls_possession`):

```json
{"backend_evidence_digest":"sha256:<hex>","backend_endpoint":"https://<routed-backend>/v1","issued_at":"<RFC3339>","keyset_digest":"sha256:<hex>","purpose":"kubetee.proof.v1","request_anchor":{...},"response_digest":"sha256:<hex>","response_input":"sha256(utf8(jcs({content,model})))","response_mode":"response-bound","version":"kubetee.proof.v1"}
```

`response_mode` is `response-bound` (non-streaming, binds the assembled output)
or `request-bound` (streaming fallback, binds the request). `response_input` is
the **recipe**, emitted verbatim so a verifier never guesses the byte layout:
`sha256(utf8(jcs({content,model})))` for `response-bound`, and
`sha256(utf8(jcs({messages,model})))` for `request-bound` (over a
JSON-stable `{messages, model}` — sorted keys, compact separators). The exact
statement text is also served in `X-KubeTEE-Proof-Statement`; hash it as
received. `request_anchor` is
`{"kind":"nonce","value":"<64-hex>"}` when the client sends `X-KubeTEE-Proof:
<64-hex>`, or `{"kind":"request-digest","value":"sha256:<hex>"}` when it sends
`X-KubeTEE-Proof: 1`. `backend_evidence_digest` is the SHA-256 of the attached
routed-pod evidence bytes (per-row cache — each LiteLLM row surfaces its own
pod's evidence, not a gateway-global blob).

The chain of trust is `gateway-sig(response+nonce+evidence) → evidence(quote) →
backend-L2(quote+nonce)`. This is **not** a quote whose `REPORTDATA` is the
response hash: silicon cannot sign arbitrary post-hoc data and the gateway
assembles the response. The algorithm is reported, not assumed (`EdDSA`, `ES256`
raw `r‖s`, or `RS256`), and verifying it is a **separate trust operation** from
the hardware-report signature and the registry signature. Signature verification
is fail-closed: no key ⇒ `X-KubeTEE-Proof-Error` and no signature. Full header
set and a runnable check are in
[CLIENT-FACING-ATTESTATION.md](./CLIENT-FACING-ATTESTATION.md) §3A/§5.

---

## 4. Keyset and key custody

The gateway endpoint serves this keyset shape:

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
`tls_possession`; a client must compare it with the certificate of **its own TLS
connection**, never a certificate supplied only inside a response.

| Key | Production custody | Trust boundary |
|---|---|---|
| Public gateway TLS identity | Measured gateway bootstrap retrieves `default/litellm-confidential/{tls.crt,tls.key}` over CDH loopback `127.0.0.1:8006` into Memory `emptyDir` `/etc/tls`. LiteLLM serves `:4000`; Traefik TLS passthrough and DNS-only Cloudflare do not terminate it. This is not a direct conventional Kubernetes TLS Secret projection. | At every guest start the current identity is loaded after KBS appraisal — the registry's `fresh_certificate_per_boot` convention describes this retrieval, **not generation of a new keypair per boot**. The identity can persist across boots. Trustee/KBS and its authorized storage/admin boundary remain trusted key-release parties. |
| Gateway east-west identity | `kubetee_bootstrap` retrieves the approved CA and gateway leaf over CDH loopback into container-local `/run/kubetee-eastwest`. Startup fails closed if unavailable. This path is not a declared pod-shared host-visible volume. | Protected by guest/policy custody and role-scoped key release, not a claim that privileged KBS administrators cannot access escrowed identity material. |
| Kimi/MiMo backend identities | A measured CDH-fetch init container inside each backend Kata CVM retrieves its role-specific cert/key, CA and HF resource into disk-backed `emptyDir: {}` `/certs`. On the Granian frontend the measured SGLang process reads `/certs` and terminates strict mTLS directly; on the legacy frontend an in-CVM HAProxy container reads `/certs` and fronts loopback SGLang. | The volume is in-sandbox guest storage, not a mounted ordinary Kubernetes TLS Secret, and not Memory tmpfs. The backend key is released to an appraised guest, not proved generated only inside it. |
| Backend per-epoch evidence key (`tee-pubkey`) | Ed25519 key held by the backend guest; public half committed in the epoch statement's `keyset_digest` and therefore bound into the hardware `report_data`. Distinct from the backend TLS key and from all gateway keys. | Proves caller-binding of a relayed envelope; it does not sign model-output bytes. |
| Measurement signing key | Offline Ed25519 private key. Only its public document is served over HTTPS; it is separate from the gateway keyset. | Compromise of that public document/HTTPS publication path is a distinct reference-distribution risk from compromise of a serving guest. |

`signing_keys: []` is intentional for this deployment: the offline measurement
public key is not embedded in the keyset. The gateway processes requests and
responses in its confidential guest.

**What stops TLS termination outside the guest.** The private halves above are
never mounted as conventional Kubernetes Secrets; they are released by KBS to
an appraised guest over CDH loopback. On the ordinary path nothing outside the
guest can terminate public TLS: Cloudflare is DNS-only, Traefik is L4
passthrough and LiteLLM binds the TLS files inside the CVM. If anything did
terminate with a foreign key, the caller detects it immediately — the served
`keyset` / `tls_cert_sha256` and the measured `report_data` binding describe
the session key, and a client compares them with its **own** TLS session
(§6 step 6), so a different certificate fails the check and a replayed report
cannot match a fresh nonce. The named residual: keys are KBS-released escrow,
so the contract proves "this key is bound by a genuine measured-guest report",
not "the private half exists only inside the guest" — a privileged
Trustee/KBS storage administrator is inside the trust boundary (see §7), and
in-guest-only key generation named in `report_data` is not implemented.

---

## 5. Published reference documents

The publication surface consists of these public documents at
`https://kubetee.ai/.well-known/`:

| Document | Schema | Purpose |
|---|---|---|
| [`tee-measurements-registry.json`](https://kubetee.ai/.well-known/tee-measurements-registry.json) | `kubetee.tee-measurements-registry/1` | **Authoritative signed allowlist** of backend (`nim-terminator`, TDX) reference records — the matching surface for backend evidence and the gateway circuit breaker. |
| [`tee-measurements.json`](https://kubetee.ai/.well-known/tee-measurements.json) | `kubetee.tee-measurements/2` | Signed SNP role record for `litellm` (gateway launch measurement, `host_data`, provenance). |
| [`tee-measurements-sglang.tdx.json`](https://kubetee.ai/.well-known/tee-measurements-sglang.tdx.json) | `kubetee.tee-measurements/1` | The first single-record TDX projection (one backend record). Retained as published history; matching consumers use the registry. |
| [`tee-reference-values.cbor`](https://kubetee.ai/.well-known/tee-reference-values.cbor) (+ `.sig`, `.sha256`, human `.json`) | `kubetee.tee-reference-values/1` | CoRIM (IETF RATS) twin of one registry record for RVPS ingestion, with a detached Ed25519 signature over the raw CBOR. |
| [`tee-measurements-signing-key-2026.json`](https://kubetee.ai/.well-known/tee-measurements-signing-key-2026.json) | — | Independently published Ed25519 public verification key. |
| [`tee-measurements.schema.json`](https://kubetee.ai/.well-known/tee-measurements.schema.json) | — | Machine-readable schema for the record and its verification expectations. |

### Registry matching policy

The registry's own `policy` block is authoritative:

```json
"policy": {
  "match": "any-active-record",
  "retention": {
    "generations_per_chain": 2,
    "chain": "model + role + tee (a chain rolls versions together)",
    "generation": "one immutable image_ref (content-addressed)",
    "note": "current + previous generation per chain stay ACTIVE so BOTH verify during AND after a rollout ... there is no time-based re-capture."
  },
  "hard_expiry": "valid_until is OPTIONAL and manual-only (e.g. throwaway canaries); absent = no expiry ..."
}
```

Observed TDX evidence is legitimate iff its registers match **any** record with
`status: "active"` and, when `valid_until` is set, `now <= valid_until`, for the
same `tee`. There is no per-model or per-image pin on the verifier. This is what
accommodates node-specific `RTMR0` (§2.2) and multiple concurrent models: each
measured (model × node) launch is one record.

**Record lifecycle (current + previous per chain).** A record's *generation* is
its immutable `image_ref`; its *chain* is (model, role, tee). The newest **two**
generations per chain — the current and the previous — stay active so **both**
verify during and after a rollout: the outgoing generation keeps matching until
the rollout completes and doubles as the rollback window. A record leaves the
allowlist only when a third newer generation lands in its chain (housekeeping
`--prune`), or it is hard-expired / `status: "deprecated"` / `"revoked"`.
Measurements change only at a rollout, so there is no time-based re-capture and
no fixed validity window: `valid_until` is optional and reserved for manual
hard-expiry (for example throwaway canaries). `supersedes` names the record a
new record replaces. Rotation is a re-capture plus a new record (append-only);
a prior immutable record is not silently reused or rewritten. Retention lets a
verifier establish that a measured release is approved; it does not establish
that a different live replica has the same identity without appraisal.

### Provenance and signature

Every record links source → signed build → digest. The gateway record
identifies:

| Field | Value |
|---|---|
| Source | `KubeTEE-AI/litellm`, `kubetee-prod@e763bb83ebf6f9f711199a58760235911bb1d6e1` |
| Image | `ghcr.io/kubetee-ai/litellm-database:1.110.2-kubetee.8@sha256:5d6c4c88bbca792909a91f14df4dde3fbc4e132e530adfc88e8514d3a8400fed` |
| GitHub build | [run `45909231309`](https://github.com/KubeTEE-AI/litellm/actions/runs/45909231309) |
| Guest | Kata 4.4.0, AMD EPYC-v4, 9 effective vCPUs; measured agent policy denies `ExecProcessRequest` and guest evidence write streams. |
| Measurement derivation | Independently recomputed with `sev-snp-measure` and compared with live signed reports. |

Backend record provenance (fork commit, CI run, image digest, validation node)
is carried per record in the registry and reproduced in
[ATTESTATION-REFERENCE-MEASURES-SGLANG.md](./ATTESTATION-REFERENCE-MEASURES-SGLANG.md)
§1. The exact image is digest-pinned in the deployment and in the measured
InitData policy. Provenance links source, signed build and digest; it does **not**
by itself promise bit-for-bit reproducibility of every upstream base image or
build dependency. Verifiers use the signed reference and the live hardware
report to establish the running composition.

Verify `signature.sig` as **Ed25519 over RFC 8785 (JCS) canonicalized JSON with
the `signature` member removed**. The record's `key_id` and `key_url` identify
the independent HTTPS public key.

The publication is signed JSON and, where published, a detached-signed CoRIM —
not a claim that CoRIM/COSE ingestion is required of any consumer. The optional
`attestation.observed_pod_identities` block records which running replicas were
verified, at what time and against which verifier reference; verifier
[PR #419](https://github.com/taostat/gm-miner/pull/419) is the separate SayGM
consumer contribution awaiting its maintainers' review, not a merged worker
release.

---

## 6. Required client verification

Accept a gateway session only after all of these succeed on the caller's
connection:

1. Require explicit `tee` and `tee_type` equal to `snp`,
   `runtime_class=kata-qemu-snp-runtime-rs` and
   `evidence.snp.schema=kubetee.snp-evidence/1`.
2. Decode CoCo's unsigned-byte JSON fields with their native sizes. Require the
   supported report version, VMPL0 and valid certificate roles.
3. Verify the AMD ARK/ASK/VCEK chain, processor/chip identity and report
   signature independently using stock SNP tooling such as `sev 7.1.0`
   (pure-Rust crypto backend; OpenSSL is not required) or an equivalent
   independent implementation.
4. Compare launch `MEASUREMENT`, `HOST_DATA`, TCB and guest policy with the
   signed registry record and the verifier's own policy. Validate the measured
   InitData/image composition and denied guest control operations.
5. Recompute `SHA256(JCS(keyset))`, hash the exact statement bytes and check the
   report's 64-byte `report_data` equals that digest followed by 32 zero bytes
   (the gateway form — §3).
6. Require keyset validity, correct `llm.kubetee.ai` scope and match of the
   reported SPKI/certificate fingerprint to the caller's TLS session.
7. Verify the nonce possession signature with the session certificate. This is
   separate from the AMD report signature and from any optional boot EAR.
8. If `appraisal` exists, verify its native Trustee evidence and approval;
   never substitute a boot EAR for the current request binding.

Accept backend evidence only after the TDX counterpart succeeds:

1. Require the populated half to agree with `tee` / `schema`
   (`kubetee.tdx-evidence/1` → `quote` + `event_log`).
2. Verify the Intel DCAP quote signature and certificate chain; read the TDINFO
   registers and replay the CC event log (`RTMR[i] = SHA-384(RTMR[i] ‖ digest)`)
   to reproduce `RTMR0–3`.
3. Check the 64-byte `report_data` against the exact epoch (or nonce-bound)
   statement: the first 32 bytes must equal `SHA-256(statement)` and the tail
   must be 32 zero bytes (epoch form) or the caller's nonce bytes (fresh
   composite form, §3.2). Check `MRCONFIGID` against the published InitData
   digest.
4. Match the registers against the **signed registry** (any active record) —
   never against a value the serving guest supplies.
5. Verify Layer 2 (`tee-pubkey` per-request signature) when present. It is
   emitted on a fresh `X-KubeTEE-Nonce` mint and **absent on the cached epoch
   path** (`X-KubeTEE-Backend-Evidence-Layer2: absent`); a missing Layer 2 is a
   weaker binding, not an invalid envelope. The `X-KubeTEE-Proof` statement
   (§3.3) is a separate gateway-level signature and is verified separately.
6. If a boot EAR is present, verify it with the Trustee AS JWKS — and never let
   it clear a circuit-breaker trip or replace the request binding.

A response declaring "attested", an ordinary HTTP 200, image text, pod name or
permitted API route is not evidence of any of those checks. The runnable form of
this checklist is in [CLIENT-FACING-ATTESTATION.md](./CLIENT-FACING-ATTESTATION.md)
§5.

---

## 7. Deployment boundaries

| Question | Current answer |
|---|---|
| Is the public TLS session inside the confidential gateway? | **Yes.** TLS passthrough reaches LiteLLM in the SNP guest; neither Traefik nor Cloudflare terminates the payload. |
| Is client-to-gateway evidence fresh and nonce-bound? | **Yes.** The current connection receives an SNP report with the v1 statement binding and TLS possession. |
| Is backend evidence fresh? | **Yes, on two tiers.** `X-KubeTEE-Nonce` mints a fresh CPU + 8-GPU composite per caller nonce (rate-limited 1/min/key); `X-KubeTEE-Proof` returns the routed pod's cached evidence plus a gateway signature binding it to the response (unlimited). Without either header: one hardware quote per epoch (≤ 1 per 5 minutes per replica) with an optional per-request caller binding. |
| Are measurements publicly available? | **Yes.** The signed registry (authoritative backend allowlist), the SNP record, the CoRIM twin, schema and independent Ed25519 public key are live at the links in §5. |
| Are all gateway instances exactly the released image? | The deployment pins the exact image and measured policy; all captured replicas passed independent SNP verification. Each session still requires its own possession check. |
| Does this establish zero-operator trust? | **No.** Trustee/KBS release authority, protected administration/storage, infrastructure control and reusable identities remain explicit trust boundaries. |

This contract does not invent per-request GPU freshness beyond the deployed
`X-KubeTEE-Nonce` composite (rate-limited, raw GPU reports fetched separately),
encrypted weights, in-guest-only key generation, a completed consumer rollout or
full reproducible-build equivalence.
