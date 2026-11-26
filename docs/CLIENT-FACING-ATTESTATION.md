# Client attestation for `llm.kubetee.ai`

How to fetch evidence from `llm.kubetee.ai`, verify it, and compare it against
KubeTEE's published reference values. This is everything a client (Chutes,
SayGM, or any consumer) needs. Protocol details are in
[ATTESTATION-SPEC-v1.md](./ATTESTATION-SPEC-v1.md) (partner contract) and the
backend reference values are in
[ATTESTATION-REFERENCE-MEASURES-SGLANG.md](./ATTESTATION-REFERENCE-MEASURES-SGLANG.md).

**Current deployment:** the gateway is an **AMD SEV-SNP** Kata guest
(`kata-qemu-snp-runtime-rs`); the SGLang backend hop is **Intel TDX**
(`kata-qemu-nvidia-gpu-tdx-runtime-rs`). Evidence is disjoint per TEE: the
gateway fills `evidence.snp`, the backend fills `quote` + `event_log` +
`evidence.tdx`. Reject any response whose `tee` disagrees with the populated
half.

---

## 1. The verification model in one page

| Claim | Evidence |
|---|---|
| The serving endpoint is a genuine AMD SNP confidential guest | Signed SNP report and ARK/ASK/VCEK chain, independently verified for the relevant processor generation. |
| The evidence is fresh for this request | The report contains the hash of the caller's v1 nonce/keyset statement, not a reused fixed challenge. |
| The same guest terminates the caller's TLS connection | The gateway signs the nonce with its serving key; you verify it against the leaf certificate of your own TLS session and compare that key with the keyset. |
| The approved guest composition is running | Launch `MEASUREMENT`, `HOST_DATA`, guest policy and TCB compared with the independently signed reference registry. |
| The SGLang backend runs the approved composition | The backend's measures (MRTD/RTMR0-3/MRCONFIGID) live as records in the signed registry [`tee-measurements-registry.json`](https://kubetee.ai/.well-known/tee-measurements-registry.json); the evidence is legitimate iff its registers match **any active record** for the same `tee`. |
| Which serving replica minted the report | The endpoint's `pod` field and the TLS-session binding. A standalone request is load-balanced; it does not identify a separate chat request's replica. |

### What this does not prove

- An SNP report is not an Intel quote; Intel DCAP/ITA does not verify it (and
  vice versa).
- It does not prove a new hardware keypair is generated for every boot — the
  serving identity is retrieved after appraisal at start and can persist.
- Reusable, KBS-released keys are not a zero-operator-trust claim; KBS
  administration and trusted storage remain in the trust boundary.
- No fresh per-request backend **GPU** quote is supplied today (the backend is
  boot-attested with a per-epoch quote; the per-backend fresh-evidence contract
  is in implementation, not deployed).
- The circuit breaker catches **launch-composition drift** against the pinned
  reference — not runtime tampering inside an already-measured guest, and not
  model-output bytes. A drifted launch is caught; a compromised but
  identically-launched guest is caught only by the measured guest policy and
  the KBS release gate.
- The endpoint's hardware evidence is adjacent to the response identity; it is
  not a signature over the full model-output bytes.

---

## 2. Standalone report endpoint (gateway)

Send exactly 64 lowercase hexadecimal characters as the caller's nonce:

```bash
NONCE="$(openssl rand -hex 32)"  # any 32-byte CSPRNG output works; openssl is just one nonce source
curl --fail-with-body \
  --get 'https://llm.kubetee.ai/v1/attestation' \
  --data-urlencode "nonce=${NONCE}" \
  --output attestation.json
```

Save the response only with the original exact byte strings; a verifier uses
`bindings.report_data_statement` exactly as received. The endpoint is public but
exposes no keys or protected model inputs. Errors are fail-closed: a malformed
nonce returns 400, inability to obtain evidence returns 502.

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

Numeric fields are JSON unsigned-byte arrays. A `cert_type` label is not proof
that a certificate is an ARK, ASK or VCEK; verify the actual chain and chip
relation. The signing algorithm in the production keyset is RS256; ES256 is
permitted for an appropriate serving leaf, but never accept a mismatch between
declared algorithm and certificate public key. `appraisal` can be omitted if the
boot EAR is unavailable — that does not remove the need for the report, request
binding and TLS-possession checks.

For an Intel TDX backend response, `quote` (Intel DCAP quote carrying TDINFO
`MRTD`, `RTMR0–3`, `MRCONFIGID`), `event_log` (TCC event log whose replay
reproduces `RTMR0–3`) and `evidence.tdx` are populated instead of `evidence.snp`.

---

## 3. Inline evidence on inference responses

Opt in by sending the **same nonce in the request**:

```bash
NONCE="$(openssl rand -hex 32)"  # any 32-byte CSPRNG output works; openssl is just one nonce source
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

An API key is required for inference, not to fetch the public report. The inline
headers arrive on both streaming and non-streaming responses. Streaming carries
evidence in the initial SSE response headers, so capture headers before
consuming the event stream. The completion body remains ordinary
OpenAI-compatible JSON/SSE. Without `X-KubeTEE-Nonce`, the request is an ordinary
OpenAI call.

### Response headers

| Header | Meaning |
|---|---|
| `X-KubeTEE-Nonce` | 64-hex caller nonce, lowercased. |
| `X-KubeTEE-Attestation-Tee` / `X-KubeTEE-Runtime-Class` | `snp` / `kata-qemu-snp-runtime-rs` for this gateway. |
| `X-KubeTEE-Attestation-SNP` | Base64url(JSON) of exactly `evidence.snp`: native report plus certificate chain. Add required base64 padding, decode JSON, validate schema and field sizes. |
| `X-KubeTEE-Attestation-SNP-Encoding` | `base64url-json`. |
| `X-KubeTEE-Attestation-Report-Data` | Base64 of the 64-byte signed binding value. |
| `X-KubeTEE-Report-Data-Input` | `kubetee.attestation.v1`. |
| `X-KubeTEE-Binding-Statement` | Exact JCS statement to hash. |
| `X-KubeTEE-Binding-Keyset-Digest` | Served digest of the keyset; independently recompute it from that keyset. |
| `X-KubeTEE-TLS-Signature`, `X-KubeTEE-TLS-Signature-Alg`, `X-KubeTEE-TLS-Signature-Input` | TLS-key nonce signature, algorithm and signature-input convention. |
| `X-KubeTEE-TLS-Cert-SHA256` | SHA-256 of the serving leaf's DER, to match the caller's own TLS certificate. |
| `X-KubeTEE-Backend`, `X-KubeTEE-Backend-Endpoint` | Routed model/backend identity. |
| `X-KubeTEE-Backend-Attested` | `boot-time (Trustee EAR; east-west mTLS)` (evidence gap) or `hardware-evidence (shared epoch cache)` (fresh backend evidence). The label means the backend's shared-epoch evidence is present, not that model-output bytes are signed. |
| `X-KubeTEE-Backend-Evidence` | Base64url (no padding) of one self-describing JSON envelope for the backend role (see §4). Decode once and branch on `schema`/`tee`. |
| `X-KubeTEE-Backend-Evidence-Location`, `…-Reason` | Sent instead of `X-KubeTEE-Backend-Evidence` when the envelope exceeds the inline header budget; fetch the bulk bundle at `Location`. |
| `X-KubeTEE-Backend-Evidence-Subject`, `…-Schema`, `…-Tee`, `…-Digest`, `…-Source` | Flat discriminators so you can filter without decoding: whose evidence, what schema, which TEE, the quote/`snp` digest, and `cache`/`fetch` provenance. |
| `X-KubeTEE-Backend-Evidence-Error` | Backend evidence unavailable — a freshness gap, not a breach. |
| `X-KubeTEE-Breaker-State` | `OPEN` (measurement drift — trip) or `DEGRADED` (freshness gap). Absent when healthy. |
| `X-KubeTEE-Breaker-Trip`, `X-KubeTEE-Breaker-Action` | On `OPEN`: the drift reason and `auto-block (HTTP 503)`. |
| `X-KubeTEE-Breaker-Reason` | On `DEGRADED`: the freshness-gap reason (still serving). |
| `X-KubeTEE-Attestation-Error` | Error when inline gateway evidence cannot be supplied; ordinary inference need not fail with it. |

If evidence cannot be framed safely within the header-size limit, the endpoint
instructs you to obtain the standalone bundle rather than silently accepting a
truncated report. A malformed nonce produces an inline evidence error rather
than fabricating a report.

---

## 4. Backend evidence (`nim-terminator`)

The SGLang backend's own in-guest evidence surface (`GET /kubetee/evidence` on
its strict-mTLS `:8443` listener) returns a `{quote, cc_eventlog, keyset,
bindings, tee_pubkey, signature}` envelope. The caller-facing contract relays it
through **one response header**.

**Request surface is one header.** Send `X-KubeTEE-Nonce` (64 lowercase hex) on
`POST /v1/chat/completions` — the same header used for inline gateway evidence.
No second evidence-request header, no pre-flight call, no per-request quote.

**Response surface is one envelope.** `X-KubeTEE-Backend-Evidence` is
base64url (no padding) of a self-describing JSON envelope; decode one blob and
branch on its `schema` and `tee` fields — never on a header name — so a TDX
backend and an SNP backend share one client code path. When the envelope exceeds
the inline header budget, the gateway instead sends
`X-KubeTEE-Backend-Evidence-Location` (the bulk bundle URL) plus `…-Reason`.

The top-level `schema` is the **TEE-specific evidence schema** —
`kubetee.tdx-evidence/1` for a TDX backend, `kubetee.snp-evidence/1` for an SNP
backend (it matches the populated evidence half below). Accept either; never
hard-code one.

Envelope layout (base64url-decoded):

```json
{
  "subject": "nim-terminator",
  "schema": "kubetee.tdx-evidence/1",
  "tee": "tdx",
  "role": "image-gen",
  "runtime_class": "kata-qemu-nvidia-gpu-tdx-runtime-rs",
  "epoch": {"id": "<epoch_id>", "issued_at": "<RFC3339>", "valid_until": "<RFC3339>"},
  "digest": "<sha256 of `quote` or of the native `snp` bytes>",
  "report_data": ["64 unsigned byte values"],
  "report_data_statement": "<exact JCS statement hashed into report_data>",
  "cert_chain": [{"cert_type": "<label>", "data": ["DER byte values"]}],
  "signature": "<base64 per-request signature — OPTIONAL, present only when the backend mints it; empty string otherwise. See 'Two-layer freshness'.>",
  "quote": "<base64 Intel DCAP quote, tee=tdx only>",
  "event_log": "<base64 TCC/CC event log, tee=tdx only>",
  "snp": {"schema": "kubetee.snp-evidence/1", "attestation_report": {}, "cert_chain": []}
}
```

Exactly one of `quote`/`event_log` (TDX) or `snp` (SNP) is populated. Reject a
response whose `tee` disagrees with the populated half.

| Element | Value |
|---|---|
| Bulk endpoint | `GET /v1/attestation/backend?role=nim-terminator&nonce=<64-hex>` — the same envelope plus `vm_config` (`role`, measured `files`, `agent_policy_claims`). Fetch it when the inline envelope is too large or you want `vm_config`. |
| Report-data binding | `SHA-256(JCS(statement)) ‖ 32 zero bytes` (the same 64-byte convention as the gateway), over an **epoch statement** |
| Backend signing key | `tee-pubkey` — the backend's **per-epoch evidence-signing key** (Ed25519), distinct from its TLS serving key and the gateway's keys. Its public half is bound into the epoch statement via `keyset_digest`, so it is covered by the hardware quote. |

**Two-layer freshness.** A hardware quote is sealed at mint: the caller's nonce
cannot go inside `report_data` if one quote is to serve many callers. Freshness
is therefore split:

1. **Hardware freshness (epoch)** — one quote per **epoch** (≤ 1 mint per 5
   minutes per replica), whose `report_data` binds the epoch statement. Two
   epochs (current + previous) are retained so you can resolve your `epoch_id`
   even if you fetched just before rotation.
2. **Caller freshness (per-request, optional)** — when the backend supports it,
   `signature` is the backend's `tee-pubkey` (Ed25519) over
   `SHA-256(quote) ‖ SHA-256(nonce) ‖ epoch_id ‖ counter`, where `counter` is a
   monotonic per-epoch request counter. The nonce defeats quote reuse at a
   different caller; the counter defeats within-epoch replay of the same
   caller's response.

   **Honest scope:** this per-request signature is minted by the **backend**, not
   the gateway (LiteLLM relays it and cannot re-sign — it does not hold the
   backend's key). It is therefore present only when the backend attaches one;
   an envelope may carry an empty `signature` and no `counter`. The freshness
   guarantee that is **always in force is Layer 1 (the epoch)**. Treat Layer 2 as
   an additional caller-binding when present — verify it strictly — but do not
   make a missing Layer 2 a rejection on its own.

Verify the signature with the `tee-pubkey` whose hash is committed in the epoch
statement's `keyset_digest` **when `signature` is non-empty**.

`X-KubeTEE-Attestation-Mode: nonce-bound` requests a quote whose `report_data`
binds that caller's nonce directly (the strongest form); it bypasses the epoch
cache and is rate-limited to **1 per 5 minutes per client key** (exceeding it
returns `429` with `Retry-After`). Ordinary completions ride the cached epoch.

**Residual limit, stated honestly.** A hardware report carries no timestamp, and
the serving keys are KBS-released rather than proved generated in-guest per boot
(§1). The 5-minute window bounds freshness *in time*, not *per boot*: replay is
defeated by `valid_until`, the client's clock and the per-request signature's
nonce/counter binding (when the backend mints one), not by the report itself.
Closing that last gap requires a keypair generated in-guest per boot and named
in `report_data`. Not claimed until implemented.

Also, the gateway is a relay here: the quote attests composition and freshness
of the backend guest; the linkage to a given completion is the east-west mTLS
hop plus `X-KubeTEE-Backend` — a trust-the-gateway statement, not a signature
over the model output.

### Boot Trustee EAR — bulk bundles only

The **boot-time Trustee EAR** (the appraisal over the guest's measured
composition, minted once at start) is **not** a per-request freshness proof and
is never presented as one:

| Boundary | Rule |
|---|---|
| Where it appears | **Bulk** evidence bundles only (`GET /v1/attestation`, `GET /v1/attestation/backend`), as `appraisal.ear_token` + `appraisal.ar4si`. Omitted from inline per-completion envelopes. |
| What it covers | Boot composition of the guest that minted it. Nothing about a later request, prompt, or model-output bytes. |
| Freshness | One EAR per **boot**, not per request. Always pair it with the per-request Layer-2 signature when one is present. |
| Breaker relationship | A fresh boot EAR **never clears a tripped circuit breaker** — otherwise a reboot would launder a drift trip. |

The EAR is a JWT signed by the Trustee Attestation Service (AS); verify it with
the **AS JWKS**. Three trust anchors cover the whole contract — do not collapse
them into one check:

| Trust anchor | Verifies | Key source |
|---|---|---|
| AMD root (ARK/ASK/VCEK) | the SNP report is genuine AMD hardware | AMD root material, per processor generation |
| Trustee AS JWKS | the boot EAR is a genuine Trustee appraisal | AS published JWKS |
| Registry Ed25519 key | the reference measures are our approved values | `key_url` in the registry, out-of-band |

A successful hardware appraisal (EAR `affirming`) is **not** by itself proof of
resource authorization or per-request freshness. Passing one anchor does not
imply the others.

### Circuit breaker — what a client sees

The gateway runs a **measurement-drift circuit breaker** over the backend
envelope:

| Condition | Class | Client sees | Serving |
|---|---|---|---|
| **Measurement drift** (role / InitData `MRCONFIGID` / `MRTD` / `RTMR0-3` / OVMF changes vs the signed registry — no active record matches) | **TRIP** — breach signal | `X-KubeTEE-Breaker-State: OPEN`, `X-KubeTEE-Breaker-Trip: <reason>`, `X-KubeTEE-Breaker-Action: auto-block (HTTP 503)` | **Blocked** — the backend must not serve. |
| **Freshness gap** (epoch absent/expired, or hardware evidence momentarily unavailable) | **DEGRADE** — evidence gap, not drift | `X-KubeTEE-Breaker-State: DEGRADED`, `X-KubeTEE-Breaker-Reason: <reason>` | **Still serving**, downgraded to the boot boundary label. |

Behavior to rely on:

- **A TRIP is fail-closed and sticky.** Once OPEN it stays OPEN until an
  operator clears it; a later healthy sample or a fresh boot EAR does not
  auto-reset it. Treat `OPEN` as "this backend's composition changed — stop
  accepting its output" and surface it.
- **A DEGRADE is not a breach.** Keep the response, mark the evidence boundary
  (`boot-time (Trustee EAR; east-west mTLS)`) and carry the reason. Do not treat
  it as attested-with-fresh-backend-hardware-evidence.
- **Drift is measured against the signed registry** (matched against any active
  record), never against a value the serving guest supplies — the registers are
  read from the quote you verify.

---

## 5. Verification checklist

The full rules and exact reference contracts are in
[ATTESTATION-SPEC-v1.md](./ATTESTATION-SPEC-v1.md) §6. Use any native SNP
implementation — e.g. stock **`sev 7.1.0`** (its pure-Rust crypto backend;
OpenSSL is not required) or an equivalent independent verifier. No patch
to CoCo, Trustee or KBS is needed to consume this contract.

1. **Explicit type and framing.** Require `tee=snp`, `tee_type=snp`,
   `runtime_class=kata-qemu-snp-runtime-rs` and
   `evidence.snp.schema=kubetee.snp-evidence/1`.
2. **AMD authenticity.** Support report versions 3–5; require VMPL0 and expected
   field lengths. Validate ARK/ASK/VCEK by cryptographic roles, AMD root and
   processor/chip generation. Verify the report signature and approved reported
   TCB. Certificate labels alone are insufficient.
3. **Composition and policy.** Compare the signed report's 48-byte launch
   `measurement`, 32-byte `host_data`, guest policy and TCB with the signed
   registry. Require debug-off, migration-agent-off and measured denied
   guest-control operations; text declaring these alone is not enough.
4. **Keyset digest.** Canonicalize the served keyset using RFC 8785 JCS, compute
   its SHA-256, and check the resulting value in the statement. `signing_keys`
   is empty in this deployment. The TLS identity named in the keyset is
   KBS-released into the guest (not a mounted Kubernetes Secret); a client
   always compares the keyset/`tls_cert_sha256` against its **own** TLS
   session, so an out-of-TEE terminator with any other certificate is detected
  (trust-boundary detail:
   [ATTESTATION-SPEC-v1.md](./ATTESTATION-SPEC-v1.md) §4).
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
6. **TLS possession.** Read the leaf directly from your TLS socket, hash its DER
   and SPKI, match the keyset plus `tls_cert_sha256`, and verify the nonce
   signature. The report signature, TLS signature and registry signature are
   three separate trust operations.
7. **Registry.** Validate the schema, canonicalize the registry without its
   `signature` member, and verify its Ed25519 signature using the separately
   published public key.
8. **Optional EAR.** Validate the boot RCAR's native evidence and Trustee policy
   if present. Do not substitute it for the caller's nonce binding or the
   current connection's possession proof.

Reject missing evidence, unknown types, certificate failures, report mismatches,
bad guest policy, unapproved measurements and TLS mismatches. Do not downgrade
failed native SNP verification to a transport or key-label check. AMD root
material, guest reference and processor expectations must be maintained
independently — KubeTEE's signed registry identifies the approved software/guest
reference; it cannot solely establish AMD's root of trust.

### Runnable backend-evidence checklist

For the **relayed backend envelope** (`X-KubeTEE-Backend-Evidence`):

```python
import base64, hashlib, json
from nacl.signing import VerifyKey  # Ed25519 for the tee-pubkey signature

def b64url_decode(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))

def verify_backend_envelope(header_value: str, nonce_hex: str, *,
                            registry, as_jwks, amd_root):
    env = json.loads(b64url_decode(header_value))

    # 1. Self-describing type + disjoint evidence. The schema is the TEE
    #    evidence schema (kubetee.tdx-evidence/1 or kubetee.snp-evidence/1).
    assert env["schema"] in ("kubetee.tdx-evidence/1", "kubetee.snp-evidence/1")
    tdx = "quote" in env and env.get("quote")
    snp = env.get("snp")
    assert (tdx != bool(snp)), "exactly one TEE half populated"
    assert (env["tee"] == "tdx") == bool(tdx), "tee disagrees with populated half"

    # 2. Freshness. Layer 1 (epoch) is always present and always enforced:
    epoch = env["epoch"]
    assert epoch["valid_until"] > now_utc(), "epoch expired"          # Layer 1 window

    # Layer 2 (per-request caller binding) is the STRONGEST form and is verified
    # whenever the backend mints it. It is a backend-side signature (LiteLLM
    # relays it and cannot re-sign — it does not hold the backend key), so it is
    # present only when the backend attaches one; today the epoch layer is the
    # freshness guarantee that is always in force. Verify it when present — do
    # NOT require it (an envelope without it is not invalid, just less bound):
    if env.get("signature"):
        # per-request signature over quote||nonce||epoch_id||counter
        msg = (hashlib.sha256(b64url_decode(env["quote"]) if tdx else canonical(env["snp"])).digest()
               + hashlib.sha256(bytes.fromhex(nonce_hex)).digest()
               + epoch["id"].encode()
               + int(env.get("counter", 0)).to_bytes(8, "big"))
        tee_pubkey = registry_key_for(epoch, env["role"])             # bound via keyset_digest
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
    ref = registry.match_any_active(regs, tee=env["tee"])               # VERIFY registry Ed25519 sig
    assert ref is not None, "registers match no active record"          # policy.match: any-active-record

    # 5. Boot EAR (bulk bundles only) — verify AS signature + Trustee policy,
    #    but NEVER use it to clear a breaker trip or replace Layer 2.
    if env.get("appraisal", {}).get("ear_token"):
        verify_ear_jwt(env["appraisal"]["ear_token"], as_jwks)          # VERIFY

    return True
```

This is deliberately a checklist, not a complete verifier: hardware-report
signature verification, chain validation and registry signature verification are
marked `# VERIFY` and must be filled from a native implementation before you
accept anything. A response that fails any assertion must be rejected outright —
do not downgrade to a transport or key-label check.

---

## 6. Reference values and keys

The exact measures and container provenance live as **records** in one signed
registry (Ed25519-signed; verification key via its `key_url`):

| Document | Records | Human doc | Status |
|---|---|---|---|
| [`tee-measurements-registry.json`](https://kubetee.ai/.well-known/tee-measurements-registry.json) | **all backend records** (schema `kubetee.tee-measurements-registry/1`) — `nim-terminator` TDX records for Kimi-K3.1-Pro and MiMo-v2.6-Pro (per model × node), each with the six registers (`MRTD`/`MRCONFIGID`/`RTMR0-3`) captured from the booted guest's quote + CCEL replay | [ATTESTATION-REFERENCE-MEASURES-SGLANG.md](./ATTESTATION-REFERENCE-MEASURES-SGLANG.md) | **Active** (signed) |
| `litellm` (SNP gateway) | [`tee-measurements.json`](https://kubetee.ai/.well-known/tee-measurements.json) | [ATTESTATION-SPEC-v1.md](./ATTESTATION-SPEC-v1.md) §2–5 | **Active** (signed) |
| `nim-terminator` **CoRIM twin** | [`tee-reference-values.cbor`](https://kubetee.ai/.well-known/tee-reference-values.cbor) (detached `.sig`, `.sha256`, human `.json`) | [ATTESTATION-REFERENCE-MEASURES-SGLANG.md](./ATTESTATION-REFERENCE-MEASURES-SGLANG.md) §5 | **Active** (signed) — **Kimi record only**: the same six registers as a CoRIM (CBOR tag 501/506, SHA-384) for RVPS-based verifiers, with a detached Ed25519 `.sig` over the raw CBOR bytes |

**One registry, match-any-active-record (no per-model pin).** You do not pin one
reference per model or per image. Fetch the registry, verify its Ed25519
signature against the pinned public key, and accept the backend evidence iff its
registers match **any** record whose `status` is `active` and — when the record
sets `valid_until` — whose `valid_until` is still in the future, for the same
`tee`. The registry's own `policy` block states this:

```json
"policy": {
  "match": "any-active-record",
  "match_note": "Observed TEE evidence is legitimate iff its registers match ANY record with status=active and now <= valid_until (when set), for the same `tee`. No per-model / per-image pin on the verifier.",
  "retention": {
    "generations_per_chain": 2,
    "chain": "model + role + tee (a chain rolls versions together)",
    "generation": "one immutable image_ref (content-addressed)",
    "note": "current + previous generation per chain stay ACTIVE so BOTH verify during AND after a rollout ... there is no time-based re-capture."
  },
  "hard_expiry": "valid_until is OPTIONAL and manual-only (e.g. throwaway canaries); absent = no expiry ..."
}
```

**Record lifecycle (current + previous per chain).** A record's *generation* is
its immutable `image_ref`; its *chain* is (model, role, tee). The newest **two**
generations per chain — the current and the previous — stay active so **both**
verify during and after a rollout: when a new version is being rolled, the
outgoing version's measurements remain acceptable until the rollout completes,
and the pair doubles as the rollback window. A record leaves the allowlist only
when a third newer generation lands in its chain (housekeeping `--prune`), or it
is hard-expired / `status: "deprecated"` / `"revoked"`. Measurements change only
at a rollout — there is no time-based re-capture and no fixed validity window.
`valid_until` is optional and reserved for manual hard-expiry (for example
throwaway canaries). Deploying a new measured model is simply one more active
record in this registry; the verifier needs no change.

- Compare the backend's live evidence registers against the registry's active
  records — never against a value supplied only by the serving guest. Each
  record names which fields are captured; a match against any active record is
  what keeps the circuit breaker from tripping, and a match against **none** is
  the drift that trips it. Note that `RTMR0` is node-specific — a model on a new
  node mints a new record — so expect one record per measured (model × node)
  launch.
- Measurement signing key (public half). `signing_keys: []` in the keyset does
  not expose it. It is pinned in **two independent channels** — verify they
  agree before you trust a record's signature:

  | Channel | Value |
  |---|---|
  | 1 — machine record | [`tee-measurements-signing-key-2026.json`](https://kubetee.ai/.well-known/tee-measurements-signing-key-2026.json) |
  | 2 — this document | the literal values below |

  - `key_id`: `kubetee-measurements-2026-11-25`
  - algorithm: `Ed25519`, canonicalization: RFC 8785 JCS over the record without its
    `signature` member
  - public `x` (Ed25519): `FekS2fBdTq91Xe6IIUoGWot_ig7uybpX9vhO5WN_1Wc`
  - SPKI (DER, base64url): `MCowBQYDK2VwAyEAFekS2fBdTq91Xe6IIUoGWot_ig7uybpX9vhO5WN_1Wc`
  - SPKI SHA-256: `sha256:046b732aa6bb0695a15c00af9d58d64661e5e27ec3d169851ea77dc0bbf6f530`
- Serving TLS key custody and its limits are summarized in §1 ("What this does
  not prove"); the measured-container provenance behind these values is in
  [ATTESTATION-REFERENCE-MEASURES-SGLANG.md](./ATTESTATION-REFERENCE-MEASURES-SGLANG.md)
  §1.
