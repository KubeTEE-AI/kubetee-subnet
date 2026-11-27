# Attestation reference measures — SGLang serving backend (`nim-terminator`)

This document is the **values record** for the TDX launch measures and
container provenance of KubeTEE's east-west SGLang model backend — the guest
that the measured AMD SEV-SNP LiteLLM gateway calls over strict mTLS (the
"backend hop" of [EAST-WEST-ATTESTED-MTLS.md](./EAST-WEST-ATTESTED-MTLS.md)).
Protocol, framing and binding are specified in
[ATTESTATION-SPEC-v1.md](./ATTESTATION-SPEC-v1.md); the client procedure is
[CLIENT-FACING-ATTESTATION.md](./CLIENT-FACING-ATTESTATION.md).

**Where these values are consumed: the signed registry (live allowlist).** The
registers below are published as **records** in the single signed
[`tee-measurements-registry.json`](https://kubetee.ai/.well-known/tee-measurements-registry.json)
(schema `kubetee.tee-measurements-registry/1`). A verifier — and the gateway's
circuit breaker — accepts live evidence iff its registers match **any active
record** for the same `tee` (`policy.match: "any-active-record"`); there is no
per-model / per-image pin. Records are retained **current + previous generation
per chain** (a chain = model + role + tee; a generation = one immutable
`image_ref`): both stay active so **both** verify during and after a rollout,
and a record leaves the allowlist only when a third newer generation lands in
its chain (or it is hard-expired / `status: "deprecated"` / `"revoked"`).
Measurements change only at a rollout — there is no time-based re-capture and no
fixed validity window. `valid_until` is optional, reserved for manual
hard-expiry (for example throwaway canaries). Rotation is a re-capture + re-add
(or `--prune` to drop the old one).

**The `nim-terminator` role is TEE-generic.** The role names the SGLang/NIM
backend regardless of hardware. The deployed NIM backends run on Intel TDX
nodes, so the records below are the `tee: "tdx"` family and their filenames
carry `.tdx.`. An AMD SEV-SNP NIM deployment publishes a separate `tee: "snp"`
sibling record with `evidence.snp` populated and `quote`/`event_log`/`tdx` null —
the same `role`, a different TEE. Do not treat the TDX registers below as
intrinsic to the role.

---

## 1. Record inventory and provenance

Current registry records (each one measured `(model × node)` launch):

| Record id | Model | Captured | Valid until | Capture node |
|---|---|---|---|---|
| `kimi-k3.1-pro-kimi-k31-granian-mtls-45497390909-b8f8015d` | `moonshotai/kimi-k3.1-pro` | 2026-11-25T01:28:17Z | 2027-02-23T01:28:17Z | `kimi-k3-1-pro-sglang-b300-cc-0` (lu-b300-39) |
| `mimo-v2.6-pro-mtls-evidence-3117f580-20261125-d12bfac` | `xiaomi/mimo-v2.6-pro` | 2026-11-25T17:41:08Z | 2027-02-23T17:41:08Z | `mimo-v2-6-pro-rl-sglang-b200-cc-0` (tx-b200-16) |
| `mimo-v2.6-pro-mtls-evidence-3117f580-20261125-lub30040` | `xiaomi/mimo-v2.6-pro` | 2026-11-26T10:28:53Z | 2027-02-24T10:28:53Z | `mimo-v2-6-pro-rl-sglang-b300-cc-0` (lu-b300-40) |

A new measured model — or the same model on a new node — is simply one more
record; the verifier needs no change.

**Deployed generation note (2026-11-27).** All three live pods (MiMo
tx-b200-16, MiMo lu-b300-40, Kimi-K3.1-Pro on `kimi-k3-1-pro39-sglang-b300-cc-0`
/ lu-b300-39) now run the **freshgpu** image generation
(`mtls-evidence-freshgpu-3117f580-20261126`, provenance below) with the fresh
CPU+8-GPU mint enabled. Launch registers are unchanged from the table — an
image roll that changes only application code keeps the same registers — so
live evidence from these pods still matches the active records above
(`policy.match: any-active-record`, no per-image pin). Per the retention policy,
a new record per (model × node) is captured and appended as the new generation
(20261126) at the pods' evidence captures; the 20261125 records above stay
active as the previous generation until a third generation lands.

The serving engine is built from **KubeTEE's SGLang fork
[`KubeTEE-AI/sglang`](https://github.com/KubeTEE-AI/sglang)** (public fork of
[`sgl-project/sglang`](https://github.com/sgl-project/sglang)), in GitHub
Actions on GitHub-hosted runners only, and consumed `@sha256:` digest-pinned.
The strict-mTLS transport and the evidence route are **fork source code inside
the attested image** — not a sidecar or a proxy — so they are covered by the
guest measurement. Per-record container provenance:

| Record | Image (quote-minting build) | Fork source | CI run |
|---|---|---|---|
| Kimi (lu-b300-39) | `ghcr.io/kubetee-ai/sglang:kimi-k31-granian-mtls-45497390909-b8f8015d@sha256:68cb8790dd1a959831f9bb10403c6f68142ddf9b5963722d3aa2b5b3f1cf59cb` | `kubetee/kimi-k31-granian-mtls-day0` @ [`b8f8015d3291`](https://github.com/KubeTEE-AI/sglang/commit/b8f8015d329182a8d973aacc71e3d7ca371a5e22) | [`45497390909`](https://github.com/KubeTEE-AI/sglang/actions/runs/45497390909) |
| MiMo (tx-b200-16, lu-b300-40) | `ghcr.io/kubetee-ai/sglang:mtls-evidence-3117f580-20261125@sha256:982c8c10f59c5e8fb724a9cc5d67e8f777c5fde36704d79a5e0dba5f727a9590` | `kubetee-overlay` @ [`d12bfac85c87`](https://github.com/KubeTEE-AI/sglang/commit/d12bfac85c87076fd80983751d4f10f5dcb5c377) | [`45639037187`](https://github.com/KubeTEE-AI/sglang/actions/runs/45639037187) |
| **freshgpu** (deployed 2026-11-27 on all three live pods — MiMo ×2 + Kimi K3.1-Pro pro39) | `ghcr.io/kubetee-ai/sglang:mtls-evidence-freshgpu-3117f580-20261126@sha256:b1b9b705cc7db51e20c9405b3c3c5e6a8e97f6d48dbf4596ff5541777c44148e` | `kubetee-overlay` @ [`b25fafc964cd`](https://github.com/KubeTEE-AI/sglang/commit/b25fafc964cda56ff7d8cf32f59a38f003a95abc) | [`45882334220`](https://github.com/KubeTEE-AI/sglang/actions/runs/45882334220) |

RuntimeClass `kata-qemu-nvidia-gpu-tdx-runtime-rs` for both. Launch registers
measure firmware + kernel + initrd + cmdline and **not** application code, so
canary image rolls that change only app code keep the same registers. Full
fork/branch/patch provenance, the transport source layout, the model-agnostic
overlay base images and the guest's complete container set are in
`docs/attestation-internal-technical-notes-2026-11-25.md` (root repo).

---

## 2. Measured launch inputs (TDX / NVIDIA-CC)

These are the inputs a verifier pins.

### 2.1 InitData → MRCONFIGID / `host_data`

The guest's InitData is the gzip+base64 blob in the Kata annotation
`io.katacontainers.config.hypervisor.cc_init_data`. Per
[ATTESTATION-SPEC-v1.md](./ATTESTATION-SPEC-v1.md) §2, Kata 4.x computes
**SHA-384(uncompressed InitData TOML)**; the first 32 bytes are the SNP
`host_data`, and the full 48-byte digest is the TDX **MRCONFIGID**.

All deployed backend records share one InitData (role `image-gen`, committing
`policy.rego`, `aa.toml`, `cdh.toml` at algorithm `sha384`, KBS endpoint
`https://kbs.kubetee.ai`):

- **InitData SHA-384 (= MRCONFIGID):**
  `0484a58e5927efd31bf871c74bcc9f1768f4335bb92340176989b3c5b320f9341d772b9e3e9c4fe4d824613cc19e6e0b`
- **`host_data` prefix-32 (SNP sibling field):**
  `0484a58e5927efd31bf871c74bcc9f1768f4335bb92340176989b3c5b320f934`

Recomputed from the annotation and confirmed byte-for-byte equal to the booted
guests' quotes.

### 2.2 Measured agent policy

The `policy.rego` inside InitData is **measured** — changing it changes
MRCONFIGID, so enabling a denied capability is a measurement change a verifier
would reject. The posture denies `ExecProcessRequest` and `WriteStreamRequest`
(the host cannot exec into the guest or write to its processes) while allowing
the standard container-lifecycle and read surface. The full request table is in
`docs/attestation-internal-technical-notes-2026-11-25.md` (root repo).

### 2.3 Guest composition

| Input | Value |
|---|---|
| RuntimeClass | `kata-qemu-nvidia-gpu-tdx-runtime-rs` |
| Kata | **`4.4.0`** (upstream `f9cbda4d235b345340bf461e4aaba8c89e841d8d`, kata-deploy chart `4.4.0+kubetee.1`) |
| Shim | `/opt/kata/runtime-rs/bin/containerd-shim-kata-v2`, sha256 `82cd97b52ac89b6a73871d5ca68b61f840c5d84e030f28b72dc03f9baab9a73a` (overlay `v4.4.0-fix11649-t15t16-vsocktimeout`) |
| Firmware (OVMF) | `/opt/kata/share/ovmf/OVMF.inteltdx.fd`, **`edk2-stable202608`** (in-tree lazy-accept) — fd sha256 **`2a2dc2710b0cfafc813310c7e98c67b72b919b8e1572d52a4c79466a2e499226`** |
| NVIDIA guest driver | `615.71.09` (`kata-containers/versions.yaml` `nvidia.driver`) |

---

## 3. TDX launch registers (captured from booted quotes)

| Register | Kimi (lu-b300-39) | MiMo (tx-b200-16) | MiMo (lu-b300-40) | Extended by |
|---|---|---|---|---|
| **MRTD** | `382d7bb61e152a5cc6eb22922a4dc9d33025211e24ec199fe38d6233c39cd86bf633e3c4f6e62393cf7ce6da91069ca0` | *(identical)* | *(identical)* | TDX module (initial TD: OVMF + kernel + initrd + cmdline) |
| **MRCONFIGID** | `0484a58e5927efd31bf871c74bcc9f1768f4335bb92340176989b3c5b320f9341d772b9e3e9c4fe4d824613cc19e6e0b` | *(identical)* | *(identical)* | from `cc_init_data` (= §2.1 InitData SHA-384) |
| **RTMR0** | `14f01287aefb3ac196451163aa8cf68cc1635083b24eb317256288815a5b48bbe7cdf2e2395ebf0474b3e528d2004014` | `e5f1d7d291f34258fec25a5ba409a9b3a7a17d7057756fa556b22fad5e8d76d47f50be3d294d210e85039bacc57b1e19` | `f448be9c9b0a239e72852dc0711f87593a961823318ece53123693e555c08ee4fdd5908d9f12dafbc251f0b4ef19ef0b` | firmware / CCEL — **node-specific** |
| **RTMR1** | `97fa8ac275f656b876de7c68709608bfe6ace60b58a3b8fb6e990c15bd8711ce8807ed86956f39b62afb9a9daee80227` | *(identical)* | *(identical)* | kernel cmdline (incl. `agent.guest_components_rest_api=all`) |
| **RTMR2** | `77903a48ffcc66809d3f01a9853186ac08bc0081d06e4d05a0e0307450188e08d9f21b9c77e6747df0a90e65d7e3bff9` | *(identical)* | *(identical)* | initrd / OS |
| **RTMR3** | `0000…0000` (zero) | *(identical)* | *(identical)* | unused (zero) |
| **MROWNER / MROWNERCONFIG** | `0000…0000` (both zero) | *(identical)* | *(identical)* | unset (as expected) |

**Register behavior across records:**

- `MRTD`, `MRCONFIGID`, `RTMR1`, `RTMR2`, `RTMR3` are a function of the guest's
  **launch config** (OVMF `edk2-stable202608` + kernel `6.18.62-211-nvidia-gpu`
  + initrd + cmdline + `cc_init_data`), **not** the in-guest `sglang` container
  image. They are byte-identical across every record above — and stay identical
  across canary image rolls that change only application code.
- `RTMR0` (firmware / CCEL) is **node-specific**: it legitimately differs per
  host's firmware state. This is why the registry matches **any active record**
  rather than one pinned register set — and why a model deployed to a new node
  needs one new record for that `(model × node)` launch.

Capture procedure (per release): (a) MRCONFIGID from the InitData digest as in
§2.1; (b) `MRTD` + `RTMR0-3` from a booted guest's hardware quote via the
`/kubetee/evidence` route (or the gateway relay), cross-checked by CCEL replay;
(c) OVMF/shim sha256 per node from the host. Each measure-changing release goes
through the publication lifecycle in
[ATTESTATION-SPEC-v1.md](./ATTESTATION-SPEC-v1.md) §5.

### 3.1 Capture method and cross-checks

The registers are captured **from the live guest, with no pod disruption and no
`ExecProcess`**, via the in-guest evidence surface (CoCo's
`GET 127.0.0.1:8006/aa/evidence`, relayed by our `/kubetee/evidence` route,
enabled by the guest kernel parameter `agent.guest_components_rest_api=all`).
`GET https://<backend-host>:8443/kubetee/evidence?role=nim-terminator&nonce=<64-hex>`
over strict mTLS with the gateway east-west identity returns the
`kubetee.attestation.v1` envelope (epoch statement, Ed25519 `tee-pubkey`,
monotonic counter, `quote`, `cc_eventlog`); `MRTD`, `MRCONFIGID` and `RTMR0-3`
are read from the quote's TDINFO. When the direct listener is unavailable, the
same envelope is obtained through the gateway relay
(`X-KubeTEE-Backend-Evidence`).

**Cross-checks (passed on the Kimi and tx-b200-16 MiMo captures):**

- **Report-data binding** — the quote's 64-byte `report_data` equals
  `SHA-256(epoch statement) ‖ 32 zero bytes` on the cached epoch form,
  recomputed independently: **match**. On the **fresh composite** form
  (`?nonce=`), it is `SHA-256(nonce statement) ‖ <nonce bytes>` instead
  (verified live 2026-11-27, MiMo lu-b300-40).
- **CCEL replay** — the CC event log replayed with the TDX rule
  `RTMR[i] = SHA-384(RTMR[i] ‖ digest)` (records 1–4 → RTMR0–3) reproduces
  **all four** quote RTMRs exactly. MRTD is TDX-module-measured and is not in
  the event log.
- **MRCONFIGID live-confirm** — equals the recomputed InitData SHA-384 (§2.1).

The lu-b300-40 MiMo capture was cross-checked by register identity against its
tx-b200-16 twin (MRTD/MRCONFIGID/RTMR1-3 byte-exact) plus the MRCONFIGID
binding.

---

## 4. What is proven, and what is not

Proven / in the measured surface:

- The TLS key is built **in-guest** from attested CDH delivery — no Kubernetes
  Secret, no host mount, no unmeasured proxy in the trust path. TLS terminates
  inside the measured SGLang process (`:8443` Granian strict mTLS).
- Key possession is provable: the backend signs the caller's nonce with the TLS
  key.
- Exec into the guest is **measured-denied** (`ExecProcessRequest := false`),
  and stopping the pod destroys the VM and its decrypted memory.
- The transport code itself is inside the attested image, built from our public
  fork at an exact commit by a public, SHA-pinned workflow.

Not claimed:

- **Byte-identical reproducible digest** from a third party's own build.
  Transitive dependency resolution at build time (only one requirements file is
  fully hash-locked) and build-timestamp normalization (`SOURCE_DATE_EPOCH` /
  layer-tar normalization) block bit-reproducibility. Independent **rebuild +
  verify** is available (public source, digest-pinned bases, SHA-pinned
  workflow). We state bit-reproducibility only once a third-party rebuild
  actually matches.
- Fresh per-request **GPU** evidence on the backend hop is **deployed** since
  Phase 4b (2026-11-27): `X-KubeTEE-Nonce` mints a fresh CPU quote + 8× GPU
  SPDM evidence per caller nonce (rate-limited 1/min/key); the shared epoch
  quote remains the always-on freshness layer. The 8 raw GPU reports live on
  the backend's own east-west-mTLS evidence service; the relayed envelope
  carries a compact `gpu` summary + `evidence_digest` commitment.
- A bit-for-bit independent recomputation of `MRTD` from firmware inputs — it is
  captured from the hardware quote and cross-checked via the CCEL replay + the
  report-data binding, but no Intel TDX `tdx-measure`-equivalent recompute has
  run (that tool has no TDX MRTD mode).

---

## 5. The CoRIM twin and RVPS registration

Alongside the JSON records, KubeTEE publishes a **CoRIM** (Concise Reference
Integrity Manifest, IETF RATS) so a Verifier's **RVPS** (Trustee Reference Value
Provider Service) can appraise a TDX quote's launch registers against approved
reference state.

- **CoRIM (CBOR):** [https://kubetee.ai/.well-known/tee-reference-values.cbor](https://kubetee.ai/.well-known/tee-reference-values.cbor)
- **Detached signature:** `/.well-known/tee-reference-values.cbor.sig` (Ed25519,
  same `key_id` as the JSON records)
- **Digest:** `/.well-known/tee-reference-values.cbor.sha256`
- **Human twin + derived URIs:** `/.well-known/tee-reference-values.json`

**Scope: the Kimi-K3.1-Pro record only.** The published CoRIM carries the
`kimi-k3.1-pro` register set (its model class is `kubetee` /
`sglang-kimi-k3-1-pro`); the MiMo records exist in the JSON registry and are
not (yet) represented in RVPS reference state. An RVPS-based verifier appraises
Kimi evidence; MiMo evidence is appraised against the JSON registry.

The CoRIM is canonical CBOR (RFC 8949), CoRIM tag **501** wrapping one CoMID tag
**506** with a single compound reference-triple (all six registers must match
together — the RATS "compound reference value" model,
[trustee#350](https://github.com/confidential-containers/trustee/issues/350)).
Digests are SHA-384 (`alg = 7`). The build is byte-reproducible:
`kubetee-subnet/scripts/build-tee-reference-values-corim.py`.

### Reference-value URIs (RVPS)

Trustee's CoRIM extractor (`rvps/src/extractors/corim/`, v0.23.0) maps each
reference value to a URI `class.vendor / class.model / mkey / digests`. The model
class identifies the model (`vendor = kubetee`, `model = sglang-kimi-k3-1-pro`) —
it carries no deployment or node suffix. These land as:

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

The CoRIM's detached signature is a **publication integrity artifact** (same
offline key as the JSON records); verify it offline before ingesting if you want
supply-chain assurance. Trustee v0.23.0's RVPS CoRIM extractor does not verify
CoRIM signatures itself. The build, the byte-reproducible generator
(`kubetee-subnet/scripts/build-tee-reference-values-corim.py`), and the Trustee
RVPS ingestion mechanics (the standard gRPC `RegisterReferenceValue` call) are
documented in `docs/attestation-internal-technical-notes-2026-11-25.md` (root
repo).

---

## 6. Publication gate and signing key

A generated-but-unsigned record is a **draft**, not evidence — a successful
hardware appraisal does not establish the claim you are publishing. A record is
published only after its capture and cross-checks (§3.1) pass, both
machine-readable projections are published and registered, and the offline
Ed25519 signature (RFC 8785 JCS over the document with `signature` removed) is
in place and independently verified against the published verification key
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
