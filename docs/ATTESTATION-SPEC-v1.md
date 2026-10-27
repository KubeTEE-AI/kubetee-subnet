# KubeTEE attestation specification — v1 (partner contract)

**Status:** published 2026-10-23. **This document is the contract** for partners integrating KubeTEE attestation: the reference-value publication schema, the verifier contract, the binding construction, key custody as shipped, and the measurement map. `CLIENT-FACING-ATTESTATION.md` describes the live endpoint behavior and stays the operational companion; where the two describe different binding constructions, **this spec's v1 section is the target contract** and the live section records what runs today.

**Audience:** partner verifiers (e.g. RedPILL-style automation) that consume KubeTEE reference values and verify KubeTEE attestation evidence.
**Related:** [CLIENT-FACING-ATTESTATION.md](./CLIENT-FACING-ATTESTATION.md) (live endpoint), [EAST-WEST-ATTESTED-MTLS.md](./EAST-WEST-ATTESTED-MTLS.md) (east-west mTLS), `gm-miner/attestd/src/eventlog.rs` (reference eventlog replay implementation).

---

## 1. Standards map

KubeTEE attestation speaks standard building blocks; where a standard exists we use it and name the non-standard part explicitly:

| Concept | Standard | As used by KubeTEE |
|---|---|---|
| Evidence | IETF RATS CTR (`conceptual-msg-wrap` / CoRIM evidence profile) — concretely an **Intel TDX quote** | TDX quote + TCG2 CCEL event log, served by the attestation endpoint |
| Reference values | **CoRIM / CoMID** (`tee-reference-values`) | Published as `.well-known/tee-reference-values.cbor` (CoRIM, CBOR/COSE) + a signed JSON projection (below) |
| Appraisal results | **EAR / AR4SI** (EAT + AR4SI trustworthiness vector) | Trustee's appraisal token (AR4SI claims) is included in the evidence bundle |
| Evidence↔response binding | — | **KubeTEE construction** (§4): SHA-256 of a fixed-template RFC 8785 JCS statement, zero-padded to 64 bytes into the quote's `REPORTDATA` |
| Reference-value projection | — | **KubeTEE schema** (§3): `/.well-known/tee-measurements.json` (documented, signed) |

The AR4SI claim → KubeTEE claim mapping for partner adapters (TRUSTWORTHY_* style → RedPILL claims):

| AR4SI group | Maps to |
|---|---|
| `executables` | `serving_software_known_good` |
| `configuration` | `tcb_up_to_date` |
| `environment` | `os_known_good` |

---

## 2. Measurement map — what each register is and what moves it

| Register | Source | What moves it |
|---|---|---|
| **MRTD** | TDX module (SEAM) | OVMF firmware build, TDVF configuration — the immutable VM firmware measurement |
| **RTMR0** | TDX boot-time extend | vmlinuz + initrd (guest kernel 6.18.x, NVIDIA-guest initrd) |
| **RTMR1** | boot kernel params | `KERNELPARAMS_CONFIDENTIAL_NV` + the kata config's kernel_params |
| **RTMR2** | boot scripts (init) | guest image init stage |
| **RTMR3** | init binary + **InitData** | measured rootfs contents; the `cc_init_data` blob (see MRCONFIGID) |
| **MRCONFIGID** | `SHA-384(initdata)` | Any byte of any `initdata-*.toml` — incl. the `policy.rego` container allowlist and the aa/cdh KBS URLs |

Event-log semantics (verified implementation: `gm-miner/attestd/src/eventlog.rs`): the TDX CC event log (CCEL) is TCG2 crypto-agile (`Spec ID Event03` header, SHA-384 digests); replay starts each RTMR at zero and extends `RTMR = SHA-384(RTMR || digest)` per `TDG.MR.RTMR.EXTEND`. Event indices 1–4 are RTMR0–RTMR3; MRTD (index 0) is never extended by a log record. `EV_NO_ACTION` records are informational only. Partners may replay the served `evidence.event_log` against the published RTMRs with any conforming TCG2 replay implementation.

### MRCONFIGID — the composition anchor

**MRCONFIGID = SHA-384(initdata blob) and is THE allowlist anchor** of the KubeTEE verifier contract: the measured container allowlist lives inside the initdata (`policy.rego`'s `policy_data.containers` — image names + UIDs, mirrored out by the attestation service as `agent_policy_claims`), so **an allowlist change moves MRCONFIGID and RTMR3** and requires a new reference-value version (§3).

Implementation facts (for anyone recomputing it): `nim/eastwest/encode-initdata.py` assembles the TOML (`algorithm = "sha384"`, `version = "0.1.0"`) and emits **gzip(mtime=0) + base64** for the `cc_init_data` annotation; the guest measurements extend the SHA-384 over that blob. The CoCo eventlog's RTMR3 InitData event is the anchor's eventlog form.

**dstack mapping (partner side):** RedPILL's check-4 "compose-hash" has no dstack-compatible compose-hash event emitted from KubeTEE guests. RedPILL maps that check to **our anchor (MRCONFIGID / InitData digest)** on their side; we publish the value both in the CoRIM (as the MRCONFIGID CoMID environment claim) and in the JSON projection. **Mapping is the partner's adapter responsibility** — we do not fabricate a compose-hash event.

---

## 3. Reference-value publication (the partner-facing artifact)

Three publications, one version, one lifecycle:

### 3.1 `/.well-known/tee-measurements.json` — signed JSON projection (human + automation)

The **KubeTEE measurement-projection schema** (this section defines it; partners adapt their automation to it — we do not ship a dstack `rtmrs.json` clone):

```json
{
  "schema": "kubetee.tee-measurements/1",
  "version": 3,
  "status": "active",
  "not_before": "2026-10-23T00:00:00Z",
  "key_id": "kubetee-measurements-2026",
  "measurements": {
    "mrtd": "hex:48",
    "rtmr0": "hex:48",
    "rtmr1": "hex:48",
    "rtmr2": "hex:48",
    "rtmr3": "hex:48",
    "mrconfigid": "hex:48"
  },
  "initdata": {
    "sha384": "hex:48",
    "algorithm": "sha384",
    "files": { "aa.toml": "...", "cdh.toml": "...", "policy.rego": "..." }
  },
  "guest": {
    "kata_version": "4.3.1",
    "ovmf_fd_sha256": "hex:64",
    "shim_sha256": "hex:64",
    "kernel": "6.18.x-202-nvidia-gpu",
    "nvidia_guest_driver": "615.71.09"
  },
  "signature": { "alg": "ed25519", "key_id": "kubetee-measurements-2026", "sig": "base64" }
}
```

Signing: `signature.sig` is **Ed25519 over the RFC 8785 (JCS) canonicalized document with `signature` removed**. The verification public key and `key_id` are distributed **out-of-band** (partner onboarding); the key is offline (§5).

**Version lifecycle (strictly enforced by the signer, never rewritten):**

- `version` is a monotonically increasing integer per publication; **history is append-only** — a published version is never edited.
- `status`: `upcoming` (published before the change goes live — partners pre-load) → `active` (live fleet matches) → `revoked` (superseded; stop accepting).
- Multiple `active` rows may exist across role families (gateway CPU-TDX vs GPU-TDX guests differ — one row per guest class), each with its own version stream.

### 3.2 `/.well-known/tee-reference-values.cbor` — the CoRIM (machines)

The same reference values as a standard **CoRIM/CoMID** (veraison `corim-rs` structure; RVPS ingests it natively) — this is the machine format; the JSON projection is its signed human/automation twin. The same CoRIM is pushed to the fleet RVPS (Phase 4 feed).

### 3.3 `ATTESTATION-REFERENCE-MEASURES.md` — human-readable twin

Full `cc_init_data` TOML + blob hash, MRTD/RTMR0-3 + MRCONFIGID values, OVMF/shim sha256, kata version, guest driver — everything a human needs to diff a fleet change against the published baseline.

---

## 4. Binding — the `kubetee.attestation.v1` construction (target contract)

**One construction for all surfaces** (endpoint payload, inline evidence headers, gm-miner keyset). `REPORTDATA` (64 bytes in the quote) is:

```
report_data = SHA-256(JCS(statement)) || 32 zero bytes
```

The statement is this **fixed template** (all three keys required, exact strings, one purpose tag = domain separation):

```json
{"keyset_digest":"sha256:<hex>","nonce":"<64-hex>","purpose":"kubetee.attestation.v1"}
```

- `keyset_digest` = `sha256:<hex>` of the **RFC 8785 JCS** encoding of the currently served keyset (§5) — recomputed by the verifier from the served keyset, never trusted from the response alone.
- `nonce` = the caller's 64-hex nonce (lowercase).
- `purpose` = the literal `kubetee.attestation.v1`.

### Conformance vectors (pinned — unit tests must match byte-for-byte)

Input keyset (canonical fixture):

```json
{"not_after":"2030-01-01T00:00:00Z","subject":"kubetee.attestation.v1/test-vector","tls_public_keys":[{"domain":"llm.kubetee.ai","spki_sha256":"0000000000000000000000000000000000000000000000000000000000000000"}]}
```

| Step | Value |
|---|---|
| `keyset_digest` | `sha256:693868b5f94f4dad208e8e37fe93ebf1be212f3451462b079dc9ba828b8d33ea` |
| Statement (nonce = `0123456789abcdef…` ×4) | `{"keyset_digest":"sha256:693868b5f94f4dad208e8e37fe93ebf1be212f3451462b079dc9ba828b8d33ea","nonce":"0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef","purpose":"kubetee.attestation.v1"}` |
| `SHA-256(statement)` | `755d36ae1b2ea98e9bdb32350b7356b75515e4ecae711a198ade29ec325b14f4` |
| `report_data` (64 B) | `755d36ae…b14f4` + 32 × `00` (see `report_data` row of the JSON projection's `bindings` on any live response) |

The statement itself travels in the bundle as `bindings.report_data_statement` (the exact JCS string), so a verifier recomputes `SHA-256(statement)` and compares to the quote's `REPORTDATA` — no reconstruction ambiguity.

### Live constructions (what runs today)

**FLIPPED 2026-10-27** — the gateway now serves the **v1 construction** as the
wire default. Both gate conditions closed: the gm-miner switch PR
(`kubetee_verify`, [taostat#356](https://github.com/taostat/gm-miner/pull/356))
merged upstream in **v0.5.12**, and the Phala fleet was redeployed on v0.5.12
(`gm-miner-23/24/25`, 2026-10-27). Flip mechanism: `KUBETEE_ATTESTATION_V1=1`
in `values-litellm-na-us-oakland-56.yaml` `envVars` (fleet `8ee7868`) —
switches the quote binding AND adds `keyset`/`bindings`/`evidence`/`appraisal`
atomically. Rollback = unset the flag (the exact legacy shape returns; the
`BindingGuard` fails mixed shapes closed in both directions — never ship v1
fields with the legacy binding or vice versa). Reference-value rows in the
publication schema are `active` as of this date.

| Surface | Live binding | Status |
|---|---|---|
| `GET /v1/attestation` + `X-KubeTEE-Nonce` (gateway) | **v1 JCS statement** as `report_data` (§4; travels verbatim as `bindings.report_data_statement`, `keyset_digest` covers the served keyset) | **live since 2026-10-27** — verified live: `report_data_input: "kubetee.attestation.v1"`, v1 bundle present, nonce echoed, dual-ES256/RS256 `tls_possession` (RS256 via the cert-manager `litellm-tls` key). `appraisal` is **omitted when the per-boot cached EAR is absent** (`/run/kubetee-eastwest/boot-ear.jwt`, minted at startup via the Trustee RCAR path — best-effort by design; the quote + binding stand alone) |
| gm-miner `attestd` (`kubetee_verify`) | accepts the v1 shape **and** legacy dual-read (`BindingGuard` fails mixed shapes closed) | **live since 2026-10-27** (v0.5.12 fleet) — verified live: nonce-bound chat smoke through a v0.5.12 worker HTTP 200 |

The legacy `SHA512(nonce)` construction remains the **rollback shape only** (it
was the wire default 2026-09-18 → 2026-10-27; `report_data_input` names the
active construction on every response). The earlier `SHA512(SPKI-DER ‖ nonce)`
draft is **dropped** — the JCS-statement construction is the single mechanism.

---

## 5. Keyset and key custody (as shipped)

The attestation bundle's `keyset` (served on the endpoint; bound into `report_data` via `keyset_digest`):

```json
{
  "subject": "…",
  "not_after": "RFC3339",
  "tls_public_keys": [{ "spki_sha256": "hex:64", "domain": "llm.kubetee.ai" }],
  "signing_keys": [ … ],
  "e2ee_keys": [ … ]
}
```

`tls_public_keys[].spki_sha256` is the SHA-256 of the DER SubjectPublicKeyInfo of the serving TLS key — **per boot** (below). The same key signs the TLS-possession proof, so the quote, the keyset, and the client's TLS session are the same machine (the split-identity gap is closed).

### Custody classes (documented as-shipped, plus the Phase 5 target)

| Key | Custody as shipped | Notes |
|---|---|---|
| Client TLS key (`llm.kubetee.ai`) | **K8s Secret `litellm-tls`** mounted at `/etc/tls` (fleet `values-litellm-na-us-oakland-56.yaml`) — external PKI / cert-manager issuance path is **retired history** (Vault/VSO removed 2026-07-23; `SECRET-MANAGEMENT-STRATEGY.md`) | **Phase 5 target:** per-boot P-256 keygen in memory → ACME DNS-01 (SANs: `llm.kubetee.ai` + a unique per-boot SAN vs LE's 5-duplicate limit) → cert+key only to container-local tmpfs `/run/kubetee-tls` → fail-closed. The per-boot SPKI feeds `tls_public_keys` and `keyset_digest` |
| East-west keys (`eastwest-ca`, `eastwest-nim`, `eastwest-litellm`) | **KBS (Trustee) secret store** — seeded with `kbs-client set-resource` (`default/eastwest-ca`, `default/eastwest-nim`, `default/eastwest-litellm`), fetched in-guest via CDH (`fetch-certs.sh` → `http://127.0.0.1:8006/cdh/resource/…`) | Written to the host-shared `/certs` emptyDir **today**; Phase 5 same-roll scope moves the fetch into the using container's entrypoint → that container's tmpfs |
| Signing keys (`signing_keys` in keyset) | Same custody class as east-west (KBS) unless a row documents otherwise | |
| Reference-value signing key (`key_id: kubetee-measurements-2026`) | **Offline Ed25519** — private key never in cluster or repo; pubkey + `key_id` distributed to partners out-of-band | CoRIM signing uses COSE_Sign1 per the standard (evaluated at build time); the JSON projection's Ed25519 signature is as specified above |

### Verification contract (what a partner must check)

1. **Quote authenticity:** Intel TDX DCAP chain (PCK → Intel root) against Intel PCS or ITA; `td_attributes.debug == 0`; TCB status per your policy (KubeTEE PCCS runs TCB-R `standard`).
2. **Binding:** `SHA-256(bindings.report_data_statement)` + 32 zero bytes == quote `REPORTDATA` (offset 568 in the TDREPORT1.6 layout — live-verified 2026-09-18), and the statement's `keyset_digest` == `sha256(JCS(keyset))` **recomputed from the served keyset**, and the statement's `nonce` == your request nonce.
3. **Reference values:** replay `evidence.event_log` (TCG2 crypto-agile, SHA-384 extends) → RTMR0-3 == published values; MRTD == published; **MRCONFIGID == published `initdata.sha384`** (the anchor). `evidence.vm_config` (incl. `agent_policy_claims`) must match the published `initdata` files.
4. **Appraisal:** `evidence.ear_token` (Trustee AR4SI) carries the TCB/config appraisal; map per §1.
5. **Keyset freshness:** `keyset.not_after` in the future; `spki_sha256` matches **your TLS session's leaf SPKI** (TLS-possession) if you are binding to the serving guest.

Conformance: a verifier that passes the §4 vectors and the five checks above is a conforming KubeTEE v1 verifier. Report gaps to KubeTEE — do not patch around them in the adapter without telling us.

---

## 6. Claim → control mapping (scope honesty)

| Claim | Control | Honesty note |
|---|---|---|
| Serving software is known-good | event-log replay vs published RTMRs/MRTD + allowlist (MRCONFIGID) | Images are **digest-pinned** (`@sha256:` in pod specs and `policy_data.containers`) — **NOT signed or encrypted**; digest pinning is the whole control |
| TCB up to date | TDX quote TCB status (TCB-R `standard` channel) | Partner policy must choose its TCB floor |
| OS / guest known-good | RTMR0-2 + guest image measurement | Guest kernel 6.18.x + NVIDIA guest driver 615.71.09 (measured) |
| Composition / allowlist | **MRCONFIGID (InitData digest)** | See §2 anchor semantics; partners with a compose-hash concept map it themselves |
| Boot-time backend attestation | east-west mTLS (Trustee-gated cert issuance) | Per-request GPU quotes are **out of scope** (`X-KubeTEE-Backend-Attested: boot-time`) |

**Intel Trust Authority attestation tokens available on request** — KubeTEE quotes are standard Intel TDX DCAP quotes; ITA appraisal works per `CLIENT-FACING-ATTESTATION.md` (path A): ITA appraises the **quote** (DCAP/TCB/debug-off), and the relying party checks the **v1 binding** (`SHA-256(bindings.report_data_statement) + 32 zero bytes == REPORTDATA`, keyset digest recomputed). The legacy `SHA512(nonce)` + raw-nonce-as-`runtime_data` rule applies only to the rollback shape, not the live v1 construction.
