# Deploying in a TEE — Challenge and debugging

A confidential pod is a virtual machine with an encrypted, attested memory boundary, not a namespaced process on the host. From Phase 1, workloads run on **external miner clusters** with CC on and guest debug off. **Only external miners are onboarded.** The subnet-owner staging miner UID 56 (`na-us-oakland-56`), previously the CC-off debug target, is decommissioned as a miner as Phase 1 begins. Subnet-owner control-plane infrastructure is not a replacement miner. There is no staging promotion workflow.

## Runtime classes (Kata 4.4.0)

Kata is **4.4.0** (upstream `f9cbda4d235b345340bf461e4aaba8c89e841d8d`; `kata-deploy` Fleet bundle, vendored chart `4.4.0+kubetee.1`, `updateStrategy: RollingUpdate`, `maxUnavailable: 1`; deployed on external-miner clusters). KubeTEE uses **only** the runtime-rs classes — the Go shims (`kata-qemu-nvidia-gpu-tdx`, `kata-qemu-tdx`) are retired.

| `runtimeClassName` | Workload |
|--------------------|----------|
| `kata-qemu-nvidia-gpu-tdx-runtime-rs` | GPU TEE (NIM / SGLang / Armada GPU jobs) |
| `kata-qemu-tdx-runtime-rs` | CPU-only TDX (LiteLLM gateway, CPU jobs) |

Keep CoCo `kata-as-coco-runtime` **disabled** — it duplicates these RuntimeClasses.

TDX guests use **erofs + host-pull** (`IfNotPresent`). Nydus is installed only; do not select it for TDX shims. `#13482` (`WantedBy=rke2-server.service`) is in 4.1.0+ — do **not** restore `WantedBy=multi-user.target` or the retired `nydus-systemd-fix` drop-in.

**Still overlayed on 4.4.0:** shim `v4.4.0-fix11649-t15t16-vsocktimeout` (branch `kubetee-fix11649-t15t16-440`, [`KubeTEE-AI/kata-containers`](https://github.com/KubeTEE-AI/kata-containers) — fix15 for [#11649](https://github.com/kata-containers/kata-containers/issues/11649) plus T15/T16 missing-task `stop_vm` for [#13665](https://github.com/kata-containers/kata-containers/issues/13665)/[#13746](https://github.com/kata-containers/kata-containers/issues/13746); host shim sha256 `82cd97b52ac8…`, overlay image `ghcr.io/kubetee-ai/kata-deploy-shim-overlay:v4.4.0-fix11649-t15t16-vsocktimeout@sha256:a8699a87…`). **OVMF overlay retired:** stock Kata supplies lazy-accept `edk2-stable202608` through [#13717](https://github.com/kata-containers/kata-containers/pull/13717); [#13535](https://github.com/kata-containers/kata-containers/issues/13535) closed completed 2026-10-27. Other retired overlays: `kata-deploy-gpu-extension-overlay` (2026-08-24, `#13471` stock), `nydus-systemd-fix` (2026-08-24, `#13482` stock), `kata-deploy-base-overlay` (2026-09-15, NVRC v0.1.7 stock).

Never `kubectl delete --force --grace-period=0` a Kata/CC pod. After a CC GPU node reboot, **cordon** until `kata-deploy` has finished extracting and the shim overlay hash is applied — a pod that starts on the stock shim can leave a leftover VM holding all GPUs.

## Phase 0 staging history and the external-miner boundary

During Phase 0, the subnet-owner staging miner UID 56 (`na-us-oakland-56`) ran TEE-CC-capable nodes with guest debug off by default. For diagnostics, an operator could disable CC on a staging node or enable guest debug per pod. [CoCo Trustee](https://github.com/confidential-containers/trustee) (KBS) attested only the non-debug guests.

That staging-miner role and its CC-off diagnostic exception are **decommissioned at Phase 1**. No replacement owner-operated staging miner is onboarded. External miner clusters keep CC on and guest debug off; Trustee attests those guests. External miners must not reproduce the historical staging CC-off configuration for production capacity.

## Supply-chain CI

Ordinary supply-chain CI (SAST, image CVE, IaC, provenance) is a **design reference** (manual/advisory practice).

### Secrets and images

Secrets live in CoCo Trustee / KBS and are released only to an attested guest (guest debug off). They are not Kubernetes Secrets and must not appear in Git, Helm, or image layers.

See the [README external-miner transition](../README.md#phase-1-transition) and [Miner Onboarding](./MINER-ONBOARDING.md).
