# Deploying in a TEE — Challenge and debugging

A confidential pod is a virtual machine with an encrypted, attested memory boundary, not a namespaced process on the host. Workloads run on **miner clusters**. Every node on the subnet-owner **staging cluster** is TEE CC capable. Staging is a **debug target** when a workload fails — not a required promotion workflow.

## Runtime classes (Kata 4.3.1)

Kata is **4.3.1** (`kata-deploy` Fleet bundle, vendored chart `4.3.1+kubetee.1`, `updateStrategy: RollingUpdate`, `maxUnavailable: 1`; Oakland since 2026-10-23, Luxembourg `lu-b300-40` verified 2026-11-03). KubeTEE uses **only** the runtime-rs classes — the Go shims (`kata-qemu-nvidia-gpu-tdx`, `kata-qemu-tdx`) are retired.

| `runtimeClassName` | Workload |
|--------------------|----------|
| `kata-qemu-nvidia-gpu-tdx-runtime-rs` | GPU TEE (NIM / SGLang / Armada GPU jobs) |
| `kata-qemu-tdx-runtime-rs` | CPU-only TDX (LiteLLM gateway, CPU jobs) |

Keep CoCo `kata-as-coco-runtime` **disabled** — it duplicates these RuntimeClasses.

TDX guests use **erofs + host-pull** (`IfNotPresent`). Nydus is installed only; do not select it for TDX shims. `#13482` (`WantedBy=rke2-server.service`) is in 4.1.0+ — do **not** restore `WantedBy=multi-user.target` or the retired `nydus-systemd-fix` drop-in.

**Still overlayed on 4.3.1:** shim `v4.3.1-fix11649-t15t16` (fix15 for [#11649](https://github.com/kata-containers/kata-containers/issues/11649) plus T15/T16 missing-task `stop_vm` for [#13665](https://github.com/kata-containers/kata-containers/issues/13665)/[#13746](https://github.com/kata-containers/kata-containers/issues/13746); host shim sha256 `96bcd8efa4cb…`). **OVMF overlay retired:** stock 4.3.1 supplies lazy-accept `edk2-stable202608` through [#13717](https://github.com/kata-containers/kata-containers/pull/13717), sha256 `2a2dc271…`; [#13535](https://github.com/kata-containers/kata-containers/issues/13535) closed completed 2026-10-27. Other retired overlays: `kata-deploy-gpu-extension-overlay` (2026-08-24, `#13471` stock), `nydus-systemd-fix` (2026-08-24, `#13482` stock), `kata-deploy-base-overlay` (2026-09-15, NVRC v0.1.7 stock).

Never `kubectl delete --force --grace-period=0` a Kata/CC pod. After a CC GPU node reboot, **cordon** until `kata-deploy` has finished extracting and the shim overlay hash is applied — a pod that starts on the stock shim can leave a leftover VM holding all GPUs.

## Kata guest debug, CC off, and CoCo Trustee

On the **staging cluster**, Kata Containers guest debug is **off**. [CoCo Trustee](https://github.com/confidential-containers/trustee) (KBS) attests those guests.

If a workload fails and needs debugging, target staging. For diagnostics:

- CC can be turned **off** on a staging node.
- Guest debug can be enabled **per pod**.

Trustee attests only when debug is off (CC on).

Miner clusters keep CC on with guest debug off. Trustee attests those guests.

## Supply-chain CI

Ordinary supply-chain CI (SAST, image CVE, IaC, provenance) is a **design reference** (manual/advisory practice).

### Secrets and images

Secrets live in CoCo Trustee / KBS and are released only to an attested guest (guest debug off). They are not Kubernetes Secrets and must not appear in Git, Helm, or image layers.

See the [README](../README.md#debugging-on-the-staging-cluster).
