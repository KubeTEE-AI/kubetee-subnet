# Client attestation for `llm.kubetee.ai`

**Current deployment:** three **AMD SEV-SNP** Kata guests on the
Subnet-Owner-controlled `kubetee` cluster, running **LiteLLM
`1.110.2-kubetee.1`** with `kata-qemu-snp-runtime-rs`.
**Partner contract:** [ATTESTATION-SPEC-v1.md](./ATTESTATION-SPEC-v1.md).
**Backend hop:** [EAST-WEST-ATTESTED-MTLS.md](./EAST-WEST-ATTESTED-MTLS.md).

The client can verify a fresh, nonce-bound AMD report for the gateway guest
that terminates its TLS connection. The release's exact source, image,
measurements and verifier observations are published in the signed
[`tee-measurements.json`](https://kubetee.ai/.well-known/tee-measurements.json)
registry.

---

## 1. What clients can verify

| Claim | Evidence |
|---|---|
| The serving endpoint is a genuine AMD SNP confidential guest | Signed SNP report and ARK/ASK/VCEK chain, independently verified for the relevant processor generation. |
| The evidence is fresh for this request | The report contains the hash of the caller's v1 nonce/keyset statement, not a reused fixed challenge. |
| The same guest terminates the caller's TLS connection | The gateway signs the nonce with its serving key; the client verifies it against the leaf certificate of its own TLS session and compares that key with the keyset. |
| The approved guest composition is running | Launch `MEASUREMENT`, `HOST_DATA`, guest policy, TCB and approved images/policy are compared with the independently signed reference registry. |
| The east-west SGLang backend runs our SGLang fork with the in-guest strict-mTLS transport | [ATTESTATION-REFERENCE-MEASURES-SGLANG.md](./ATTESTATION-REFERENCE-MEASURES-SGLANG.md) publishes the backend's measures (MRTD/RTMR0-3/MRCONFIGID), measured container set and fork/image provenance; machine record: [tee-measurements-sglang.tdx.draft.json](./tee-measurements-sglang.tdx.draft.json), published signed as [`tee-measurements-sglang.tdx.json`](https://kubetee.ai/.well-known/tee-measurements-sglang.tdx.json) — all six registers (`MRTD`/`MRCONFIGID`/`RTMR0-3`) are **captured** from the booted guest's quote and cross-validated (report-data binding + CCEL replay), and the record is **Active (signed)**. |
| A measurement-drifted or substituted backend cannot serve | Two independent layers: the KBS release policy (`nim/eastwest/resource-policy.rego`) blocks a drifted guest's certificate fetch at the source, and the gateway measurement-drift circuit breaker auto-blocks the row (HTTP 503) when role/`MRCONFIGID`/`MRTD`/`RTMR0-3`/OVMF move off the pinned reference. |
| Which serving replica minted the report | The endpoint's `pod` field and the TLS-session binding. A standalone request is load-balanced; it does not identify a separate chat request's replica. |

### What this does not prove

- It does not send an Intel quote, and Intel DCAP or ITA does not verify an
  SNP gateway report.
- It does not prove a new hardware keypair was generated for every boot.
  The gateway retrieves its approved serving identity after appraisal at
  each start; that identity can persist across starts.
- It does not turn reusable, KBS-released keys into a zero-operator-trust
  claim. KBS administration and trusted storage remain in the trust
  boundary.
- The backend is boot-attested for mTLS. No fresh per-request backend GPU
  quote is supplied by this gateway deployment. A per-backend fresh-evidence
  contract (scheduled composite CPU + 8-GPU appraisal via stock CoCo
  attestation-agent and Trustee AS, plus a per-nonce CPU quote binding the
  caller's challenge to the serving key) is designed and in implementation;
  it is **not deployed**.
- The measurement-drift circuit breaker covers **launch-composition drift**
  (role, InitData/`MRCONFIGID`, `MRTD`, `RTMR0-3`, OVMF) against the pinned
  reference — the boundary between boot appraisal and runtime drift. It does
  **not** detect runtime memory/code tampering *inside* an already-measured
  guest (no live runtime measurement exists), and it does not re-verify each
  request's model output. A drifted launch is caught; a compromised but
  identically-launched guest is caught only by whatever the in-guest measured
  policy denies (e.g. `ExecProcessRequest=false`) and by the KBS release gate.
- The endpoint's hardware evidence is adjacent to the response identity;
  it is not a signature over the full model-output bytes.

---

## 2. Standalone report endpoint

Send exactly 64 lowercase hexadecimal characters as the caller's nonce:

```bash
NONCE="$(openssl rand -hex 32)"
curl --fail-with-body \
  --get 'https://llm.kubetee.ai/v1/attestation' \
  --data-urlencode "nonce=${NONCE}" \
  --output attestation.json
```

Save the response only with the original exact byte strings; a verifier
uses `bindings.report_data_statement` exactly as received. The endpoint is
public but exposes no keys or protected model inputs.

### Response shape

The following is a **schema illustration**, not a real nonce, signature,
certificate or verified report:

```json
{
  "spec_version": "kubetee.attestation.v1",
  "tee": "snp",
  "tee_type": "snp",
  "runtime_class": "kata-qemu-snp-runtime-rs",
  "quote": null,
  "cc_eventlog": null,
  "nonce": "<64-lowercase-hex>",
  "report_data_input": "kubetee.attestation.v1",
  "pod": "<serving-replica>",
  "keyset": {
    "subject": "kubetee.attestation.v1/llm.kubetee.ai",
    "not_after": "<RFC3339>",
    "tls_public_keys": [{"domain": "llm.kubetee.ai", "spki_sha256": "<hex>"}],
    "signing_keys": [],
    "e2ee_keys": []
  },
  "bindings": {
    "version": "kubetee.attestation.v1",
    "report_data_statement": "{\"keyset_digest\":\"sha256:<hex>\",\"nonce\":\"<64-hex>\",\"purpose\":\"kubetee.attestation.v1\"}",
    "keyset_digest": "sha256:<hex>"
  },
  "evidence": {
    "quote": null,
    "quote_report_data": null,
    "event_log": null,
    "snp": {
      "schema": "kubetee.snp-evidence/1",
      "attestation_report": {
        "version": 5,
        "vmpl": 0,
        "report_data": ["64 unsigned byte values"],
        "measurement": ["48 unsigned byte values"],
        "host_data": ["32 unsigned byte values"],
        "signature": {"r": ["72 unsigned byte values"], "s": ["72 unsigned byte values"]}
      },
      "cert_chain": [{"cert_type": "<CoCo serialization label>", "data": ["DER byte values"]}]
    },
    "tdx": null,
    "vm_config": {"role": "litellm", "files": {}, "agent_policy_claims": {}}
  },
  "tls_possession": {
    "tls_signature": "<base64 signature>",
    "tls_signature_alg": "RS256",
    "tls_signature_input": "sha256(nonce)",
    "tls_cert_sha256": "<hex DER-certificate digest>"
  },
  "appraisal": {"ear_token": "<optional boot Trustee EAR>", "ar4si": {}}
}
```

The producer preserves CoCo's structured report and certificate chain rather
than translating them into a quote or base64 string. Numeric fields are JSON
unsigned-byte arrays. A `cert_type` label is not proof that a certificate is
an ARK, ASK or VCEK; verify the actual chain and chip relation.

**Roles and TEEs are independent; `evidence` is disjoint per TEE.** The role
(`litellm`, `nim-terminator`) names *which guest* is attesting. The TEE names
*how* it attests, and is a property of each deployment record — `nim-terminator`
is not a TDX role and may be deployed on AMD SEV-SNP nodes as well as Intel TDX
nodes.

Only one half of `evidence` is populated per response, determined by the TEE:

- **AMD SEV-SNP guest** fills `evidence.snp`; `quote` / `quote_report_data` /
  `event_log` / `tdx` stay null, because an SNP report is not a quote.
- **Intel TDX guest** fills `quote` (the Intel DCAP quote carrying TDINFO
  `MRTD`, `RTMR0–3`, `MRCONFIGID`), `event_log` (the TCC event log whose replay
  reproduces `RTMR0–3`) and `evidence.tdx` (`schema: kubetee.tdx-evidence/1`,
  parallel to `snp`); `snp` stays null.

A verifier must reject a response whose `tee` / `tee_type` / `runtime_class`
disagree with the populated half.

**What this surface serves today.** This v1 contract covers exactly one role:
the `litellm` **gateway**, which is AMD SEV-SNP. Both the complete endpoint and
the inline completion evidence bind SNP `report_data` against the
`kubetee.attestation.v1/llm.kubetee.ai` keyset and populate `evidence.snp`; the
`quote` / `cc_eventlog` / `tdx` members are null in those responses because an
SNP guest emits no quote. The `nim-terminator` backend is **not** exposed on
either surface yet; §"Backend evidence" below is the agreed contract for it and
has not been observed in a response.

**These `quote` members are the TDX quote slot, not inert placeholders.** On an
earlier deployment the gateway ran on Intel TDX and `x-kubetee-attestation-quote`
carried a real 5,243-byte TDX quote (REPORTDATA = `sha512(nonce)`, the legacy
`kubetee.attestation` binding). That path ended when the gateway moved TDX →
AMD SEV-SNP and the contract migrated to `KUBETEE_ATTESTATION_V1`, whose
producer emits structured `evidence.snp` and **rejects a TDX quote**. A TDX
guest — the legacy gateway, or the `nim-terminator` TDX backend under the agreed
contract — is what populates `quote` / `cc_eventlog` / `tdx`. Read the populated
half, not the presence of these keys, as the signal.

The signing algorithm shown in the production keyset is RS256. A verifier
can support ES256 as a permitted key type for an appropriate serving leaf,
but must not accept a mismatch between declared algorithm and certificate
public key.

`appraisal` can be omitted if the boot EAR is unavailable. That does not
remove the need for the report, request binding and TLS-possession checks.

Errors are fail-closed for the evidence surface: a malformed nonce returns
400, and inability to obtain evidence returns 502. A gateway can continue
ordinary inference while evidence is unavailable; this is not a successful
attestation.

---

## 3. Inline evidence on inference responses

Opt in by sending the **same nonce in the request**:

```bash
NONCE="$(openssl rand -hex 32)"
curl --fail-with-body \
  'https://llm.kubetee.ai/v1/chat/completions' \
  -H "Authorization: Bearer ${KUBETEE_KEY}" \
  -H 'Content-Type: application/json' \
  -H "X-KubeTEE-Nonce: ${NONCE}" \
  --data '{
    "model": "moonshotai/kimi-k3.1-pro",
    "messages": [{"role": "user", "content": "Reply with OK."}],
    "reasoning_effort": "low",
    "temperature": 0,
    "max_tokens": 20
  }' \
  --dump-header response-headers.txt \
  --output response-body.json
```

An API key is required for inference, not to fetch the public report. This
example uses modest Kimi token/reasoning budgets; it is not a claim of
SayGM worker acceptance or of model-output attestation.

The inline headers arrive on both streaming and non-streaming responses.
Streaming carries evidence in the initial SSE response headers, so capture
headers before consuming the event stream. The completion body remains
ordinary OpenAI-compatible JSON/SSE.

### Current response headers

| Header | Meaning |
|---|---|
| `X-KubeTEE-Nonce` | 64-hex caller nonce, lowercased. |
| `X-KubeTEE-Attestation-Tee` | `snp` for this gateway. |
| `X-KubeTEE-Runtime-Class` | `kata-qemu-snp-runtime-rs`. |
| `X-KubeTEE-Attestation-SNP` | Base64url(JSON) of exactly `evidence.snp`: native report plus certificate chain. It does not carry `vm_config`. |
| `X-KubeTEE-Attestation-SNP-Encoding` | `base64url-json`; add required base64 padding and decode JSON, then validate the schema and field sizes. |
| `X-KubeTEE-Attestation-Report-Data` | Base64 of the 64-byte signed binding value. |
| `X-KubeTEE-Report-Data-Input` | `kubetee.attestation.v1`. |
| `X-KubeTEE-Binding-Statement` | Exact JCS statement to hash. |
| `X-KubeTEE-Binding-Keyset-Digest` | Served digest of the keyset; independently recompute it from that keyset. |
| `X-KubeTEE-TLS-Signature`, `X-KubeTEE-TLS-Signature-Alg`, `X-KubeTEE-TLS-Signature-Input` | TLS-key nonce signature, algorithm and signature-input convention. |
| `X-KubeTEE-TLS-Cert-SHA256` | SHA-256 of the serving leaf's DER, to match the caller's own TLS certificate. |
| `X-KubeTEE-Backend`, `X-KubeTEE-Backend-Endpoint` | Routed model/backend identity. |
| `X-KubeTEE-Backend-Attested` | `boot-time (Trustee EAR; east-west mTLS)` (degraded/freshness gap) or `hardware-evidence (shared epoch cache)` (fresh backend evidence). A boundary statement; the hardware label means the backend's shared-epoch evidence is present, not that the model-output bytes are signed. |
| `X-KubeTEE-Backend-Evidence` | Base64url (no padding) of one self-describing JSON envelope for the backend role (see "Backend evidence"). Decode once and branch on `schema`/`tee`. |
| `X-KubeTEE-Backend-Evidence-Location`, `…-Reason` | Sent instead of `X-KubeTEE-Backend-Evidence` when the envelope exceeds the inline header budget; fetch the bulk bundle at `Location`. |
| `X-KubeTEE-Backend-Evidence-Subject`, `…-Schema`, `…-Tee`, `…-Digest`, `…-Source` | Flat discriminators so a client can filter without decoding: whose evidence, what schema, which TEE, the quote/`snp` digest, and `cache`/`fetch` provenance. |
| `X-KubeTEE-Backend-Evidence-Error` | Backend evidence unavailable — boundary label only. A freshness gap, not a breach. |
| `X-KubeTEE-Breaker-State` | `OPEN` (measurement drift — trip) or `DEGRADED` (freshness gap). Absent when healthy. |
| `X-KubeTEE-Breaker-Trip`, `X-KubeTEE-Breaker-Action` | On `OPEN`: the drift reason and `auto-block (HTTP 503)`. |
| `X-KubeTEE-Breaker-Reason` | On `DEGRADED`: the freshness-gap reason (still serving). |
| `X-KubeTEE-Attestation-Error` | Error when inline gateway evidence cannot be supplied; ordinary inference need not fail with it. |

The native inline SNP value has a header-size limit. If evidence cannot be
framed safely, the endpoint instructs the client to obtain the standalone
bundle rather than silently accepting a truncated report.

Without `X-KubeTEE-Nonce`, a request is an ordinary OpenAI call with no
additional report work. A malformed nonce produces an inline evidence error
rather than fabricating a report.

### Backend evidence for `nim-terminator` (agreed contract — relay to caller **not yet wired**)

Everything above serves the `litellm` gateway role. The SGLang backend's own
**in-guest evidence surface is deployed** — `GET /kubetee/evidence` (and the
`/v1/kubetee/evidence` relay alias) on its in-guest strict-mTLS `:8443`
listener returns the `{quote, cc_eventlog, keyset, bindings, tee_pubkey,
signature}` envelope; this is the surface the 2026-11-25 capture exercised, and
the measured gateway calls it as an mTLS client (east-west identity). What is
**not yet wired** is the caller-facing relay described below — surfacing that
backend envelope to the *caller* through a `X-KubeTEE-Backend-Evidence` response
header on `/v1/chat/completions`. The backend cannot reuse the gateway surface
unchanged: the gateway terminates the caller's TLS, so the gateway's possession
proof does not bind the backend, and the two roles sign against different
keysets. The agreed contract is a **separate surface for the backend role**,
relayed by the gateway.

**Request surface is one header.** The caller sends `X-KubeTEE-Nonce` (64
lowercase hex) on `POST /v1/chat/completions` — the same header already used for
inline gateway evidence. There is no second evidence-request header, no
pre-flight call, and no per-request quote. Everything the caller needs to verify
the **backend** arrives in **one response header**.

**Response surface is one envelope.** The gateway emits a single
self-describing header, `X-KubeTEE-Backend-Evidence`: base64url (no padding) of
a JSON envelope. The client decodes one blob and branches on its `schema` and
`tee` fields — never on a header name — so a TDX backend and an SNP backend
share one client code path. When the envelope would exceed the inline header
budget, the gateway instead sends `X-KubeTEE-Backend-Evidence-Location` (the
bulk bundle URL) plus `X-KubeTEE-Backend-Evidence-Reason`; the client fetches
the same envelope there.

Envelope layout (base64url-decoded):

```json
{
  "subject": "nim-terminator",
  "schema": "kubetee.backend-evidence/1",
  "tee": "tdx",
  "role": "image-gen",
  "runtime_class": "kata-qemu-nvidia-gpu-tdx-runtime-rs",
  "epoch": {"id": "<epoch_id>", "issued_at": "<RFC3339>", "valid_until": "<RFC3339>"},
  "digest": "<sha256 of `quote` or of the native `snp` bytes>",
  "report_data": ["64 unsigned byte values"],
  "report_data_statement": "<exact JCS statement hashed into report_data>",
  "cert_chain": [{"cert_type": "<label>", "data": ["DER byte values"]}],
  "signature": "<base64 per-request signature, see below>",
  "quote": "<base64 Intel DCAP quote, tee=tdx only>",
  "event_log": "<base64 TCC/CC event log, tee=tdx only>",
  "snp": {"schema": "kubetee.snp-evidence/1", "attestation_report": {}, "cert_chain": []}
}
```

Exactly one of `quote`/`event_log` (TDX) or `snp` (SNP) is populated; the other
is absent. Reject a response whose `tee` disagrees with the populated half.

| Element | Value |
|---|---|
| Bulk endpoint | `GET /v1/attestation/backend?role=nim-terminator&nonce=<64-hex>` — returns the same envelope plus `vm_config` (`role: nim-terminator`, measured `files`, `agent_policy_claims`). Bulk evidence is fetched only when the inline envelope is too large or the caller wants `vm_config`. |
| Inline on completions | the envelope above (or its `Location` redirect when oversized). No separate "small proof" header set — one envelope. |
| Report-data binding | `SHA-256(JCS(statement)) ‖ 32 zero bytes`, the same 64-byte convention as §4, over an **epoch statement** |
| Backend signing key | `tee-pubkey` — the backend's **per-epoch evidence-signing key** (Ed25519), distinct from its TLS serving key and from the gateway's keys. Its public half is bound into the epoch statement via `keyset_digest`, so it is covered by the hardware quote. |

**Two-layer freshness.** A hardware quote is sealed at mint: the caller's nonce
cannot go inside `report_data` if one quote is to serve many callers. Freshness
is therefore split:

1. **Hardware freshness (epoch)** — one quote per **epoch** (≤ 1 mint per 5
   minutes per replica, single-flight), whose `report_data` binds the epoch
   statement `{"epoch_id","issued_at","valid_until","keyset_digest","purpose"}`.
   The quote is cached **in the serving guest's memory** and not recomputed until
   `valid_until` passes. Two epochs (current + previous) are retained so a
   client that fetched just before rotation can still resolve its `epoch_id`.
2. **Caller freshness (per-request)** — `signature` is the backend's `tee-pubkey`
   (Ed25519) over the concatenation
   `SHA-256(quote) ‖ SHA-256(nonce) ‖ epoch_id ‖ counter`, where `counter` is a
   monotonic per-epoch request counter the backend increments on every signed
   response. The nonce binding defeats quote reuse at a different caller; the
   counter defeats within-epoch replay of the *same* caller's signed response.

Verify the signature with the `tee-pubkey` whose hash is committed in the
epoch statement's `keyset_digest`. A cached quote is non-replayable at a
different caller or a different request because the signature covers
`quote ‖ nonce ‖ epoch_id ‖ counter`.

`X-KubeTEE-Attestation-Mode: nonce-bound` requests a quote whose `report_data`
binds that caller's nonce directly (the strongest form). It bypasses the epoch
cache and is rate-limited to **1 per 5 minutes per client key**; exceeding it
returns `429` with `Retry-After`. Ordinary completions ride the cached epoch.

**Residual limit, stated honestly.** A hardware report carries no timestamp, and
the serving keys are KBS-released rather than proved generated in-guest per boot
(see §1 "What this does not prove"). The 5-minute window therefore bounds
freshness *in time*, not *per boot*: replay is defeated by `valid_until`, the
client's clock, and the monotonic counter, not by the report itself. Closing
that last gap requires a keypair generated in-guest per boot and named in
`report_data`. Not claimed until implemented.

Also, the gateway is a relay here: it does not prove the model-output bytes came
from the backend's GPU. The quote attests composition and freshness of the
backend guest; the linkage to a given completion is the east-west mTLS hop plus
`X-KubeTEE-Backend`, which is a trust-the-gateway statement, not a signature over
the output.

### Boot Trustee EAR — bulk bundles only

The **boot-time Trustee EAR** (the appraisal over the guest's measured
composition, minted once at start) is **not** a per-request freshness proof and
is never presented as one. The gateway exposes it under a narrow contract:

| Boundary | Rule |
|---|---|
| Where it appears | **Bulk** evidence bundles only (`GET /v1/attestation`, `GET /v1/attestation/backend`), as `appraisal.ear_token` + `appraisal.ar4si`. It is **omitted** from inline per-completion envelopes. |
| What it covers | Boot composition of the guest that minted it — measured launch inputs + InitData at start. It says nothing about a later request, a later prompt, or the model-output bytes. |
| Freshness | One EAR per **boot**, not per request. Its value is bounded by the boot, not by a nonce. Always pair it with the per-request Layer-2 signature. |
| Breaker relationship | A fresh boot EAR **never clears a tripped circuit breaker** (see below). Recovery is an operator action, not an evidence event — otherwise a reboot would launder a drift trip. |

The EAR is a JWT signed by the Trustee Attestation Service (AS). Verifiers that
want it fetch the **AS JWKS** to check the signature. Three trust anchors cover
the whole contract — do not collapse them into one check:

| Trust anchor | Verifies | Key source |
|---|---|---|
| AMD root (ARK/ASK/VCEK) | the SNP report is genuine AMD hardware | AMD root material, per processor generation |
| Trustee AS JWKS | the boot EAR is a genuine Trustee appraisal | AS published JWKS |
| Registry Ed25519 key | the reference measures are our approved values | `key_url` in the registry, out-of-band |

A successful hardware appraisal (EAR `affirming`) is **not** by itself proof of
resource authorization or of per-request freshness. Each trust anchor is a
separate verification; passing one does not imply the others.

### Circuit breaker — what a client sees

The gateway runs a **measurement-drift circuit breaker** over the backend
envelope. It is layered so one failure mode never masks another:

| Condition | Class | Client sees | Serving |
|---|---|---|---|
| **Measurement drift** (role / InitData `MRCONFIGID` / `MRTD` / `RTMR0-3` / OVMF changes vs the pinned reference) | **TRIP** — breach signal | `X-KubeTEE-Breaker-State: OPEN`, `X-KubeTEE-Breaker-Trip: <reason>`, `X-KubeTEE-Breaker-Action: auto-block (HTTP 503)` | **Blocked.** The gateway auto-blocks the row (`POST /model/block`) and alerts. This is a tamper/misdeploy signal — the backend must not serve. |
| **Freshness gap** (epoch absent/expired, or hardware evidence momentarily unavailable) | **DEGRADE** — evidence gap, not drift | `X-KubeTEE-Breaker-State: DEGRADED`, `X-KubeTEE-Breaker-Reason: <reason>` (or `X-KubeTEE-Backend-Evidence-Error` on a hard fetch miss) | **Still serving**, downgraded to the boot boundary label. Never blocks a serving backend on a mere freshness gap. |

Behavior a client should rely on:

- **A TRIP is fail-closed and sticky.** Once OPEN it stays OPEN until an
  operator clears it; a subsequent healthy evidence sample does **not** auto-reset
  the breaker, and a fresh boot EAR does not either. Treat `OPEN` as "this
  backend's composition changed — stop accepting its output" and surface it.
- **A DEGRADE is not a breach.** Keep the response, but mark the evidence
  boundary (`boot-time (Trustee EAR; east-west mTLS)`) and carry the reason. Do
  not treat a DEGRADED response as attested-with-fresh-backend-hardware-evidence.
- **Drift is measured against the pinned reference**, never against a value the
  serving guest supplies. A guest cannot talk its way past a trip by relaying a
  matching summary — the registers are read from the quote the client verifies.
- The breaker is a **detective/enforcement layer** on top of the authoritative
  KBS resource-policy gate, which already blocks a drifted guest's certificate
  fetch at the source. Two independent layers; a bypass of one is caught by the
  other.

---

## 4. Verification checklist

The full rules and exact reference values are in
[ATTESTATION-SPEC-v1.md](./ATTESTATION-SPEC-v1.md). Use a native SNP
implementation such as stock **`sev 7.1.0`**, with SNP/OpenSSL support.
No patch to CoCo, Trustee or KBS is needed to consume this contract.

1. **Explicit type and framing.** Require `tee=snp`, `tee_type=snp`,
   `runtime_class=kata-qemu-snp-runtime-rs` and
   `evidence.snp.schema=kubetee.snp-evidence/1`.
2. **AMD authenticity.** Support report versions 3–5; require VMPL0 and
   expected field lengths. Validate ARK/ASK/VCEK by cryptographic roles,
   AMD root and processor/chip generation. Verify the report signature and
   approved reported TCB. Certificate labels alone are insufficient.
3. **Composition and policy.** Compare the signed report's 48-byte launch
   `measurement`, 32-byte `host_data`, guest policy and TCB with the signed
   registry. Require debug-off, migration-agent-off and measured denied
   guest-control operations; text declaring these alone is not enough.
4. **Keyset digest.** Canonicalize the served keyset using RFC 8785 JCS,
   compute its SHA-256, and check the resulting value in the statement.
   `signing_keys` is empty in this deployment.
5. **Binding.** Compute:

   ```python
   expected = hashlib.sha256(
       payload["bindings"]["report_data_statement"].encode("utf-8")
   ).digest() + bytes(32)
   actual = bytes(
       payload["evidence"]["snp"]["attestation_report"]["report_data"]
   )
   assert actual == expected
   ```

   This is deliberately a fragment, not a complete verifier. The report's
   signature and provenance checks must precede acceptance; parsing a native
   AMD report must not be replaced by slicing a different evidence format.
6. **TLS possession.** Read the leaf directly from your TLS socket, hash its
   DER and SPKI, match the keyset plus `tls_cert_sha256`, and verify the
   nonce signature. The report signature, TLS signature and registry
   signature are three separate trust operations.
7. **Registry.** Validate the schema, canonicalize the registry without its
   `signature` member, and verify its Ed25519 signature using the separately
   published public key.
8. **Optional EAR.** Validate the boot RCAR's native evidence and Trustee
   policy if present. Do not substitute it for the caller's nonce binding or
   the current connection's possession proof.

Reject missing evidence, unknown types, certificate failures, report
mismatches, bad guest policy, unapproved measurements and TLS mismatches.
Do not downgrade failed native SNP verification to a transport or key-label
check.

The AMD root material, guest reference and processor expectations must be
maintained independently. KubeTEE's signed registry identifies the approved
software/guest reference; it cannot solely establish AMD's root of trust.

### Runnable backend-evidence checklist

The gateway-side checks above apply to the SNP gateway. For the **relayed
backend envelope** (`X-KubeTEE-Backend-Evidence`), the following is a runnable
verification skeleton. It is deliberately a checklist, not a complete verifier:
hardware-report signature verification, chain validation and registry
signature verification are marked `# VERIFY` and must be filled from a native
implementation before you accept anything. Parsing must never be swapped for a
slicing shortcut on a different evidence format.

```python
import base64, hashlib, json
from nacl.signing import VerifyKey  # Ed25519 for the tee-pubkey signature

def b64url_decode(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))

def verify_backend_envelope(header_value: str, nonce_hex: str, *,
                            registry, as_jwks, amd_root):
    env = json.loads(b64url_decode(header_value))

    # 1. Self-describing type + disjoint evidence.
    assert env["schema"] == "kubetee.backend-evidence/1"
    tdx = "quote" in env and env.get("quote")
    snp = env.get("snp")
    assert (tdx != bool(snp)), "exactly one TEE half populated"
    assert (env["tee"] == "tdx") == bool(tdx), "tee disagrees with populated half"

    # 2. Freshness split.
    epoch = env["epoch"]
    assert epoch["valid_until"] > now_utc(), "epoch expired"          # Layer 1 window
    # Layer 2: per-request signature over quote||nonce||epoch_id||counter
    msg = (hashlib.sha256(b64url_decode(env["quote"]) if tdx else canonical(env["snp"])).digest()
           + hashlib.sha256(bytes.fromhex(nonce_hex)).digest()
           + epoch["id"].encode()
           + env["counter"].to_bytes(8, "big"))
    tee_pubkey = registry_key_for(epoch, env["role"])                 # bound via keyset_digest
    VerifyKey(tee_pubkey).verify(msg, b64url_decode(env["signature"])) # Ed25519

    # 3. Report-data binding (64-byte convention).
    expected = hashlib.sha256(env["report_data_statement"].encode()).digest() + bytes(32)
    assert bytes(env["report_data"]) == expected, "report_data does not bind statement"

    # 4. Hardware authenticity + composition against the SIGNED registry.
    if tdx:
        # VERIFY: Intel DCAP quote signature + chain, and read TDINFO registers.
        regs = verify_tdx_quote(env["quote"], env["cert_chain"])        # MRTD/RTMR0-3/MRCONFIGID
    else:
        # VERIFY: AMD ARK/ASK/VCEK chain + report signature (sev-snp), read
        # measurement/host_data/policy.
        regs = verify_snp_report(env["snp"], amd_root)
    ref = registry.reference_for(role=env["role"], tee=env["tee"])      # VERIFY registry Ed25519 sig
    assert regs["mrconfigid"] == ref["mrconfigid"], "InitData drift"
    for field in ("mrtd", "rtmr0", "rtmr1", "rtmr2", "rtmr3"):
        if ref.get(field):                                             # enforced only if captured
            assert regs[field] == ref[field], f"{field} drift"

    # 5. Boot EAR (bulk bundles only) — verify AS signature + Trustee policy,
    #    but NEVER use it to clear a breaker trip or replace Layer 2.
    if env.get("appraisal", {}).get("ear_token"):
        verify_ear_jwt(env["appraisal"]["ear_token"], as_jwks)          # VERIFY

    return True
```

Every `VERIFY` comment is a real cryptographic operation you must source from a
native TDX/SNP implementation. A response that fails any assertion must be
rejected outright — do not downgrade to a transport or key-label check.

---

## 5. Current serving-key custody

Traefik uses Gateway API TLS **Passthrough** to the LiteLLM process, and
Cloudflare is DNS-only. The public CA-valid TLS identity is retrieved by
the measured gateway bootstrap through CDH loopback into Memory
`emptyDir` at `/etc/tls`. It is not directly mounted as a traditional
Kubernetes TLS Secret.

The gateway obtains this identity at each start after appraisal.
The registry's `fresh_certificate_per_boot: true` field describes this
current identity retrieval; it does **not** assert a distinct keypair is
generated inside each new guest. The key can be reusable. Trustee/KBS
appraisal, resource authorization and its privileged storage/administration
remain part of the security boundary.

The gateway's outbound mTLS identity is separately fetched into
container-local `/run/kubetee-eastwest`. Its backend CA checks and client
identity are loaded by measured image-local code only for the approved
east-west trust anchor.

Backend serving-key custody (2026-11-23): on backends deployed with the
measured **Granian mTLS frontend**, the model server itself holds the
CDH-released server identity and terminates strict mTLS inside the guest —
there is no transport proxy in the trust path, and the health probe surface
is a separate loopback-only HTTP listener exposing `/health` and
`/health_generate` only. Backends still on the earlier in-CVM HAProxy
frontend carry an equivalent evidence contract with one additional in-guest
process; they migrate as their images rebuild. Neither frontend's key is
proved generated inside the guest — see the custody limits above.

`signing_keys: []` does not expose the offline measurement public key;
obtain that public key from the registry's `key_url`.

---

## 6. Reference measures and container provenance

The exact **measures and the container used for the attestation** are
published per role in the signed
[`tee-measurements.json`](https://kubetee.ai/.well-known/tee-measurements.json)
registry (Ed25519-signed projection; verification key via its `key_url`),
with a human twin per record in this directory.

| Role | Record | Human twin | Status |
|---|---|---|---|
| `litellm` (SNP gateway) | [`tee-measurements.json`](https://kubetee.ai/.well-known/tee-measurements.json) | [ATTESTATION-SPEC-v1.md](./ATTESTATION-SPEC-v1.md) §2–3 | **Active** (signed) |
| `nim-terminator` (SGLang backend, TDX/NVIDIA-CC) | [`tee-measurements-sglang.tdx.json`](https://kubetee.ai/.well-known/tee-measurements-sglang.tdx.json) | [ATTESTATION-REFERENCE-MEASURES-SGLANG.md](./ATTESTATION-REFERENCE-MEASURES-SGLANG.md) | **Active** (signed) — all six registers (`MRTD`/`MRCONFIGID`/`RTMR0-3`) captured from the booted guest's quote + CCEL replay (report-data binding MATCH) and cross-validated; signed Ed25519 (`key_id kubetee-measurements-2026-11-22`) and published at the role-scoped `.tdx.` URL. `MRTD` is captured-and-cross-checked (eventlog + binding), not independently recomputed bit-for-bit from firmware inputs (`tdx-measure` has no TDX MRTD mode). |

**Measurement-drift boundary.** "A drifted backend cannot serve" (§1) is
enforced against the **captured** pins above: `MRCONFIGID` (which fixes the
whole InitData — role, measured agent policy, KBS endpoint), OVMF firmware
digest, and the measured container/shim/image set. The TDX launch registers
`MRTD`/`RTMR0-3` are captured and published, but the breaker enforces each one
**only when its expectation is set** (a `None` expectation cannot fire — the
detective always skips an unset field). In the shipped verifier those values are
opt-in via env (`KUBETEE_BACKEND_EXPECTED_MRTD`/`_RTMR0-3`, which default to
unset), so firmware/boot-measurement drift is caught only after those are
configured; `MRCONFIGID` and OVMF are enforced by default. Auto-block itself is
**separately opt-in** (`KUBETEE_BREAKER_ENFORCE=1`, default `0` = detect + 503
surface only). The boundary is stated in the machine record (`capture_blockers`)
and mirrored in the gateway verifier's expectations.

### Our SGLang fork (the measured backend source)

The backend engine is built from **KubeTEE's SGLang fork —
[`https://github.com/KubeTEE-AI/sglang`](https://github.com/KubeTEE-AI/sglang)**
(public fork of [`sgl-project/sglang`](https://github.com/sgl-project/sglang),
default branch `kubetee/mimo-penfix`). The strict-mTLS transport (native Granian
mTLS on `:8443` + health-only listener on `:8000`) is **fork source code inside
the attested image**, not a sidecar or proxy, so it is covered by the guest
measurement. Images are built **only** in GitHub Actions (GitHub-hosted
runners) and consumed `@sha256:`-pinned; the fork's
`docker/kubetee-mtls-overlay/patches/by-sha-<commit>/` layout pins each
transport patch to its exact upstream base commit with pre/postimage sha256
tripwires, so upstream drift fails the build rather than partially patching.

Current identity (full provenance in
[ATTESTATION-REFERENCE-MEASURES-SGLANG.md](./ATTESTATION-REFERENCE-MEASURES-SGLANG.md)):

- Deployed strict-mTLS canary: `ghcr.io/kubetee-ai/sglang:kimi-k31-granian-mtls-45228495550-bf52f822@sha256:d808dd7bec0d1ebb3f6942e47f636a69c57ec4d74497eaad4a81030da0a0437a`
  (source `kubetee/kimi-k31-granian-mtls-day0` @ `bf52f8223b88`,
  [run 45228495550](https://github.com/KubeTEE-AI/sglang/actions/runs/45228495550),
  validated 2026-11-23)
- Model-agnostic transport base images `mtls-297e54fd-20261124@sha256:c2be72eb…`
  (v0.5.23 base) and `mtls-3117f580-20261124@sha256:7978ad60…` (nightly base) —
  transport layer only, no model-layer patches.

A verifier comparing the backend's live evidence should expect the published
MRCONFIGID (SHA-384 of the uncompressed InitData TOML) and the MRTD/RTMR0-3
values from the record — never a value supplied only by the serving guest.
The record's values are **captured and cross-validated** (read from a booted
guest's quote and CC event-log replay) and the record is **signed and
published** at [`tee-measurements-sglang.tdx.json`](https://kubetee.ai/.well-known/tee-measurements-sglang.tdx.json).
