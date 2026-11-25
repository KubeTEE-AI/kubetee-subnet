# Attestation reference measures — SGLang serving backend (`nim-terminator`)

**Status: PUBLISHED (2026-11-25) — measures captured & cross-validated, record
signed (Ed25519, `key_id: kubetee-measurements-2026-11-25`) and live at
[`tee-measurements-sglang.tdx.json`](https://kubetee.ai/.well-known/tee-measurements-sglang.tdx.json).**
Prepared 2026-11-24, captured 2026-11-25, signed & published 2026-11-25.
This is the human twin of the machine record
[`tee-measurements-sglang.tdx.draft.json`](./tee-measurements-sglang.tdx.draft.json).
It documents **the measures and the container used for the attestation** of the
east-west SGLang model backend — the guest that the measured AMD SEV-SNP LiteLLM
gateway calls over strict mTLS (the "backend hop" of
[EAST-WEST-ATTESTED-MTLS.md](./EAST-WEST-ATTESTED-MTLS.md)).

**The `nim-terminator` role is TEE-generic; this record is one TEE of it.** The
role names the SGLang/NIM backend regardless of hardware. The currently deployed
NIM backends run on Intel TDX nodes, so this record is the `tee: "tdx"` sibling
and its filename carries `.tdx.`. An AMD SEV-SNP NIM deployment would publish a
separate `tee: "snp"` sibling record with `evidence.snp` populated and
`quote`/`event_log`/`tdx` null — the same `role`, a different TEE. Do not treat
the TDX registers below as intrinsic to the role.

Published 2026-11-25 as
`https://kubetee.ai/.well-known/tee-measurements-sglang.tdx.json` (role-scoped
`.tdx.` filename — the same `role`, a different TEE sibling of the SNP
`litellm` record at `/.well-known/tee-measurements.json`, which is a separate
document and is not overwritten by this record) + this human twin. The record
contains no `PENDING-CAPTURE` field — see [Publication gate](#5-publication-gate).

Companion specs (authoritative; this file is a role record, not a
re-statement of the protocol):

| Spec | Covers |
|---|---|
| [ATTESTATION-SPEC-v1.md](./ATTESTATION-SPEC-v1.md) | `kubetee.attestation.v1` evidence, report-data binding, publication lifecycle |
| [CLIENT-FACING-ATTESTATION.md](./CLIENT-FACING-ATTESTATION.md) | endpoint guide for verifiers |
| [EAST-WEST-ATTESTED-MTLS.md](./EAST-WEST-ATTESTED-MTLS.md) | the backend hop this record measures |
| [tee-measurements-sglang.tdx.schema.json](https://kubetee.ai/.well-known/tee-measurements-sglang.tdx.schema.json) | machine-readable schema for the published record (`kubetee.tee-measurements/1`) |

---

## 1. Source and container provenance

The serving engine is built from **KubeTEE's SGLang fork
[`KubeTEE-AI/sglang`](https://github.com/KubeTEE-AI/sglang)** (public fork of
[`sgl-project/sglang`](https://github.com/sgl-project/sglang)), in GitHub
Actions on GitHub-hosted runners only, and consumed `@sha256:` digest-pinned.
The strict-mTLS transport and the evidence route are **fork source code inside
the attested image** — not a sidecar or a proxy — so they are covered by the
guest measurement. Container provenance (image identity, the exact fork commit,
the CI build, and the full container set in the guest):

| Field | Value |
|---|---|
| Image (quote-minting build) | `ghcr.io/kubetee-ai/sglang:kimi-k31-granian-mtls-45497390909-b8f8015d@sha256:68cb8790dd1a959831f9bb10403c6f68142ddf9b5963722d3aa2b5b3f1cf59cb` |
| Fork source | `KubeTEE-AI/sglang`, `kubetee/kimi-k31-granian-mtls-day0` @ [`b8f8015d3291`](https://github.com/KubeTEE-AI/sglang/commit/b8f8015d329182a8d973aacc71e3d7ca371a5e22) |
| CI run | [`45497390909`](https://github.com/KubeTEE-AI/sglang/actions/runs/45497390909) |
| RuntimeClass | `kata-qemu-nvidia-gpu-tdx-runtime-rs` |
| Validated | 2026-11-25 on the live Kimi-K3.1-Pro backend guest (Luxembourg) — the guest that minted the reference measurements |

Launch registers measure firmware + kernel + initrd + cmdline and **not
application code**, so canary image rolls that change only app code keep the
same registers. Full fork/branch/patch provenance, the transport source layout,
the model-agnostic overlay base images and the guest's complete container set
are in `docs/attestation-internal-technical-notes-2026-11-25.md` (root repo).

---

## 2. Measured launch inputs (TDX / NVIDIA-CC)

These are the inputs a verifier pins. The TDX launch registers below were
captured 2026-11-25 from the booted guest's hardware quote and cross-checked
(report-data binding + CCEL replay) — see §2.3 and §5.

### 2.1 InitData → MRCONFIGID / `host_data`

The guest's InitData is the gzip+base64 blob in the Kata annotation
`io.katacontainers.config.hypervisor.cc_init_data`. Per
[ATTESTATION-SPEC-v1.md](./ATTESTATION-SPEC-v1.md) §2, Kata 4.x computes
**SHA-384(uncompressed InitData TOML)**; the first 32 bytes are the SNP
`host_data`, and the full 48-byte digest is the TDX **MRCONFIGID**.

The deployed guest's InitData (role `image-gen`, committing `policy.rego`,
`aa.toml`, `cdh.toml` at algorithm `sha384`, KBS endpoint
`https://kbs.kubetee.ai`) digests to the `MRCONFIGID` in §2.3 — recomputed from
the annotation and confirmed equal to the booted guest's quote byte-for-byte
(2026-11-25).

### 2.2 Measured agent policy

The `policy.rego` inside InitData is **measured** — changing it changes
MRCONFIGID, so enabling a denied capability is a measurement change a verifier
would reject. The posture denies `ExecProcessRequest` and `WriteStreamRequest`
(host cannot exec into the guest or write to processes) while allowing the
standard container-lifecycle and read surface. The full request table is in
`docs/attestation-internal-technical-notes-2026-11-25.md` (root repo).

### 2.3 Guest composition

| Input | Value |
|---|---|
| RuntimeClass | `kata-qemu-nvidia-gpu-tdx-runtime-rs` |
| Kata | **`4.4.0`** (upstream `f9cbda4d235b345340bf461e4aaba8c89e841d8d`, kata-deploy chart `4.4.0+kubetee.1`) |
| Shim | `/opt/kata/runtime-rs/bin/containerd-shim-kata-v2`, sha256 `82cd97b52ac89b6a73871d5ca68b61f840c5d84e030f28b72dc03f9baab9a73a` (overlay `v4.4.0-fix11649-t15t16-vsocktimeout`) |
| Firmware (OVMF) | `/opt/kata/share/ovmf/OVMF.inteltdx.fd`, **`edk2-stable202608`** (in-tree lazy-accept) — fd sha256 **`2a2dc2710b0cfafc813310c7e98c67b72b919b8e1572d52a4c79466a2e499226`** |
| NVIDIA guest driver | `615.71.09` (`kata-containers/versions.yaml` `nvidia.driver`) |
| **TDX launch registers** | captured 2026-11-25 from the booted quote (TDINFO) — see the table below |
| `MRTD` cross-check | captured from the quote's TDINFO (MRTD is TDX-module-measured and cannot be reconstructed from launch inputs). `RTMR0-3` independently cross-checked by CCEL replay — both matched (§2.5). |

**TDX launch registers (captured 2026-11-25, `nim-terminator` / Kimi-K3.1-Pro):**

| Register | Value (48-byte SHA-384, hex) | Extended by |
|---|---|---|
| **MRTD** | `382d7bb61e152a5cc6eb22922a4dc9d33025211e24ec199fe38d6233c39cd86bf633e3c4f6e62393cf7ce6da91069ca0` | TDX module (initial TD: OVMF + kernel + initrd + cmdline) |
| **MRCONFIGID** | `0484a58e5927efd31bf871c74bcc9f1768f4335bb92340176989b3c5b320f9341d772b9e3e9c4fe4d824613cc19e6e0b` | from `cc_init_data` (= §2.1 InitData SHA-384) |
| **RTMR0** | `14f01287aefb3ac196451163aa8cf68cc1635083b24eb317256288815a5b48bbe7cdf2e2395ebf0474b3e528d2004014` | firmware / CCEL |
| **RTMR1** | `97fa8ac275f656b876de7c68709608bfe6ace60b58a3b8fb6e990c15bd8711ce8807ed86956f39b62afb9a9daee80227` | kernel cmdline (incl. `agent.guest_components_rest_api=all`) |
| **RTMR2** | `77903a48ffcc66809d3f01a9853186ac08bc0081d06e4d05a0e0307450188e08d9f21b9c77e6747df0a90e65d7e3bff9` | initrd / OS |
| **RTMR3** | `000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000` | unused (zero) |
| **MROWNER / MROWNERCONFIG** | `0000…0000` (both zero) | unset (as expected) |

These registers are a function of the guest's **launch config** (OVMF
`edk2-stable202608` + kernel `6.18.62-211-nvidia-gpu` + initrd + cmdline +
`cc_init_data`), **not** the in-guest `sglang` container image — the transport /
evidence-route code is application-level and does not change MRTD/RTMR. So these
values hold across canary image rolls that change only the app code.

Capture procedure (per release): (a) MRCONFIGID from the InitData digest as in
§2.1; (b) `MRTD` + `RTMR0-3` from a booted guest's hardware quote via the
`/kubetee/evidence` route (§2.5), cross-checked by CCEL replay; (c)
OVMF/shim sha256 per node from the host. Each measure-changing release goes
through the publication lifecycle in
[ATTESTATION-SPEC-v1.md](./ATTESTATION-SPEC-v1.md) §3 (change-notice →
`upcoming` → roll → `active`, strictly increasing version).

### 2.4 Report-data binding (agreed contract for this role)

| Field | Value |
|---|---|
| Schema | `kubetee.attestation.v1` |
| `report_data` | `SHA-256(JCS(statement)) ‖ 32 zero bytes` (64 bytes) |
| statement (nonce-bound form) | `{"keyset_digest":"sha256:<hex>","nonce":"<64-hex>","purpose":"kubetee.attestation.v1"}` |
| statement (epoch form, cached) | `{"epoch_id","issued_at","valid_until","keyset_digest","purpose"}` |
| Nonce | caller-supplied, 64 lowercase hex |
| Evidence | Intel TDX DCAP quote at `UpToDate` TCB, **debug bit clear** (AMD SEV-SNP is the gateway hop only) |
| Per-request signature key | `tee-pubkey` — the backend's **per-epoch evidence-signing key** (Ed25519), distinct from its TLS serving key and from the gateway's keys. Its public half is committed via `keyset_digest` in the epoch statement (and therefore bound into the hardware `report_data`). |
| Per-request signature input | `SHA-256(quote) ‖ SHA-256(nonce) ‖ epoch_id ‖ counter`, where `counter` is a monotonic per-epoch request counter. Verified with `tee-pubkey`. |

The 64-byte convention is shared with the SNP gateway record. The two binding
forms (nonce-bound and cached epoch) and the two-layer freshness model are
specified in [CLIENT-FACING-ATTESTATION.md](./CLIENT-FACING-ATTESTATION.md)
"Backend evidence for `nim-terminator`".

> **This role is TEE-generic.** These TDX registers describe the currently
> deployed NIM backends (Intel TDX nodes). An AMD SEV-SNP NIM deployment
> publishes a sibling record for the same role with `evidence.snp` populated and
> `quote`/`event_log`/`tdx` null; its binding is the SNP `report_data` convention
> of [ATTESTATION-SPEC-v1.md](./ATTESTATION-SPEC-v1.md) §4.

### 2.5 Capture method and cross-checks (2026-11-25)

The registers in §2.3 are captured **from the live guest, with no pod disruption
and no `ExecProcess`**, via the in-guest evidence surface (CoCo's
`GET 127.0.0.1:8006/aa/evidence`, relayed by our `/kubetee/evidence` route,
enabled by the guest kernel parameter `agent.guest_components_rest_api=all`).
`GET https://kimi-k3-1-pro.eu-lu-luxembourg-133.inference.kubetee.ai:8443/kubetee/evidence?role=nim-terminator&nonce=<64-hex>`
over strict mTLS with the gateway east-west identity returns the
`kubetee.attestation.v1` envelope (epoch statement, Ed25519 `tee-pubkey`,
monotonic counter, `quote`, `cc_eventlog`); `MRTD`, `MRCONFIGID` and `RTMR0-3`
are read from the quote's TDINFO.

**Cross-checks (both passed):**

- **Report-data binding** — the quote's 64-byte `report_data` equals
  `SHA-256(epoch statement) ‖ 32 zero bytes`, recomputed independently: **match**.
- **CCEL replay** — the 22-record CC event log replayed with the TDX rule
  `RTMR[i] = SHA-384(RTMR[i] ‖ digest)` (records 1–4 → RTMR0–3) reproduces
  **all four** quote RTMRs exactly. MRTD is TDX-module-measured and is not in
  the event log.
- **MRCONFIGID live-confirm** — equals the recomputed InitData SHA-384 (§2.1).

---

## 3. What is proven, and what is not

Proven / in the measured surface:

- The TLS key is built **in-guest** from attested CDH delivery — no Kubernetes
  Secret, no host mount, no unmeasured proxy in the trust path. TLS terminates
  inside the measured SGLang process (`:8443` Granian strict mTLS).
- Key possession is provable: the backend signs the caller's nonce with the
  TLS key.
- Exec into the guest is **measured-denied** (`ExecProcessRequest := false`),
  and stopping the pod destroys the VM and its decrypted memory.
- The transport code itself is inside the attested image, built from our public
  fork at an exact commit by a public, SHA-pinned workflow.

Not claimed:

- **Byte-identical reproducible digest** from a third party's own build. As with
  the gateway record: transitive dependency resolution at build time (only one
  requirements file is fully hash-locked) and build-timestamp normalization
  (`SOURCE_DATE_EPOCH` / layer-tar normalization) block bit-reproducibility.
  Independent **rebuild + verify** is available (public source, digest-pinned
  bases, SHA-pinned workflow). We state bit-reproducibility only once a
  third-party rebuild actually matches.
- Fresh per-request **GPU** evidence on the backend hop (boot appraisal today;
  the scheduled composite CPU + 8-GPU appraisal is designed and in
  implementation — [EAST-WEST-ATTESTED-MTLS.md](./EAST-WEST-ATTESTED-MTLS.md)).
- A bit-for-bit independent recomputation of `MRTD` from firmware inputs — it is
  captured from the hardware quote and cross-checked via the CCEL replay + the
  report-data binding, but no Intel TDX `tdx-measure`-equivalent recompute has
  run (that tool has no TDX MRTD mode).

---

## 4. Publication gate

A generated-but-unsigned record is a **draft**, not evidence — a successful
hardware appraisal does not establish the claim you are publishing. This record
was published 2026-11-25 only after the §2.5 capture and cross-checks passed,
both machine-readable projections were published and registered, and the offline
Ed25519 signature (`key_id: kubetee-measurements-2026-11-25`, RFC 8785 JCS over
the document with `signature` removed) was in place and independently verified
against the published verification key
([`tee-measurements-signing-key-2026.json`](https://kubetee.ai/.well-known/tee-measurements-signing-key-2026.json)).

The verification key (public half) — mirrored here independently of the machine
record so a website-repo change cannot silently swap it. Verify the two agree
before trusting a record signature:

| Field | Value |
|---|---|
| `key_id` | `kubetee-measurements-2026-11-25` |
| algorithm | `Ed25519` (RFC 8785 JCS, without the `signature` member) |
| public `x` | `FekS2fBdTq91Xe6IIUoGWot_ig7uybpX9vhO5WN_1Wc` |
| SPKI (DER, base64url) | `MCowBQYDK2VwAyEAFekS2fBdTq91Xe6IIUoGWot_ig7uybpX9vhO5WN_1Wc` |
| SPKI SHA-256 | `sha256:046b732aa6bb0695a15c00af9d58d64661e5e27ec3d169851ea77dc0bbf6f530` |
The full gate checklist and its status are in
`docs/attestation-internal-technical-notes-2026-11-25.md` (root repo).

---

## 5. The CoRIM twin and RVPS registration

Alongside the JSON record, KubeTEE publishes a **CoRIM** (Concise Reference
Integrity Manifest, IETF RATS) so a Verifier's **RVPS** (Trustee Reference Value
Provider Service) can appraise a TDX quote's launch registers against this
approved reference state.

- **CoRIM (CBOR):** [https://kubetee.ai/.well-known/tee-reference-values.cbor](https://kubetee.ai/.well-known/tee-reference-values.cbor)
- **Detached signature:** `/.well-known/tee-reference-values.cbor.sig` (Ed25519,
  same `key_id: kubetee-measurements-2026-11-25` as the JSON record)
- **Digest:** `/.well-known/tee-reference-values.cbor.sha256`
- **Human twin + derived URIs:** `/.well-known/tee-reference-values.json`

The CoRIM is canonical CBOR (RFC 8949), CoRIM tag **501** wrapping one CoMID tag
**506** with a single compound reference-triple (all six registers must match
together — the RATS "compound reference value" model,
[trustee#350](https://github.com/confidential-containers/trustee/issues/350)).
Digests are SHA-384 (`alg = 7`). The build is byte-reproducible:
`kubetee-subnet/scripts/build-tee-reference-values-corim.py`.

### Reference-value URIs (RVPS)

Trustee's CoRIM extractor (`rvps/src/extractors/corim/`, v0.23.0) maps each
reference value to a URI `class.vendor / class.model / mkey / digests`. The model
class identifies the **Kimi-K3.1-Pro** model (`vendor = kubetee`,
`model = sglang-kimi-k3-1-pro`) — it carries no deployment or node suffix. These
land as:

| URI | Register | Value (SHA-384) |
|---|---|---|
| `kubetee/sglang-kimi-k3-1-pro/mr_td/digests` | `MRTD` | `382d7bb6…1069ca0` |
| `kubetee/sglang-kimi-k3-1-pro/rtmr_0/digests` | `RTMR0` | `14f01287…2004014` |
| `kubetee/sglang-kimi-k3-1-pro/rtmr_1/digests` | `RTMR1` | `97fa8ac2…e80227` |
| `kubetee/sglang-kimi-k3-1-pro/rtmr_2/digests` | `RTMR2` | `77903a48…e3bff9` |
| `kubetee/sglang-kimi-k3-1-pro/rtmr_3/digests` | `RTMR3` | `00000000…00000000` |
| `kubetee/sglang-kimi-k3-1-pro/mr_config_id/digests` | `MRCONFIGID` | `0484a58e…19e6e0b` |

(Full values are in the JSON record and the CoRIM; truncated here for width.)

**These URIs are namespaced on purpose.** The stock `default_cpu` attestation
policy queries **bare** ids (`mr_td`, `rtmr_1`, `rtmr_2`, `xfam`, …), so this
registration is **inert to live appraisal** — it cannot accidentally affirm an
arbitrary guest. Only a policy that explicitly queries these namespaced URIs
appraises against them. A KubeTEE appraisal policy opts in like this:

```rego
package policy

import rego.v1

# Appraise the TDX launch registers against the KubeTEE reference state
# registered in RVPS (kubetee/sglang-kimi-k3-1-pro/.../digests). Each
# query_reference_value("<uri>") returns the list of approved hex digests, so a
# quote register is affirmed when it is a member of that list.
executables := 3 if {
	input.tdx
	input.tdx.quote.body.mr_td in query_reference_value("kubetee/sglang-kimi-k3-1-pro/mr_td/digests")
	input.tdx.quote.body.rtmr_1 in query_reference_value("kubetee/sglang-kimi-k3-1-pro/rtmr_1/digests")
	input.tdx.quote.body.rtmr_2 in query_reference_value("kubetee/sglang-kimi-k3-1-pro/rtmr_2/digests")
}

hardware := 2 if {
	input.tdx
	input.tdx.quote.body.mr_config_id in query_reference_value("kubetee/sglang-kimi-k3-1-pro/mr_config_id/digests")
}
```

Compare the quote's `report_data` / `mr_config_id` against the record's
`initdata.sha384` for the InitData binding, exactly as in the JSON twin.

These URIs are namespaced (`kubetee/<model>/<register>/digests`) on purpose: the
stock `default_cpu` attestation policy queries bare ids, so this registration is
inert to live appraisal and cannot accidentally affirm an arbitrary guest. Only a
policy that explicitly queries these URIs appraises against them.

The CoRIM's detached signature is a **publication integrity artifact** (same
offline key as the JSON record); verify it offline before ingesting if you want
supply-chain assurance. The build, the byte-reproducible generator
(`kubetee-subnet/scripts/build-tee-reference-values-corim.py`), and the Trustee
RVPS ingestion mechanics (the standard gRPC `RegisterReferenceValue` call) are
documented in `docs/attestation-internal-technical-notes-2026-11-25.md` (root
repo).
