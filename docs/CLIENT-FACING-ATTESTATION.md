# Client-facing attestation of inference on `llm.kubetee.ai`

**Status:** live on staging `na-us-oakland-56` (2026-09-18) — endpoint + inline evidence shipped on the LiteLLM gateway (3 CPU-TDX replicas, `kata-qemu-tdx-runtime-rs`).
**Audience:** miners and clients calling the KubeTEE inference API who want cryptographic proof that responses came from a TDX confidential guest.
**Related:** [EAST-WEST-ATTESTED-MTLS.md](./EAST-WEST-ATTESTED-MTLS.md) (live east-west spec + roadmap, merged 2026-10-27).

> **`kubetee.attestation.v1` is the wire construction since 2026-10-27** — the
> quote is bound to the v1 JCS statement (`bindings.report_data_statement` +
> `keyset_digest`), and `keyset`/`bindings`/`evidence`/`appraisal` ship in the
> bundle. `report_data_input` names the active construction on every response
> ("kubetee.attestation.v1" today; "sha512(nonce)" is the legacy rollback
> shape). The binding a verifier **must** recompute is
> [ATTESTATION-SPEC-v1.md](./ATTESTATION-SPEC-v1.md) §4 — not `SHA512(nonce)`.
> `appraisal` is omitted when the per-boot cached Trustee EAR is absent
> (best-effort); verify the quote + binding in that case.

---

## What the client-facing attestation proves

| Claim | Evidence |
|-------|----------|
| The response was produced by a genuine Intel TDX confidential VM (guest debug off) | TDX quote in the response, verified against Intel-signed DCAP collateral |
| The quote was minted **fresh** (not replayed) and is bound to this request | Client-supplied 64-hex nonce is hashed into the quote's `REPORTDATA` |
| The guest that minted the quote is the one terminating **your TLS session** | The guest signs your nonce with the pod's TLS private key; you verify the signature against the leaf cert from your own TLS session (`tls_possession` / `X-KubeTEE-TLS-*`) |
| The gateway guest runs an unmodified container set | The measured container allowlist is part of the guest's initdata (`cc_init_data`), which is measured into the TD; the AS extraction surfaces `agent_policy_claims` |
| Which replica minted it | `pod` field (endpoint payload) / replica identity headers |
| Which inference backend served the request (boot-time attested) | `X-KubeTEE-Backend*` headers on inline evidence |

**What it does NOT prove (scope decisions, 2026-09-17/18):**
- Per-request GPU quotes from the inference backend. Backends attest at **boot** to Trustee for their mTLS certs; relaying a per-request GPU quote is a much bigger lift (each SGLang guest would need the attestation REST API + per-request minting). Backend identity headers are the current contract.
- That the *content* of a specific chat response was computed by the quoted guest (the quote is minted adjacent to the response, both from the same replica, but the connection is by identity, not cryptographic chaining).

---

## API surface

### 1. Standalone fresh quote — `GET /v1/attestation?nonce=<64 hex>`

Mints a **fresh TDX quote** with the nonce bound into `REPORTDATA`.

```bash
NONCE=$(openssl rand -hex 32)   # exactly 64 hex chars = 32 bytes
curl -s "https://llm.kubetee.ai/v1/attestation?nonce=$NONCE"
```

Response (200):

```json
{
  "nonce": "<your 64-hex nonce, lowercased>",
  "report_data_input": "kubetee.attestation.v1",
  "quote": "<base64 TDX quote, ~7KB>",
  "cc_eventlog": "<base64 eventlog or null>",
  "tee": "tdx",
  "runtime_class": "kata-qemu-tdx-runtime-rs",
  "tls_possession": {
    "tls_signature": "<base64 RSA signature>",
    "tls_signature_alg": "RS256",
    "tls_signature_input": "sha256(nonce)",
    "tls_cert_sha256": "<sha256 of the serving cert's DER>"
  },
  "pod": "litellm-6d48d45cbc-xgj7w",
  "spec_version": "kubetee.attestation.v1",
  "tee_type": "tdx",
  "keyset": {
    "subject": "kubetee.attestation.v1/llm.kubetee.ai",
    "not_after": "<cert notAfter>",
    "tls_public_keys": [{"domain": "llm.kubetee.ai", "spki_sha256": "<sha256 of the DER SPKI>"}],
    "signing_keys": [],
    "e2ee_keys": []
  },
  "bindings": {
    "version": "kubetee.attestation.v1",
    "report_data_statement": "{\"keyset_digest\":\"sha256:<hex>\",\"nonce\":\"<64-hex>\",\"purpose\":\"kubetee.attestation.v1\"}",
    "keyset_digest": "sha256:<hex>"
  },
  "evidence": {
    "quote": "<same base64 quote>",
    "quote_report_data": "<base64 of the 64-byte REPORTDATA>",
    "event_log": "<base64 eventlog or null>",
    "vm_config": {"algorithm": "sha384", "version": "0.1.0", "role": "litellm", "files": {...}, "initdata_sha384": "<hex>", "agent_policy_claims": {...}}
  },
  "appraisal": {"ear_token": "<Trustee EAR JWT>", "ar4si": {...}}
}
```

`appraisal` is **omitted when the per-boot cached Trustee EAR is absent** (best-effort) — verify the quote + binding in that case. `report_data_input` names the active construction ("sha512(nonce)" is the legacy rollback shape; branch on it).

**TLS-possession proof (what `tls_possession` is):** `llm.kubetee.ai` is TLS **passthrough** — your TLS session terminates inside the same TDX guest that served this payload. The guest signed your nonce with the private key of the certificate your TLS session used. Verify it against the leaf certificate from **your own TLS session** (`ssl.get_server_certificate` / `openssl s_client`), and check the reported `tls_cert_sha256` matches that same cert:

```python
import base64, hashlib, ssl, socket
from cryptography import x509
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding

# 1. leaf cert straight from your TLS session
pem = ssl.get_server_certificate(("llm.kubetee.ai", 443))
cert = x509.load_pem_x509_certificate(pem.encode())

# 2. fingerprint must equal tls_cert_sha256
der = base64.b64decode("".join(l for l in pem.splitlines() if "CERTIFICATE" not in l))
assert hashlib.sha256(der).hexdigest() == payload["tls_possession"]["tls_cert_sha256"]

# 3. verify the nonce signature with the session cert's public key
cert.public_key().verify(
    base64.b64decode(payload["tls_possession"]["tls_signature"]),
    payload["nonce"].encode(),
    padding.PKCS1v15(),
    hashes.SHA256(),
)
```

If both checks pass, the TDX guest that minted the quote holds the private key of the exact certificate you are connected to — the quote and the TLS endpoint are the **same machine**, not just the same fleet.

- 400 if the nonce is not exactly 64 hex characters.
- 502 if the in-guest attestation service is unavailable (fail-closed for evidence, fail-open for the gateway itself — chat keeps working).
- **3-replica caveat:** the Service load-balances; the quote proves *a gateway replica* is a TDX guest, not *the* replica that served a given chat. Use inline evidence for per-response binding.

### 2. Inline evidence on chat — `X-KubeTEE-Nonce` request header

Send the nonce **with a chat completion**; the same HTTP response carries the evidence headers.

```bash
NONCE=$(openssl rand -hex 32)
curl -s "https://llm.kubetee.ai/v1/chat/completions" \
  -H "Authorization: Bearer $KUBETEE_KEY" \
  -H "Content-Type: application/json" \
  -H "X-KubeTEE-Nonce: $NONCE" \
  -d '{"model": "z-ai/glm-5.3", "messages": [{"role": "user", "content": "Say OK"}], "max_tokens": 8}' \
  -D /tmp/headers.txt
grep -i x-kubetee /tmp/headers.txt
```

Response headers (both streaming and non-streaming):

| Header | Meaning |
|--------|---------|
| `X-KubeTEE-Nonce` | your nonce, echoed (lowercase hex) |
| `X-KubeTEE-Attestation-Quote` | base64 TDX quote minted on this replica for this request |
| `X-KubeTEE-Attestation-Tee` | `tdx` |
| `X-KubeTEE-Report-Data-Input` | the active construction (`kubetee.attestation.v1`; `sha512(nonce)` = legacy rollback shape) |
| `X-KubeTEE-Binding-Statement` | the exact JCS statement string bound into REPORTDATA (v1) |
| `X-KubeTEE-Binding-Keyset-Digest` | `sha256:<hex>` of the served keyset (recompute it from the keyset — spec §5) |
| `X-KubeTEE-TLS-Signature` | base64 RSA signature of your nonce, made with the private key of the cert your TLS session is using (RS256) — verify against your session's leaf cert |
| `X-KubeTEE-TLS-Signature-Alg` | `RS256` |
| `X-KubeTEE-TLS-Signature-Input` | `sha256(nonce)` |
| `X-KubeTEE-TLS-Cert-SHA256` | sha256 of the serving cert's DER — must match your session's leaf cert |
| `X-KubeTEE-Backend` | model name that served (e.g. `z-ai/glm-5.3`) |
| `X-KubeTEE-Backend-Endpoint` | the backend Service the gateway routed to |
| `X-KubeTEE-Backend-Attested` | `boot-time (Trustee EAR; east-west mTLS)` — the backend's TLS cert was issued only after its TDX quote passed Trustee appraisal |
| `X-KubeTEE-Attestation-Error` | present instead of the quote on failure (e.g. `invalid nonce`, `quote unavailable`) |

Notes:
- **Opt-in:** without the header, requests are normal OpenAI calls with zero overhead.
- Works on **streaming** responses too (evidence rides the initial SSE response headers).
- The response body stays 100% OpenAI-schema — no `attestation` field mixed into chat objects.
- A malformed nonce returns `X-KubeTEE-Attestation-Error: invalid nonce (need 64 hex)` instead of failing the completion.
- Small latency cost per attested request (one in-guest quote mint, measured ~sub-second on the CPU TDX guest).

---

## The critical nonce-binding semantics (read before verifying)

**`kubetee.attestation.v1` binds a JCS statement, not the nonce alone.** The
binding is **verifier-agnostic by construction** — you recompute it yourself,
byte-for-byte, and compare it to the quote's `REPORTDATA`. It is *not* a
verifier's built-in nonce check (see path A for why those two diverge).

The quote's `REPORTDATA` (64 bytes) is:

```
REPORTDATA = SHA-256(statement) || 32 zero bytes
```

where `statement` is the exact JSON string served verbatim as
`bindings.report_data_statement` (RFC 8785 JCS, keys sorted by UTF-16 code
units):

```
{"keyset_digest":"sha256:<hex>","nonce":"<64-hex>","purpose":"kubetee.attestation.v1"}
```

and `keyset_digest` = `SHA-256(JCS(keyset))` over the served `keyset` object
(spec §5) — the digest that ties this quote to the TLS keyset you are talking
to.

```
client generates nonce (64 hex)
   │
   ├─► GET /v1/attestation?nonce=…          (or X-KubeTEE-Nonce on chat)
   │      gateway: REPORTDATA := SHA256(statement) + 32 zero bytes → quote
   │      quote + {keyset, bindings, evidence, appraisal} returned
   │
   └─► YOU verify (two independent checks):
        (1) quote crypto / TCB / debug-off  → path A (ITA) or path B (DCAP)
        (2) v1 nonce + keyset binding       → recompute over the served
             statement bytes + served keyset; compare to quote REPORTDATA
```

Rules:
- **Do not** pre-hash the nonce — send KubeTEE the raw 64-hex nonce; the gateway builds the statement.
- **Do not** re-serialize the statement — hash the **exact bytes** of `bindings.report_data_statement` (re-canonicalizing can change bytes and break the match).
- **Recompute `keyset_digest` from the served `keyset`** — never trust the echoed `keyset_digest` alone (spec §5).

```python
import base64, hashlib, json

payload = json.load(open("attest.json"))
stmt   = payload["bindings"]["report_data_statement"].encode()   # exact served bytes
qb     = base64.b64decode(payload["quote"])
rd     = qb[568:568 + 64]                                        # TDREPORT1.6 REPORTDATA

# (2) v1 binding — statement bound, keyset bound (recompute keyset_digest per spec §5)
assert rd == hashlib.sha256(stmt).digest() + b"\x00" * 32, "v1 binding mismatch"
```

**Legacy rollback shape** (`report_data_input: "sha512(nonce)"`, no `keyset`/`bindings`)
binds `REPORTDATA = SHA512(raw nonce)` — the old construction. Branch on
`report_data_input`; every response names the active construction.

---

## Verification path A — Intel Trust Authority (ITA)

KubeTEE quotes are standard Intel TDX DCAP quotes and their **quote crypto + TCB** can be appraised by Intel Trust Authority (or any TDX quote verifier). But understand the split before you build a verifier:

> **ITA verifies the quote; you verify the binding.** ITA's TDX `tdx_report_data`
> rule is a cumulative **SHA-512** over `verifier_nonce ‖ runtime_data ‖
> user_data ‖ held_data`, while the v1 quote binds `SHA-256(statement) + 32
> zeros` — so the two bindings are different constructions and no plain
> `runtime_data` value makes them coincide. Submit the quote to ITA for
> DCAP/TCB appraisal **without** `runtime_data`, and run the v1 nonce + keyset
> check yourself (two lines — "The critical nonce-binding semantics" above).
> (ITA's `held_data`/`user_data` terms are a possible hook to make its hash
> coincide with a quote binding — the way CoCo/Trustee binds a runtime-data
> digest — but the gateway binds the v1 statement, so a verifier cannot
> recover a preimage for that SHA-512 rule. Whether an unenforced
> `runtime_data` mismatch errors or is ignored is **tenant/config dependent**;
> treat the split above as the contract.)

### Prerequisites
- An ITA tenant with API key (`*` or `tdx` product), and the verifier URL, e.g. `https://api.trustauthority.intel.com` (US) or `https://api.eu.trustauthority.intel.com` (EU) — see the [ITA REST API](https://docs.trustauthority.intel.com/main/articles/articles/ita/restapi/restapi-intro.html).
- `pip install intel-trustauthority-client` (the Python client) — but note the client-flow caveat below.

### The one ITA caveat (important)

The ITA client's `collect_evidence` **hashes the nonce itself** (the cumulative SHA-512 rule) before binding — that matches ITA's verification but NOT KubeTEE's binding (KubeTEE already baked `SHA256(statement)` into the quote). **Use pre-collected evidence:** submit the KubeTEE-issued quote directly to ITA's `/attest` API with `runtime_data` **omitted**, then run the v1 binding check yourself.

```python
# pip install intel-trustauthority-client requests
import requests

quote_b64 = "<X-KubeTEE-Attestation-Quote or /v1/attestation .quote>"

# 1. ITA appraisal — quote crypto + TCB + debug-off (runtime_data OMITTED:
#    the v1 REPORTDATA is not ITA's SHA-512 runtime-data binding, so passing
#    the nonce here cannot bind to the v1 statement)
resp = requests.post(
    "https://api.trustauthority.intel.com/appraisal/v1/attest",
    headers={"x-api-key": ITA_API_KEY, "Accept": "application/json"},
    json={"quote": quote_b64, "policy_ids": [YOUR_POLICY_ID]},  # verifier_nonce optional
    timeout=30,
)
token = resp.json()["token"]                # appraised JWT (quote/TCB claims)

# 2. KubeTEE v1 binding — the nonce + keyset check ITA does not do
#    (full snippet under "The critical nonce-binding semantics" above):
#    assert qb[568:656] == SHA256(bindings.report_data_statement) + 32 zeros
#    and recomputed keyset_digest matches the served keyset (spec §5)
```

**What ITA checks:** Intel-signed DCAP quote, TCB level against its TCB policy (configured in the ITA tenant), debug flags off. It returns a signed appraisal token (JWT) with policy claims. **What only you check:** that the quote is bound to *your* nonce and to the served keyset (the v1 statement) — plus `tls_possession` if you want the "quote == TLS endpoint" property.

> If your ITA tenant policy allows, set the TCB policy to match your security requirement (e.g. match KubeTEE's PCCS-configured TCB-R `standard` channel). `runtime_data` in the ITA request is `optional` per the API — leave it out for KubeTEE quotes.

### Decode the appraisal token

```python
import jwt  # pip install PyJWT
claims = jwt.decode(token, options={"verify_signature": False})  # verify sig per ITA docs
print(claims["policy_ids"], claims["results"])  # 'affirming' / 'constrained' etc.
```

## Verification path B — local DCAP quote verify (offline)

If you run your own DCAP tooling (e.g. `sgx-dcap-quote` verify, Intel DCAP library + PCK cache, or the CoCo `app-starter` verifier), the quote from `/v1` is a raw TDX quote — verify:
1. The quote's `REPORTDATA` equals `SHA-256(bindings.report_data_statement) || 32 zero bytes` (v1), or `SHA-512(your nonce)` in the legacy rollback shape (offset 568 in the TDREPORT; see the layout below).
2. The Intel DCAP signature chain (PCK cert → Intel root) against Intel's PCS.
3. `td_attributes.debug == 0` (no debug).
4. TCB/TEE TSV values against your policy.

`REPORTDATA` offset: the TDX quote starts with a 48-byte header (incl. `HEADER` type, version, vendor), and `REPORTDATA` is at **offset 568** in the standard `TDREPORT1.6` layout used by the CoCo attester (verified live 2026-09-18: `SHA512(nonce)` bytes found at offset 568 in every KubeTEE quote; v1 verified live 2026-10-27: `SHA-256(statement)+zeros` at the same offset).

```python
import base64, hashlib, json

payload = json.load(open("attest.json"))
qb = base64.b64decode(payload["quote"])
rd = qb[568:568 + 64]

if payload["report_data_input"] == "kubetee.attestation.v1":
    stmt = payload["bindings"]["report_data_statement"].encode()
    assert rd == hashlib.sha256(stmt).digest() + b"\x00" * 32, "v1 binding mismatch"
    # plus keyset_digest recomputation over the served keyset (spec §5)
else:  # legacy rollback shape "sha512(nonce)"
    assert rd == hashlib.sha512(payload["nonce"].encode()).digest(), "nonce not bound"
```

---

## Frequently asked questions

**Q: Why is `REPORTDATA` the SHA-256 of a statement, not the raw nonce?**
The statement binds three things a raw nonce cannot: **your nonce** (freshness), **the served keyset digest** (this quote belongs to the TLS keyset you are talking to), and **a fixed `purpose`** (the quote is not reusable in another protocol's statement space). It is SHA-256-of-statement zero-padded to 64 bytes because `REPORTDATA` is 64 bytes and TDX takes exactly what the attester writes — the construction is defined in [ATTESTATION-SPEC-v1.md](./ATTESTATION-SPEC-v1.md) §4 and pinned by conformance vectors.

**Q: Does Intel Trust Authority check this binding for me?**
No — and it cannot (ITA's `tdx_report_data` rule is a cumulative **SHA-512**, so it can never equal a SHA-256-plus-zeros `REPORTDATA`). ITA appraises the **quote** (DCAP chain, TCB, debug-off); the **binding** — your nonce + the keyset — is a two-line check you run over the served bytes. See path A.

**Q: Why is `REPORTDATA` the SHA512 of my nonce in the legacy shape?**
That was the pre-flip construction (`report_data_input: "sha512(nonce)"`, kept as the rollback shape): ITA's verification rule (`tdx_report_data` = cumulative SHA512 of `verifier_nonce || runtime_data || user_data || held_data`) — passing the raw nonce as `runtime_data` meant ITA hashed it and matched `REPORTDATA`. That rule applies **only** to the legacy shape; it is not the v1 contract.

**Q: Can I verify the quote on-chain / trustlessly?**
The quote is Intel-signed; on-chain verification would require an Intel PCS oracle — out of scope today. Standard off-chain ITA or DCAP verification is the contract.

**Q: Does attestation add latency to my inference?**
Opt-in only. No header → zero overhead. With the header, one in-guest quote mint rides the response (sub-second, measured on CPU TDX).

**Q: What if the endpoint returns 502?**
The gateway is alive but the in-guest attestation agent is not answering (rare; e.g. right after a guest restart). Chat still works; retry evidence later.

**Q: How do I know the backend GPU guests are also attested?**
Two signals: (1) `X-KubeTEE-Backend-Attested: boot-time (Trustee EAR; east-west mTLS)` — the gateway only has working mTLS to the backend because Trustee issued that backend's cert after a passing TDX quote; (2) the east-west spec (link above) documents the boot-time protocol.

**Q: My language is not Python — what do I do?**
The endpoint contract is plain HTTP + JSON/headers. Verification path B needs any TDX DCAP verifier. ITA also ships Go/Java clients — the same split (ITA appraises the quote; you check the v1 binding) and the same exact-statement-bytes rule apply.

---

## Endpoint reference (summary)

| Endpoint / header | Type | Description |
|---|---|---|
| `GET /v1/attestation?nonce=<64hex>` | HTTP | Fresh TDX quote, JSON payload, v1 JCS statement bound into REPORTDATA (legacy shape: SHA512(nonce)), plus keyset/bindings/evidence(/appraisal) and TLS-possession signature |
| `X-KubeTEE-Nonce: <64hex>` (request) | header | Opt-in inline evidence on any chat completion (streaming + non-streaming) |
| `X-KubeTEE-Attestation-Quote` (response) | header | base64 TDX quote minted for this request |
| `X-KubeTEE-TLS-Signature` (+`-Alg`/`-Input`/`Cert-SHA256`) (response) | header | Nonce signed with the serving TLS key — proves the quote minted is the cert holder you're connected to |
| `X-KubeTEE-Backend*` (response) | header | Backend identity + boot-time attestation signal |
| `X-KubeTEE-Attestation-Error` (response) | header | Failure reason when evidence could not be minted |

---

## Implementation notes (KubeTEE operators)

- Module: `nim/eastwest/kubetee_attestation.py` (source of truth; embedded in the `eastwest-fetch-certs` ConfigMap in `fleet-gitops/infrastructure/litellm/staging/values.yaml`).
- Callback registration: `litellm_settings.callbacks: [..., "kubetee_attestation.kubetee_attestation_logger"]` (both base values + oakland overlay).
- The hook is `async_post_call_response_headers_hook` — it fires **before** headers freeze on BOTH streaming and non-streaming chat paths. (`async_post_call_success_hook` would be too late for streaming: the `StreamingResponse` is already constructed when that hook runs.)
- `POD_NAME` env var (extraEnvVars fieldRef) pins the minting replica in the endpoint payload.
- Guest requirements: `agent.guest_components_rest_api=all` kernel param (enables `/aa/evidence` AND `/cdh/resource`), `ExecProcessRequest` blocked by agent policy (todo 4) — `kubectl exec` into the guest is denied by design; use port-forward/curl pods for testing.
- 26 unit tests at `/tmp/test-kubetee-attestation/` (mocked httpx+litellm; recreate from the repo module if needed).
