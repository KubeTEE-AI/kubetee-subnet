# Attestation reference measures — SGLang serving backend (`nim-terminator`)

**Status: MEASURES CAPTURED & CROSS-VALIDATED (2026-11-25) — offline signature
is the only step before publication.** Prepared 2026-11-24, captured 2026-11-25.
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

Publication target (once the capture steps below complete and the record is
signed): `https://kubetee.ai/.well-known/tee-measurements.json` (this role's
record) + the human twin here. Do **not** publish a record containing a
`PENDING-CAPTURE` field — see [Publication gate](#5-publication-gate).

Companion specs (authoritative; this file is a role record, not a
re-statement of the protocol):

| Spec | Covers |
|---|---|
| [ATTESTATION-SPEC-v1.md](./ATTESTATION-SPEC-v1.md) | `kubetee.attestation.v1` evidence, report-data binding, publication lifecycle |
| [CLIENT-FACING-ATTESTATION.md](./CLIENT-FACING-ATTESTATION.md) | endpoint guide for verifiers |
| [EAST-WEST-ATTESTED-MTLS.md](./EAST-WEST-ATTESTED-MTLS.md) | the backend hop this record measures |
| [tee-measurements.schema.json](./tee-measurements.schema.json) | machine-readable schema for the published record |

---

## 1. Our SGLang fork

The serving engine is **our fork**, not upstream `sgl-project/sglang`
directly. Every backend image is built from this fork in GitHub Actions
(GitHub-hosted runners only — never on a cluster node) and consumed
digest-pinned.

| Field | Value |
|---|---|
| **Fork** | **[`https://github.com/KubeTEE-AI/sglang`](https://github.com/KubeTEE-AI/sglang)** (public fork of [`sgl-project/sglang`](https://github.com/sgl-project/sglang)) |
| Org / repo | `KubeTEE-AI/sglang` |
| Default branch | `kubetee/mimo-penfix` |
| Purpose of the fork | carry the **model-agnostic strict-mTLS transport layer** (and, separately, model-layer patches) without touching upstream |
| Build venue | GitHub Actions, GitHub-hosted runners only |
| Registry | `ghcr.io/kubetee-ai/sglang` |

### 1.1 The transport source we measure

The strict-mTLS transport is **SGLang source code**, not a sidecar or a proxy
layer — which is exactly why it is inside the attested evidence surface. Three
pieces:

1. `python/sglang/srt/arg_groups/serving_hook.py` — `self_check_client_cert(cfg)`
   supplies the engine's own loopback client identity and **fails closed** if
   `--ssl-client-verify` is set without both `--ssl-certfile` and `--ssl-keyfile`.
2. `python/sglang/srt/entrypoints/http_server.py` — every loopback probe passes
   `cert=ssl_client_cert` **with verification still strict**; plus
   `_inbound_client_verify` / `_inbound_cert_reqs` (the mTLS client-cert
   requirement is driven by `ssl_ca_certs` being configured).
3. `_run_granian_server` — Granian embedded server on `:8443` with
   `ssl_client_verify=True` and **no** `allow_unauthenticated()`; plus the
   isolated health-only Uvicorn listener on `:8000`
   (`health_check.UvicornHealthServer`) that answers `GET /health` and
   `GET /health_generate` and 404s everything else.

### 1.2 Fork branches that carry it

| Branch | Tip (2026-11-24) | What it is |
|---|---|---|
| [`kubetee/kimi-k31-granian-mtls-day0`](https://github.com/KubeTEE-AI/sglang/tree/kubetee/kimi-k31-granian-mtls-day0) | [`bf52f8223b88`](https://github.com/KubeTEE-AI/sglang/commit/bf52f8223b88b143fc8776d335f70c7724cbc30c) | the strict-mTLS Granian transport **validated live** on the Kimi-K3.1-Pro canary |
| `kubetee-overlay` | [`775b49ebe5d4`](https://github.com/KubeTEE-AI/sglang/commit/775b49ebe5d40c7e907bf9db251ac01c4053fb94) | the **model-agnostic** transport overlay with multi-base keying (`docker/kubetee-mtls-overlay/patches/by-sha-<sha>/`) — zero-fuzz per-base patches + pre/postimage drift tripwires |
| `kubetee/kimi-k31-granian-mtls-h2-canary`, `kubetee-kimi-k31-mtls-h2` | — | HTTP/2 transport canary lineage |
| `kubetee/mimo-penfix{,-r2,-r3,-r4-mtls-h2}`, `dsv4.1`, `kubetee-hw-policy-tests` | — | model-layer patch lines (kept **separate** from the transport layer) |

The transport commit that matters for the validated canary is
[`ab5a17e89e64`](https://github.com/KubeTEE-AI/sglang/commit/ab5a17e89e64) —
*"fix(serving): make warmup self-check present its mTLS client identity"* — the
change that stops the engine dying on its own loopback probe.

### 1.3 Base commits the fork patches onto

| Base | Upstream commit | Overlay patch key |
|---|---|---|
| `release/v0.5.23` | [`297e54fd105e`](https://github.com/sgl-project/sglang/commit/297e54fd105e974cdf401e5b4d20253a22c16f90) | `patches/by-sha-297e54fd/` |
| nightly `cu134-20261122-3117f58` | [`3117f5801752`](https://github.com/sgl-project/sglang/commit/3117f5801752bfd8ea9aee8d3ba3dff8562378fd) | `patches/by-sha-3117f580/` |

The Dockerfile keys strictly on `by-sha-$(printf '%.8s' "$SGLANG_SHA")` and
**fails closed** if that key directory is missing, then verifies `preimage.sha`
→ applies `0001-native-granian-mtls.patch` (0 fuzz) → verifies `postimage.sha`.
Drift in an upstream file is a hard build failure, not a silent partial patch.

---

## 2. The container used for the attestation

Identity of the artifact the attestation attests to. All image refs are
**`@sha256:` digest-pinned** — a tag alone is not identity.

### 2.1 Deployed strict-mTLS canary (the reference implementation)

| Field | Value |
|---|---|
| Image (quote-minting canary) | `ghcr.io/kubetee-ai/sglang:kimi-k31-granian-mtls-45497390909-b8f8015d@sha256:68cb8790dd1a959831f9bb10403c6f68142ddf9b5963722d3aa2b5b3f1cf59cb` |
| Fork source | `KubeTEE-AI/sglang`, `kubetee/kimi-k31-granian-mtls-day0` @ [`b8f8015d3291`](https://github.com/KubeTEE-AI/sglang/commit/b8f8015d329182a8d973aacc71e3d7ca371a5e22) |
| CI run | [`45497390909`](https://github.com/KubeTEE-AI/sglang/actions/runs/45497390909) |
| RuntimeClass | `kata-qemu-nvidia-gpu-tdx-runtime-rs` |
| Validated | 2026-11-25, `kimi-k3-1-pro39-sglang-b300-cc-0` (Luxembourg, `lu-b300-39`): `1/1` Ready, mTLS self-check warmup passed, evidence route `/kubetee/evidence` HTTP 200 over mTLS — **the guest that minted the reference measurements** |

The strict-mTLS transport itself was first validated live 2026-11-23 on the
earlier transport-only canary
`ghcr.io/kubetee-ai/sglang:kimi-k31-granian-mtls-45228495550-bf52f822@sha256:d808dd7bec…`
(`bf52f8223b88`, run [`45228495550`](https://github.com/KubeTEE-AI/sglang/actions/runs/45228495550)),
then rolled to the quote-minting build above which adds the in-guest evidence
route. Both share identical launch registers (application code is not measured).
A further build (`kimi-k31-granian-mtls-45514864315-f3683545@sha256:8cb7686916…`,
run [`45514864315`](https://github.com/KubeTEE-AI/sglang/actions/runs/45514864315))
adds the `/v1/kubetee/evidence` alias for the LiteLLM gateway relay path — same
registers again.

### 2.2 Transport-only overlay images (model-agnostic base images)

Container identity for the transport layer alone — **zero model-layer
patches**. Model images are built **on top of** these.

| Tag | Base | CI run | Digest |
|---|---|---|---|
| `mtls-297e54fd-20261124` | `v0.5.23` (`297e54fd`) | [`45354817361`](https://github.com/KubeTEE-AI/sglang/actions/runs/45354817361) | `sha256:c2be72ebf5b2d5c892add32ef4636858a303ff53c55a5df0b67bf88657c9a58b` |
| `mtls-3117f580-20261124` | nightly `3117f580` | [`45359236784`](https://github.com/KubeTEE-AI/sglang/actions/runs/45359236784) | `sha256:7978ad60c3f7b64c24993eed747eeea1d0e1be6396f4bb9357a1c19934419348` |

Full refs: `ghcr.io/kubetee-ai/sglang:mtls-297e54fd-20261124@sha256:c2be72eb…`
and `ghcr.io/kubetee-ai/sglang:mtls-3117f580-20261124@sha256:7978ad60…`.
(`:mtls-latest` is a moving convenience tag — **never** cite it as identity.)

Upstream base for the nightly build (digest-pinned):
`lmsysorg/sglang:nightly-cu134-20261122-3117f58@sha256:ffb8652016b1b895cd2dee12f6bffcb7a5fa65af71378e1018c9f702faa05063`.

### 2.3 Containers in the measured guest

The guest runs more than one container; every one is inside the TCB:

| Container | Image | Role |
|---|---|---|
| `fetch-secrets` (init) | `docker.io/curlimages/curl:8.11.1` | fetch the HF token + the east-west cert pair from CDH **after** attestation; fails closed (180 × 2s then exit) — no Kubernetes Secret fallback |
| `sglang` (main) | `ghcr.io/kubetee-ai/sglang:…@sha256:d808dd7bec…` | the measured engine terminating strict mTLS on `:8443` + health-only `:8000` |

Sandbox (pause) image: `docker.io/rancher/mirrored-pause:3.10.2`.

---

## 3. Measured launch inputs (TDX / NVIDIA-CC)

These are the inputs a verifier pins. The TDX launch registers below were
captured 2026-11-25 from the booted guest's hardware quote and cross-checked
(report-data binding + CCEL replay) — see §3.3 and §5.

### 3.1 InitData → MRCONFIGID / `host_data`

The guest's InitData is the gzip+base64 blob in the Kata annotation
`io.katacontainers.config.hypervisor.cc_init_data`. Per
[ATTESTATION-SPEC-v1.md](./ATTESTATION-SPEC-v1.md) §2, Kata 4.x computes
**SHA-384(uncompressed InitData TOML)**; the first 32 bytes are the SNP
`host_data`, and the full 48-byte digest is the TDX **MRCONFIGID**.

Independently recomputed 2026-11-24 from the deployed guest's annotation (gzip →
1499 bytes of InitData TOML):

| Field | Value |
|---|---|
| `initdata.sha384` = **MRCONFIGID** (48 B) | `0484a58e5927efd31bf871c74bcc9f1768f4335bb92340176989b3c5b320f9341d772b9e3e9c4fe4d824613cc19e6e0b` |
| `host_data` prefix32 | `0484a58e5927efd31bf871c74bcc9f1768f4335bb92340176989b3c5b320f934` |
| InitData role | `image-gen` |
| InitData files committed | `policy.rego`, `aa.toml`, `cdh.toml` (algorithm `sha384`, version `0.1.0`) |
| KBS endpoint (measured) | `https://kbs.kubetee.ai` (in both `aa.toml` and `cdh.toml`) |

> ✅ **CONFIRMED live 2026-11-25.** The quote's `MRCONFIGID` on the booted canary
> guest (`kimi-k3-1-pro39-sglang-b300-cc-0`) equals this recomputed InitData
> SHA-384 byte-for-byte — the derivation semantics are right.

### 3.2 Measured agent policy (what the host can and cannot do)

The `policy.rego` inside InitData is **measured** — changing it changes
MRCONFIGID, so enabling a denied capability is a measurement change a verifier
would reject. Current posture:

| Request | Value | Meaning |
|---|---|---|
| `ExecProcessRequest` | `false` | **exec denied** — the host cannot exec into the guest to exfiltrate the Trustee-released HF token from `/secrets` |
| `WriteStreamRequest` | `false` | no stdin write into processes |
| `ReadStreamRequest` | `true` | container logs readable (stdout only; request logging is off) |
| `CreateContainerRequest` / `StartContainerRequest` / `PullImageRequest` | `true` | lifecycle allowed (Kata `storage.source` is not the image ref) |
| all other requests | `true` | standard lifecycle/read surface |

### 3.3 Guest composition

| Input | Value |
|---|---|
| RuntimeClass | `kata-qemu-nvidia-gpu-tdx-runtime-rs` |
| Kata | **`4.4.0`** (upstream `f9cbda4d235b345340bf461e4aaba8c89e841d8d`, kata-deploy chart `4.4.0+kubetee.1`) |
| Shim | `/opt/kata/runtime-rs/bin/containerd-shim-kata-v2`, sha256 `82cd97b52ac89b6a73871d5ca68b61f840c5d84e030f28b72dc03f9baab9a73a` (overlay `v4.4.0-fix11649-t15t16-vsocktimeout`, branch `kubetee-fix11649-t15t16-440`, image `ghcr.io/kubetee-ai/kata-deploy-shim-overlay:v4.4.0-fix11649-t15t16-vsocktimeout@sha256:a8699a8705d95d2287685b59321e70a326cfdb19a54345524edadd6b3635e10c`) |
| Firmware (OVMF) | `/opt/kata/share/ovmf/OVMF.inteltdx.fd`, **`edk2-stable202608`** (in-tree lazy-accept) — fd sha256 **`2a2dc2710b0cfafc813310c7e98c67b72b919b8e1572d52a4c79466a2e499226`** (captured 2026-11-24 on `lu-b300-39` at the exact `-bios` path; matches the lazy-accept pin) |
| NVIDIA guest driver | `615.71.09` (`kata-containers/versions.yaml` `nvidia.driver`) |
| **TDX launch registers** | captured 2026-11-25 from the booted quote (TDINFO) — see the table below |
| `MRTD` cross-check | captured from the quote's TDINFO (MRTD is TDX-module-measured and cannot be reconstructed from launch inputs). `RTMR0-3` independently cross-checked by CCEL replay — both matched (§3.5). |

**TDX launch registers (captured 2026-11-25, `kimi-k3-1-pro39-sglang-b300-cc-0`):**

| Register | Value (48-byte SHA-384, hex) | Extended by |
|---|---|---|
| **MRTD** | `382d7bb61e152a5cc6eb22922a4dc9d33025211e24ec199fe38d6233c39cd86bf633e3c4f6e62393cf7ce6da91069ca0` | TDX module (initial TD: OVMF + kernel + initrd + cmdline) |
| **MRCONFIGID** | `0484a58e5927efd31bf871c74bcc9f1768f4335bb92340176989b3c5b320f9341d772b9e3e9c4fe4d824613cc19e6e0b` | from `cc_init_data` (= §3.1 InitData SHA-384) |
| **RTMR0** | `14f01287aefb3ac196451163aa8cf68cc1635083b24eb317256288815a5b48bbe7cdf2e2395ebf0474b3e528d2004014` | firmware / CCEL |
| **RTMR1** | `97fa8ac275f656b876de7c68709608bfe6ace60b58a3b8fb6e990c15bd8711ce8807ed86956f39b62afb9a9daee80227` | kernel cmdline (incl. `agent.guest_components_rest_api=all`) |
| **RTMR2** | `77903a48ffcc66809d3f01a9853186ac08bc0081d06e4d05a0e0307450188e08d9f21b9c77e6747df0a90e65d7e3bff9` | initrd / OS |
| **RTMR3** | `000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000` | unused (zero) |
| **MROWNER / MROWNERCONFIG** | `0000…0000` (both zero) | unset (as expected) |

These registers are a function of the guest's **launch config** (OVMF
`edk2-stable202608` + kernel `6.18.62-211-nvidia-gpu` + initrd + cmdline +
`cc_init_data`), **not** the in-guest `sglang` container image — the transport /
evidence-route code is application-level and does not change MRTD/RTMR. So these
values hold across canary image rolls that change only the app code (as verified:
build1 and build2 of the day0 canary yield identical registers).

> The shim overlay carries `fix15` (#11649 idempotent block hotplug + stale-fdset
> reclaim) and `T15/T16` (#13665/#13746 missing-task VM stop). `fix16` (#13641)
> and the orphan reaper (`fix9–12`) are **consciously dropped** — these are
> shim-runtime behavior and are covered by the measured shim hash above, not by
> the guest launch registers.

Capture procedure (per release): (a) MRCONFIGID from the InitData digest as in
§3.1; (b) `MRTD` + `RTMR0-3` from a booted guest's hardware quote via the
`/kubetee/evidence` route (§3.5), cross-checked by CCEL replay; (c)
OVMF/shim sha256 per node from the host. Each measure-changing release goes
through the publication lifecycle in
[ATTESTATION-SPEC-v1.md](./ATTESTATION-SPEC-v1.md) §3 (change-notice →
`upcoming` → roll → `active`, strictly increasing version).

### 3.4 Report-data binding (agreed contract for this role)

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
forms exist because a hardware quote is sealed at mint: the **epoch form** is
minted at most once per 5 minutes per replica and cached in the serving guest's
memory, with a per-request signature over
`SHA-256(quote) ‖ SHA-256(nonce) ‖ epoch_id` giving caller freshness; the
**nonce-bound form** binds the caller's nonce in `report_data` directly and is
rate-limited to 1 per 5 minutes per client key. Full surface:
[CLIENT-FACING-ATTESTATION.md](./CLIENT-FACING-ATTESTATION.md)
"Backend evidence for `nim-terminator`".

> **This role is TEE-generic.** These TDX registers describe the currently
> deployed NIM backends (Intel TDX nodes). An AMD SEV-SNP NIM deployment
> publishes a sibling record for the same role with `evidence.snp` populated and
> `quote`/`event_log`/`tdx` null; its binding is the SNP `report_data` convention
> of [ATTESTATION-SPEC-v1.md](./ATTESTATION-SPEC-v1.md) §4.

### 3.5 Capture method and cross-checks (2026-11-25)

The registers in §3.3 were captured **from the live guest, no pod disruption and
no `ExecProcess`** — exactly the path the earlier host-side attempt could not
reach. Two things had to be true first:

1. **The in-guest evidence surface enabled.** CoCo's `GET
   127.0.0.1:8006/aa/evidence` (what our `/kubetee/evidence` route relays) is
   **off by default** and gated behind the guest kernel parameter
   `agent.guest_components_rest_api=all`. The first canary booted without it and
   the route failed closed with `aa/evidence HTTP 404`; adding the flag to
   `io.katacontainers.config.hypervisor.kernel_params` (which is why RTMR1
   carries it) enabled the surface. The SNP gateway manifest already carried
   this flag — why its evidence worked from day one.
2. **Both route paths registered.** The gateway builds its fetch URL as
   `api_base.rstrip('/') + '/kubetee/evidence'` where `api_base` ends in `/v1`,
   so it requests `/v1/kubetee/evidence`; a direct operator fetch uses
   `/kubetee/evidence`. Both are served.

**Capture:** `GET
https://kimi-k3-1-pro39.eu-lu-luxembourg-133.inference.kubetee.ai:8443/kubetee/evidence?role=nim-terminator&nonce=<64-hex>`
over strict mTLS with the gateway east-west identity (`litellm.crt`) → `200`,
returning the `kubetee.attestation.v1` envelope (epoch statement, Ed25519
`tee-pubkey`, monotonic counter, `quote`, `cc_eventlog`). `MRTD`, `MRCONFIGID`
and `RTMR0-3` were read from the quote's TDINFO. Raw envelope + parsed registers
archived at `docs/captures/kimi-k3-1-pro39-tdx-20261125T012817Z.{evidence,regs}.json`.

**Cross-checks (both passed):**

- **Report-data binding** — the quote's 64-byte `report_data` equals
  `SHA-256(epoch statement) ‖ 32 zero bytes`, recomputed independently: **match**.
- **CCEL replay** — the 22-record CC event log replayed with the TDX rule
  `RTMR[i] = SHA-384(RTMR[i] ‖ digest)` (records 1–4 → RTMR0–3;
  `gm-miner/attestd/src/eventlog.rs`) reproduces **all four** quote RTMRs
  exactly. MRTD is TDX-module-measured and is not in the event log.
- **MRCONFIGID live-confirm** — equals the recomputed InitData SHA-384 (§3.1)
  and the QEMU `tdx-guest` `mrconfigid` object.

---

## 4. What is proven, and what is not

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
  run (that tool has no TDX MRTD mode — §5 item 1).

---

## 5. Publication gate

Do not publish this record until **all** are true. Status as of 2026-11-25:

1. ✅ **MRTD + RTMR0-3 captured** from the booted canary guest's hardware quote
   and cross-checked (report-data binding + CCEL replay reproduce all four
   RTMRs — §3.5). *Note on the earlier wording:* the cross-check is the
   **quote-internal report-data binding + CCEL replay**, **not** `tdx-measure`
   — that tool has no Intel TDX MRTD mode (see the record's
   `capture_blockers.recomputation_tool_gap`), and MRTD cannot be reconstructed
   from launch inputs. So MRTD is captured-and-cross-checked (eventlog + binding)
   but **not** independently recomputed bit-for-bit from firmware inputs; a
   future `tdx-measure`-equivalent (Intel `tdx-measure` over OVMF + kernel +
   initrd + cmdline) would close that last gap and is the only outstanding
   sub-item here. This is stated plainly rather than papered over — publishing a
   reconstruction as a capture is the failure mode this record exists to avoid.
2. ✅ **OVMF fd sha256 verified** on `lu-b300-39` (`2a2dc271…`, §3.3) and the
   measured shim hash matches the declared overlay (`82cd97b52ac8…`) — both feed
   MRTD.
3. ✅ **MRCONFIGID confirmed live** — equals the recomputed InitData SHA-384 and
   the QEMU `tdx-guest` object (§3.1, §3.5).
4. ⬜ **Version strictly increased** (the signer enforces monotonic version) and
   the change-notice has gone out **before** the deploy lands (partners pre-load
   `upcoming` rows from it).
5. ⬜ **Lifecycle status emitted** `upcoming` → roll → `active`, and the two
   publications published together:
   - `/.well-known/tee-measurements.json` (signed Ed25519 projection),
   - `/.well-known/tee-reference-values.cbor` (CoRIM) + push to RVPS.
6. ⬜ **Signed** with the offline Ed25519 key `key_id: kubetee-measurements-2026-11-22`
   (RFC 8785 JCS over the document with `signature` removed; the **private**
   half never enters the cluster or the repo; `key_id` + pubkey go to partners
   out-of-band and ride in the attestation keyset via `keyset_digest`). The
   exact bytes to sign are prepared at
   `/tmp/tee-measurements-jcs-bytes.json` (sha256
   `90d7f32dcc6262cb14ac1768429cd05917e8cfc12bfb40d5c52aefd4d8f4b7d2` at
   capture time — recompute from the final record before signing).

A generated-but-unsigned record is a **draft**, not evidence. Publishing a
record whose live measures were never observed would be exactly the failure
mode to avoid: a successful hardware appraisal does not establish the claim
you are publishing.
