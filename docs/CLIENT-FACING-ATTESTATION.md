# Client-facing attestation of inference on `llm.kubetee.ai`

**Status:** live on staging `na-us-oakland-56` (2026-09-18) — endpoint + inline evidence shipped on the LiteLLM gateway (3 CPU-TDX replicas, `kata-qemu-tdx-runtime-rs`).
**Audience:** miners and clients calling the KubeTEE inference API who want cryptographic proof that responses came from a TDX confidential guest.
**Related:** [EAST-WEST-ATTESTED-MTLS.md](./EAST-WEST-ATTESTED-MTLS.md) (live east-west spec), [EAST-WEST-ATTESTED-MTLS-PLAN.md](./EAST-WEST-ATTESTED-MTLS-PLAN.md) (roadmap).

---

## What the client-facing attestation proves

| Claim | Evidence |
|-------|----------|
| The response was produced by a genuine Intel TDX confidential VM (guest debug off) | TDX quote in the response, verified against Intel-signed DCAP collateral |
| The quote was minted **fresh** (not replayed) and is bound to this request | Client-supplied 64-hex nonce is hashed into the quote's `REPORTDATA` |
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
  "report_data_input": "sha512(nonce)",
  "quote": "<base64 TDX quote, ~7KB>",
  "cc_eventlog": "<base64 eventlog or null>",
  "tee": "tdx",
  "runtime_class": "kata-qemu-tdx-runtime-rs",
  "pod": "litellm-6d48d45cbc-xgj7w"
}
```

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
  -d '{"model": "z-ai/glm-5.3-flash", "messages": [{"role": "user", "content": "Say OK"}], "max_tokens": 8}' \
  -D /tmp/headers.txt
grep -i x-kubetee /tmp/headers.txt
```

Response headers (both streaming and non-streaming):

| Header | Meaning |
|--------|---------|
| `X-KubeTEE-Nonce` | your nonce, echoed (lowercase hex) |
| `X-KubeTEE-Attestation-Quote` | base64 TDX quote minted on this replica for this request |
| `X-KubeTEE-Attestation-Tee` | `tdx` |
| `X-KubeTEE-Backend` | model name that served (e.g. `z-ai/glm-5.3-flash`) |
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

**KubeTEE binds `SHA512(nonce)` into the quote.**

- The gateway computes `REPORTDATA = SHA512(nonce)` (64 bytes) and passes that to the in-guest attestation agent, which writes it into the TDX quote's `REPORTDATA` field.
- Intel Trust Authority's TDX verification re-computes `SHA512(runtime_data)` over the `runtime_data` you submit with the token and requires it to equal `REPORTDATA`.
- **Therefore, when submitting the quote for appraisal, pass the RAW nonce (the same 64-hex string you generated) as `runtime_data`** — ITA will hash it and match `REPORTDATA`.

```
client generates nonce (64 hex)
   │
   ├─► GET /v1/attestation?nonce=…          (or X-KubeTEE-Nonce on chat)
   │      gateway: REPORTDATA := SHA512(nonce) → quote
   │      quote returned to client
   │
   └─► submit quote to verifier:
          runtime_data = <raw nonce, as sent>
          verifier: SHA512(runtime_data) == REPORTDATA in quote  ✓
```

**Do not** pre-hash the nonce yourself before sending it to KubeTEE (the gateway hashes it), and **do not** send the hash as `runtime_data` to the verifier (send the raw nonce).

---

## Verification path A — Intel Trust Authority (ITA)

KubeTEE quotes are standard Intel TDX DCAP quotes and can be appraised by Intel Trust Authority (or any TDX quote verifier).

### Prerequisites
- An ITA tenant with API key (`*` or `tdx` product), and the verifier URL, e.g. `https://portal.trustauthority.intel.com` (or your on-prem ITA).
- `pip install intel-trustauthority-client` (the Python client) — but note the nonce caveat below.

### The one ITA caveat (important)

The ITA Python client's `collect_evidence` **hashes the nonce itself** (SHA512) before binding — that matches ITA's verification but NOT KubeTEE's binding if you let the client collect evidence (KubeTEE already baked `SHA512(nonce)` into the quote). **Use pre-collected evidence:** submit the KubeTEE-issued quote directly to ITA's `/attest` API with the raw nonce as `runtime_data`.

```python
# pip install intel-trustauthority-client requests
import base64, requests

# 1. Get the quote from KubeTEE (inline or endpoint)
nonce = "<your 64-hex nonce>"            # the RAW one you generated
quote_b64 = "<X-KubeTEE-Attestation-Quote or /v1/attestation .quote>"

# 2. Wrap it in the ITA expected format — TDX evidence JSON envelope
#    (the KubeTEE AA returns {"quote": ..., "cc_eventlog": ...}; ITA's
#    TDX adapter expects the same JSON as its "verifier_nonce"/evidence blob)
evidence = {
    "quote": quote_b64,                 # base64 TDX quote
    # "cc_eventlog" / runtime secrets optional
}

# 3. POST to ITA attest with runtime_data = raw nonce
resp = requests.post(
    "https://portal.trustauthority.intel.com/appraisal/v1/attest",
    headers={"x-api-key": ITA_API_KEY},
    json={
        "verifier_nonce": None,         # not used with pre-collected evidence
        "runtime_data": nonce,          # RAW nonce — ITA hashes it and matches REPORTDATA
        "evidence": evidence,
    },
)
token = resp.json()["token"]            # appraised JWT
```

**What ITA checks:** Intel-signed DCAP quote, TCB level against its TCB policy (configured in the ITA tenant), `REPORTDATA == SHA512(runtime_data)`, debug flags off. It returns a signed appraisal token (JWT) with a policy-verdict claim.

> If your ITA tenant policy allows, set the TCB policy to match your security requirement (e.g. match KubeTEE's PCCS-configured TCB-R `standard` channel).

### Decode the appraisal token

```python
import jwt  # pip install PyJWT
claims = jwt.decode(token, options={"verify_signature": False})  # verify sig per ITA docs
print(claims["policy_ids"], claims["results"])  # 'affirming' / 'constrained' etc.
```

## Verification path B — local DCAP quote verify (offline)

If you run your own DCAP tooling (e.g. `sgx-dcap-quote` verify, Intel DCAP library + PCK cache, or the CoCo `app-starter` verifier), the quote from `/v1` is a raw TDX quote — verify:
1. The quote's `REPORTDATA` equals `SHA512(your nonce)` (offset 568 in the TDREPORT; see the layout below).
2. The Intel DCAP signature chain (PCK cert → Intel root) against Intel's PCS.
3. `td_attributes.debug == 0` (no debug).
4. TCB/TEE TSV values against your policy.

`REPORTDATA` offset: the TDX quote starts with a 48-byte header (incl. `HEADER` type, version, vendor), and `REPORTDATA` is at **offset 568** in the standard `TDREPORT1.6` layout used by the CoCo attester (verified live 2026-09-18: `SHA512(nonce)` bytes found at offset 568 in every KubeTEE quote).

```python
import base64, hashlib
qb = base64.b64decode(quote_b64)
rd = hashlib.sha512(nonce.encode()).digest()
assert qb[568:568+64] == rd, "nonce not bound"
```

---

## Frequently asked questions

**Q: Why is `REPORTDATA` the SHA512 of my nonce, not the raw nonce?**
Intel Trust Authority's verification rule (`tdx_report_data` = cumulative SHA512 of `verifier_nonce || runtime_data || user_data || held_data`) — passing the hash means both KubeTEE and ITA agree on the same field semantics: ITA hashes whatever raw bytes you submit as `runtime_data` and compares to the quote.

**Q: Can I verify the quote on-chain / trustlessly?**
The quote is Intel-signed; on-chain verification would require an Intel PCS oracle — out of scope today. Standard off-chain ITA or DCAP verification is the contract.

**Q: Does attestation add latency to my inference?**
Opt-in only. No header → zero overhead. With the header, one in-guest quote mint rides the response (sub-second, measured on CPU TDX).

**Q: What if the endpoint returns 502?**
The gateway is alive but the in-guest attestation agent is not answering (rare; e.g. right after a guest restart). Chat still works; retry evidence later.

**Q: How do I know the backend GPU guests are also attested?**
Two signals: (1) `X-KubeTEE-Backend-Attested: boot-time (Trustee EAR; east-west mTLS)` — the gateway only has working mTLS to the backend because Trustee issued that backend's cert after a passing TDX quote; (2) the east-west spec (link above) documents the boot-time protocol.

**Q: My language is not Python — what do I do?**
The endpoint contract is plain HTTP + JSON/headers. Verification path B needs any TDX DCAP verifier. ITA also ships Go/Java clients — the same raw-nonce-as-runtime_data rule applies.

---

## Endpoint reference (summary)

| Endpoint / header | Type | Description |
|---|---|---|
| `GET /v1/attestation?nonce=<64hex>` | HTTP | Fresh TDX quote, JSON payload, nonce bound as SHA512 into REPORTDATA |
| `X-KubeTEE-Nonce: <64hex>` (request) | header | Opt-in inline evidence on any chat completion (streaming + non-streaming) |
| `X-KubeTEE-Attestation-Quote` (response) | header | base64 TDX quote minted for this request |
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
