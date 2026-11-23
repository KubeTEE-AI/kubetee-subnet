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
| `X-KubeTEE-Backend-Attested` | `boot-time (Trustee EAR; east-west mTLS)`: a boundary statement, not a fresh GPU report. |
| `X-KubeTEE-Attestation-Error` | Error when inline evidence cannot be supplied; ordinary inference need not fail with it. |

The native inline SNP value has a header-size limit. If evidence cannot be
framed safely, the endpoint instructs the client to obtain the standalone
bundle rather than silently accepting a truncated report.

Without `X-KubeTEE-Nonce`, a request is an ordinary OpenAI call with no
additional report work. A malformed nonce produces an inline evidence error
rather than fabricating a report.

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
