# Deploying in a TEE — Challenge and debugging

A confidential pod is a virtual machine with an encrypted, attested memory boundary, not a namespaced process on the host. Workloads run on **miner clusters**. Every node on the subnet-owner **staging cluster** is TEE CC capable. Staging is a **debug target** when a workload fails — not a required promotion workflow.

## Runtime classes (Kata 4.1.0)

Production Kata is **4.1.0** (`kata-deploy` Fleet bundle, chart `updateStrategy: RollingUpdate`, `maxUnavailable: 1`). KubeTEE uses **only** the runtime-rs classes — the Go shims (`kata-qemu-nvidia-gpu-tdx`, `kata-qemu-tdx`) are retired.

| `runtimeClassName` | Workload |
|--------------------|----------|
| `kata-qemu-nvidia-gpu-tdx-runtime-rs` | GPU TEE (NIM / SGLang / Armada GPU jobs) |
| `kata-qemu-tdx-runtime-rs` | CPU-only TDX (LiteLLM gateway, CPU jobs) |

Keep CoCo `kata-as-coco-runtime` **disabled** — it duplicates these RuntimeClasses.

TDX guests use **erofs + host-pull** (`IfNotPresent`). Nydus is installed only; do not select it for TDX shims. `#13482` (`WantedBy=rke2-server.service`) is in 4.1.0 — do **not** restore `WantedBy=multi-user.target` or the retired `nydus-systemd-fix` drop-in.

**Still overlayed on 4.1.0** (not in the tag): shim `v4.1.0-nvswitch-fix19` (QEMU teardown / T15 / `#13635` blockdev-add / inotify), base EROFS (NVRC 600s), OVMF 202605 lazy-accept, CSI `-kubetee3`. **Retired 2026-08-24:** `kata-deploy-gpu-extension-overlay` (`#13471` is stock) and `nydus-systemd-fix`.

Never `kubectl delete --force --grace-period=0` a Kata/CC pod. After a CC GPU node reboot, **cordon** until `kata-deploy` has finished extracting and the shim overlay hash is applied — a pod that starts on the stock shim can leave a leftover VM holding all GPUs.

## Kata guest debug, CC off, and CoCo Trustee

On the **staging cluster**, Kata Containers guest debug is **off**. [CoCo Trustee](https://github.com/confidential-containers/trustee) (KBS) attests those guests.

If a workload fails and needs debugging, target staging. For diagnostics:

- CC can be turned **off** on a staging node.
- Guest debug can be enabled **per pod**.

Trustee attests only when debug is off (CC on).

Miner clusters keep CC on with guest debug off. Trustee attests those guests.

## Supply-chain CI

Ordinary supply-chain CI (SAST, image CVE, IaC, provenance) is designed, not yet automated. It is not a staging lane.

### Secrets and images

Secrets live in CoCo Trustee / KBS and are released only to an attested guest (guest debug off). They are not Kubernetes Secrets and must not appear in Git, Helm, or image layers.

See the [README](../README.md#debugging-on-the-staging-cluster).
