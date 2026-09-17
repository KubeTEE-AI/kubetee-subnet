# GPU Node Requirements for KubeTEE

**Quick Reference**: This document lists ALL requirements for GPU nodes in KubeTEE clusters.

> **Early Access status (2026-07):** only **Intel TDX** (Intel 5th/6th Gen Xeon)
> ships in the Early Access release — the validator and runtime classes are
> tested and live on TDX. **AMD SEV-SNP** (AMD EPYC 4th/5th Gen) is a **Phase 1
> roadmap** item: the requirements and verification commands below are kept for
> reference so miners can pre-qualify hardware, but SEV-SNP is not yet
> supported by the KubeTEE runtime classes and the validator does not score it.
> **Phase 1** will also introduce **RTX 5000 Pro Server Edition** testing on the
> staging cluster. See the README roadmap for the multi-arch TEE timeline.

---

## Critical Requirements Checklist

GPU nodes MUST meet **ALL** of these requirements:

### ✅ 1. CPU Platform (MANDATORY)

**Supported CPUs**:

| Vendor | Generation | Codename | Series | Technology |
|--------|------------|----------|--------|------------|
| **Intel** | 6th Gen Xeon Scalable | Granite Rapids | Xeon 6xxx | TDX |
| **Intel** | 5th Gen Xeon Scalable | Emerald Rapids | Xeon 5xxx | TDX |
| **AMD** | 5th Gen EPYC | Turin | EPYC 9xx5 | **SEV-SNP** (Phase 1 — not in Early Access) |
| **AMD** | 4th Gen EPYC | Genoa | EPYC 9xx4 | **SEV-SNP** (Phase 1 — not in Early Access) |

**NOT Supported**:
- ❌ Intel 4th Gen Xeon (Sapphire Rapids) or older
- ❌ AMD 3rd Gen EPYC (Milan) or older - Even with SEV/SEV-ES
- ❌ AMD EPYC with older SEV or SEV-ES (only **SEV-SNP** is supported)
- ❌ Any CPU without TDX or SEV-SNP support

**Verification**:
```bash
# Intel TDX
dmesg | grep -i tdx
lscpu | grep -i "Model name"
# MUST show: Emerald Rapids or Granite Rapids

# AMD SEV-SNP (MUST be SNP, not older SEV/SEV-ES)
dmesg | grep -i "sev-snp\|snp"
cat /sys/module/kvm_amd/parameters/sev_snp  # Should output: Y or 1
lscpu | grep -i "Model name"
# MUST show: EPYC 9xx4 (Genoa) or 9xx5 (Turin)
```

**⚠️ AMD SEV Evolution**:
- **SEV-SNP** (Secure Nested Paging) - ✅ ONLY version supported
- SEV-ES (Encrypted State) - ❌ NOT Supported - Has vulnerabilities
- SEV (Basic) - ❌ NOT Supported - Deprecated and insecure

KubeTEE requires the latest SEV-SNP for maximum security.

---

### ✅ 2. GPU Model (MANDATORY)

**Supported GPUs**:
- ✅ **NVIDIA H100** (Hopper) - 80GB HBM3
- ✅ **NVIDIA H200** (Hopper) - 141GB HBM3e
- ✅ **NVIDIA B200** (Blackwell) - 192GB HBM3e
- ✅ **NVIDIA B300** (Blackwell Ultra) - 288GB HBM3e
- ✅ **NVIDIA RTX PRO 6000 Blackwell Server Edition** - 96GB GDDR7 ECC, CC mode on, PCIe Gen5, 600W configurable

**NOT Supported**:
- ❌ NVIDIA A100 (Ampere architecture)
- ❌ NVIDIA V100 (Volta architecture)
- ❌ NVIDIA RTX PRO 6000 Workstation Edition (no CC support — Server Edition only)
- ❌ Any other GPU model

**Verification**:
```bash
# Check GPU via PCI device ID (no drivers needed)
lspci -nn | grep -i nvidia

# For H100: Look for [10de:2330] or [10de:2331]
# For H200: Look for [10de:2331]
# For B200: Look for [10de:2901] (B200) or [10de:2909] (HGX B200)
# For B300: Look for [10de:3182] (B300 SXM6)
# For RTX PRO 6000: Look for [10de:2c2e] or [10de:2c33] (Blackwell Server)
```


---

### ✅ 3. GPU Count (MANDATORY)

**Requirement**: Exactly **8 GPUs** per node

**NOT Supported**:
- ❌ 1-7 GPUs (too few)
- ❌ 9+ GPUs (too many)

**Verification**:
```bash
# Count GPUs (MUST output: 8)
lspci | grep -i nvidia | grep -i "3D controller\|VGA" | wc -l
```

---

### ✅ 4. GPU Uniformity (MANDATORY)

**Requirement**: All 8 GPUs MUST be the same model

**Supported**:
- ✅ 8x NVIDIA H100 (Hopper) - 80GB HBM3
- ✅ 8x NVIDIA H200 (Hopper) - 141GB HBM3e
- ✅ 8x NVIDIA B200 (Blackwell) - 180GB HBM3e
- ✅ 8x NVIDIA B300 (Blackwell Ultra) - 288GB HBM3e
- ✅ 8x NVIDIA RTX PRO 6000 Blackwell Server Edition - 96GB GDDR7 ECC, CC mode on, PCIe Gen5, 600W configurable

**NOT Supported**:
- ❌ 4x H100 + 4x H200 (mixed models)
- ❌ Different memory configurations

**Verification**:
```bash
# All GPUs should show the same device ID
lspci -nn | grep -i nvidia | awk -F'[][]' '{print $2}' | sort -u
# Should output only ONE device ID
```

---

### ✅ 5. Latest Firmware (MANDATORY)

**Requirement**: Latest firmware for DGX H100/H200 and HGX B200/B300 systems

**Update firmware BEFORE node registration** using the official guide:
- **[NVIDIA DGX H100/H200 Firmware Update Guide](https://docs.nvidia.com/dgx/dgxh100-fw-update-guide/)**
- For HGX B200/B300 systems, follow your OEM/HGX firmware update procedure (BIOS/BMC, GPU firmware, PCIe switches and retimers)

**Confidential Computing firmware compatibility** (authoritative source: **[NVIDIA Trusted Computing Solutions — Guides](https://docs.nvidia.com/nvtrust/index.html#guides)**, including the Secure AI Compatibility Matrix):

The Compatibility Matrix is the source of truth for supported **GPU + VBIOS + CUDA driver + Confidential Computing mode** combinations (and RIM / VBIOS_RIM status). The node operator is responsible for the **GPU VBIOS** and **CC mode** (firmware/BIOS level); the **CUDA driver** is deployed by the GPU Operator after registration. Before registering a node, confirm your GPU's **VBIOS** and chosen **CC mode** (Protected PCIe / CC-Aux / APM) are listed as supported, and that the matrix's supported **CUDA driver** version matches what the GPU Operator will deploy. Key guidance from NVIDIA:
- **Protected PCIe (PPCIe) mode** — use **HGX Hopper FW 1.7.0**; avoid HGX Hopper FW 1.6.0, which has a known issue that can cause the GPU to fall off the bus during boot when PPCIe is enabled.
- **Secure AI with HGX Hopper FW 1.8.0 or later** — rollback to FW 1.7.1 or earlier is **not supported**; plan firmware forward-only.
- For **Blackwell (B200) / Blackwell Ultra (B300)**, check the matrix for the required VBIOS + CUDA driver + CC mode combination before labeling the node.

**Critical firmware components**:
- BMC (Baseboard Management Controller)
- BIOS/UEFI
- GPU firmware
- PCIe switches and retimers
- Network adapter firmware (ConnectX-7 or equivalent Ethernet NIC — RoCE-capable is a plus, InfiniBand-only HCAs are not required; see the Networking note under Cluster Architecture)
- PSUs, CPLDs, and other components

**For DGX Systems**:
```bash
# Check current firmware version
nvfwupd --query

# Follow NVIDIA's firmware update procedures
# https://docs.nvidia.com/dgx/dgxh100-fw-update-guide/
```

**For Custom Servers**:
- Consult your hardware vendor for firmware update procedures
- Ensure all components have latest firmware before registration

---

### ✅ 6. PPCIe Mode (MANDATORY) H100/H200 nodes

**Requirement**: PPCIe (Protected PCIe) mode enabled on all GPUs

**What is PPCIe?**
- Protected PCIe mode for confidential computing
- Enables secure GPU access in confidential VMs
- Required for TDX/SNP GPU passthrough

**Configuration**:
- Enabled in BIOS/UEFI settings
- Typically configured during firmware update process
- Consult NVIDIA DGX documentation for your specific model

---

### ✅ 7. VFIO/IOMMU (MANDATORY)

**Requirement**: VFIO/IOMMU enabled for GPU passthrough

**Verification**:
```bash
# Check IOMMU groups
ls /sys/kernel/iommu_groups/
# Should show multiple IOMMU groups

# Verify IOMMU is enabled
dmesg | grep -i iommu

# For Intel (VT-d)
dmesg | grep -i "Intel-IOMMU"

# For AMD (AMD-Vi)
dmesg | grep -i "AMD-Vi"
```

**BIOS Configuration**:
- Enable VT-d (Intel) or AMD-Vi (AMD)
- Enable IOMMU
- Enable SR-IOV (if available)

---

## Kata guest debug and CoCo Trustee

Miner GPU nodes and the subnet-owner **staging cluster** run **Kata 4.2.0** with **guest debug off**. CoCo Trustee attests those guests. Every staging node is TEE CC capable; CC can be turned off on a staging node for debug.

| `runtimeClassName` | Workload |
|--------------------|----------|
| `kata-qemu-nvidia-gpu-tdx-runtime-rs` | GPU TEE (NIM / SGLang) |
| `kata-qemu-tdx-runtime-rs` | CPU-only TDX (gateway-class) |

Guest debug can be enabled **per pod** for diagnostics. Trustee attests only when debug is off. Do not use the retired Go classes (`kata-qemu-nvidia-gpu-tdx`, `kata-qemu-tdx`). See [TEE deployment](./TEE-DEPLOYMENT-AND-CICD.md#runtime-classes-kata-420).

---

## GPU Software (Managed by GPU Operator)

**⚠️ CRITICAL - Clean Ubuntu Installation Required**

Nodes do **not** install or manage any NVIDIA GPU software. The **GPU Operator** (deployed via Fleet) installs and maintains the entire GPU software stack automatically after the node joins the cluster:

- NVIDIA drivers
- CUDA toolkit
- nvidia-container-toolkit
- GPU device plugins and Kubernetes GPU resources

Because the GPU Operator owns the GPU software stack, the node must start from a **clean Ubuntu 26.04 installation** with no pre-existing NVIDIA stack, to avoid version conflicts with what the GPU Operator deploys.

**OS Requirement**:
- ✅ Ubuntu 26.04 (clean installation, no pre-existing NVIDIA software)
- ✅ Kernel **7.0.0-38-generic** (Ubuntu 26.04 pin; `-31` or newer — `-31` is in updates/security, `-38` via `resolute-proposed` + apt pin. The pin is what matters: do not drift onto unpinned proposed kernels)
- ✅ etcd user/group created

---

## Storage Requirements

| Disk | Minimum Size | Purpose |
|------|--------------|---------|
| **OS Disk** | **1 TB** | System + `/var/lib/longhorn/` |
| **Data Disk** | **14 TB** | Raw block device with no filesystem |

**Both disks are REQUIRED for GPU nodes** due to:
- Large AI/ML models
- Training datasets
- Checkpoints and artifacts
- Database storage

---


## Complete Verification Checklist

### Before Registration (On Node)

```bash
# 1. Verify CPU generation
lscpu | grep -i "Model name"

# 2. Verify TDX/SNP enabled
dmesg | grep -i tdx   # Intel
dmesg | grep -i sev   # AMD

# 3. Verify exactly 8 GPUs
lspci | grep -i nvidia | grep -i "3D controller\|VGA" | wc -l
# MUST output: 8

# 4. Verify GPU model via device ID
lspci -nn | grep -i nvidia
# All should show one of:
#   [10de:2330]/[10de:2331] (H100/H200), [10de:2901]/[10de:2909] (B200), [10de:3182] (B300)

# 5. Verify firmware (DGX systems)
nvfwupd --query

# 6. Verify IOMMU enabled
dmesg | grep -i iommu

# 7. Verify storage
df -h /
df -h /data
# OS: 800GB+, Data: 3TB+

# 8. Verify OS and kernel
lsb_release -ds  # Should show: Ubuntu 26.04 LTS
uname -r         # Should show: 7.0.0-38-generic (pin) or 7.0.0-31-generic+ (updates)

# 9. Verify a clean baseline (no pre-existing NVIDIA stack)
which nvidia-smi  # Should return: not found (GPU Operator installs it later)
which nvcc        # Should return: not found
```

---

## Quick Decision Tree

```
Is your node a GPU node?
├─ NO → Skip GPU requirements, proceed with standard registration
└─ YES → Check all requirements:
    ├─ CPU: Intel 5th/6th Gen OR AMD EPYC 4th/5th Gen? 
    │   ├─ NO → Node NOT supported ❌
    │   └─ YES → Continue
    ├─ TDX or SEV-SNP enabled?
    │   ├─ NO → Enable in BIOS, then continue
    │   └─ YES → Continue
    ├─ Exactly 8 GPUs?
    │   ├─ NO → Node NOT supported ❌
    │   └─ YES → Continue
    ├─ All GPUs are H100, H200, B200, or B300?
    │   ├─ NO → Node NOT supported ❌
    │   └─ YES → Continue
    ├─ All GPUs same model?
    │   ├─ NO → Node NOT supported ❌
    │   └─ YES → Continue
    ├─ Latest firmware installed?
    │   ├─ NO → Update firmware first
    │   └─ YES → Continue
    ├─ PPCIe mode enabled?
    │   ├─ NO → Enable in BIOS/firmware
    │   └─ YES → Continue
    ├─ VFIO/IOMMU enabled?
    │   ├─ NO → Enable in BIOS, update kernel params
    │   └─ YES → Continue
    ├─ Clean Ubuntu 26.04, kernel 7.0.0-3x pin (no pre-existing NVIDIA stack)?
    │   ├─ NO → Reinstall Ubuntu 26.04
    │   └─ YES → Continue
    └─ ✅ Node meets ALL requirements → Proceed with registration
```

---

## Common Mistakes to Avoid

### ❌ Wrong GPU Count

```bash
# BAD: Only 4 GPUs
lspci | grep nvidia | wc -l
# Output: 4  ← NOT SUPPORTED
```

### ❌ Mixed GPU Models

```bash
# BAD: 4x H100 + 4x H200
lspci -nn | grep nvidia
# Shows: [10de:2330] and [10de:2331]  ← NOT SUPPORTED
```

### ❌ Pre-existing NVIDIA Software

The GPU Operator owns the entire GPU software stack. A pre-existing NVIDIA install conflicts with what it deploys.

```bash
# BAD: a previous NVIDIA install is present
which nvidia-smi
# /usr/bin/nvidia-smi  ← reinstall Ubuntu 26.04 clean
```

### ❌ Old CPU Generation

```bash
# BAD: Intel 4th Gen (Sapphire Rapids)
lscpu | grep "Model name"
# Intel Xeon ... Sapphire Rapids  ← NOT SUPPORTED
```

### ❌ Outdated Firmware

```bash
# BAD: Old firmware version
nvfwupd --query
# Shows: Version 24.09.1  ← UPDATE REQUIRED
# Current: Version 25.10.1+
```

---

## Support Matrix

| Requirement | Valid Options | NOT Supported |
|-------------|---------------|---------------|
| **CPU** | Intel 5th/6th Gen, AMD 4th/5th Gen EPYC | Intel ≤4th Gen, AMD ≤3rd Gen |
| **Confidential Computing** | TDX (Intel), SEV-SNP ONLY (AMD) | No TDX/SNP, older SEV/SEV-ES |
| **GPU Model** | H100, H200, B200, B300 | A100, V100, others |
| **GPU Count** | Exactly 8 | 1-7, 9+ |
| **GPU Uniformity** | All same model | Mixed models |
| **Firmware** | Latest (25.10.1+) | Outdated versions |
| **GPU Mode** | PPCIe enabled | Standard PCIe |
| **IOMMU** | Enabled | Disabled |
| **OS** | Ubuntu 26.04 (clean, kernel 7.0.0-38-generic pin; `-31`+ acceptable) | Pre-existing NVIDIA software |
| **OS Disk** | 800 GB+ | <800 GB |
| **Data Disk** | 3 TB+ | <3 TB |

---

## Cluster Architecture & High Availability

> KubeTEE is a **decentralized multi-cluster architecture**. Each miner operates one RKE2 cluster (one hotkey per cluster), and the full tech stack — GPU Operator, Kata/CoCo runtime classes, NeMo Microservices, Armada Executor, Longhorn storage, monitoring — is deployed onto it via Rancher Fleet GitOps. Miners must provide the minimum cluster shape below to allow high availability, deploy the tech stack, and have enough nodes to run SOTA AI services and enhanced services for enterprises. These minimum requirements are written and enforced in Phase 0.

### Minimum cluster topology

| Requirement | Minimum | Why |
|---|---|---|
| **Total nodes** | **7 minimum** (5 control-plane+etcd+worker combined, 2+ dedicated GPU workers per GPU type) | 5 nodes run the control plane, etcd, and the tech stack (GPU Operator, Kata/CoCo, Longhorn, NeMo Microservices, Armada Executor, monitoring) while also serving inference; 3+ dedicated 8-GPU workers **per GPU type** run AI job workloads. Fewer nodes cannot simultaneously host the tech stack and serve inference with HA. |
| **Control-plane + etcd nodes** | **5** (combined control-plane + etcd + worker role) | 5 nodes give etcd quorum with 2-node failure tolerance. These nodes run the control plane AND double as workers — they host the tech stack and can serve inference workloads, so they are not "wasted" on control-plane duty alone. |
| **Dedicated GPU worker nodes** | **3+ per GPU type** (8x H100/H200/B200/B300 per node) | **3 nodes of each GPU type** is the minimum for HA — if a cluster serves H200 and B200 workloads, it needs 3 H200 nodes + 3 B200 nodes (4 dedicated GPU workers). A single-GPU-type cluster needs 3; a mixed-GPU cluster needs 3 per type. Each 8-GPU worker can run one large confidential workload or multiple smaller ones. |
| **Co-location** | All nodes in a **single data center** | Multi-GPU NVLink/NVSwitch passthrough requires low latency; cross-DC NVLink is unsupported. One cluster = one DC. |
| **Network** | All nodes on the same L2 / low-latency fabric | VFIO passthrough, Kata sandbox creation, and in-guest NVLink all depend on local fabric; high-latency cross-DC links cause sandbox timeouts and degraded GPU topology |

### Why 7 nodes minimum

- **5 control-plane + etcd + worker nodes**: RKE2 etcd needs an odd number for quorum. 5 nodes give 2-node failure tolerance (survive losing 2 of 5 and still have quorum). These 5 nodes are **not idle control-plane nodes** — they run the tech stack (GPU Operator, Kata/CoCo runtime classes, Longhorn storage, NeMo Microservices, monitoring, Armada Executor) and can serve inference workloads, so their GPU capacity counts toward the fleet. A 3-node control plane tolerates only 1 failure; 5 is the minimum where a cluster can lose 2 nodes and still serve.
- **3 dedicated GPU workers per GPU type**: the tech stack on the 5 control-plane+worker nodes consumes CPU/memory and some GPU capacity for NeMo services and inference. 3 dedicated 8-GPU workers **per GPU type** ensure enough bare-metal GPU capacity to run AI services and Armada jobs (inference, fine-tuning, batch) without competing with the tech stack for resources, and keep HA for that GPU type (losing 1 of 2 leaves 1 dedicated worker serving that GPU type). **A mixed-GPU cluster needs 3 per type**: e.g. 3 H200 + 3 B200 = 6 dedicated GPU workers + 5 control-plane.
- **7 total (single GPU type)**: 5 (control-plane+etcd+worker, running tech stack + inference) + 2 (dedicated GPU workers of one type, running AI jobs) = 7 nodes minimum for a single-GPU-type cluster. A mixed-GPU cluster adds 2 per additional GPU type.

### Scaling beyond the minimum

| Scale | Total nodes | Topology | Concurrent 8-GPU workloads | Networking |
|---|---|---|---|
| **Minimum** | 7 | 5 control-plane+etcd+worker (tech stack + inference) + 2 dedicated GPU workers | 2+ (dedicated) + inference on the 5 combined | Ethernet OK |
| **Small** | 12 | 5 control-plane+etcd+worker + 7 dedicated GPU workers | 7+ | Ethernet OK |
| **Production** | 16+ | 5 control-plane+etcd+worker + 11+ dedicated GPU workers | 11+ | High-bandwidth Ethernet (100/400GbE, jumbo-frame capable) |
| **Large** | 24+ | 5 control-plane+etcd+worker + 19+ dedicated GPU workers | 19+ | High-bandwidth Ethernet (100/400GbE, jumbo-frame capable) |
| **HGX Cluster** | 32+ | 5 control-plane+etcd+worker + 27+ dedicated GPU workers (full HGX racks) | 27+ | High-bandwidth Ethernet (100/400GbE, jumbo-frame capable) |

> **InfiniBand is not a hard requirement.** High-bandwidth Ethernet (100/400GbE) is the baseline at every scale. If a miner provides an RDMA-capable fabric anyway, it **must be RoCE (RDMA over Converged Ethernet), not InfiniBand**: kernel-bypass RDMA into Confidential Computing guest memory does not work until **TDX Connect is GA on 6th-Generation Intel Xeon (Granite Rapids)**. Our 2026-09-15/16 HCA-passthrough PoC on 8×H200 TDX + PPCIE (kata 4.1.0 and 4.2.0) proved the full device pipeline works (vfio-pci bind → device plugin → CDI → 4×CX7 ACTIVE at 400 Gb/s NDR → NCCL NET/IB transport with QPs + ECE) but the first `ibv_reg_mr_iova2` fails with `EFAULT` — the NIC cannot DMA into encrypted guest memory. Until the TDX Connect hardware path is GA, confidential workloads run over ordinary TCP (NCCL NET/Socket) on the Ethernet fabric; enable jumbo frames for throughput (measured on our 8×H200 fleet: MTU 9000 gives 5.8× non-CC and 3.1× CC pod-to-pod over the Calico overlay).

> **One cluster per hotkey.** A miner may operate multiple clusters, but each cluster must have its own Bittensor hotkey (one cluster per hotkey, enforced by the validator's `kubetee.ai/hotkey` label binding). Multiple clusters = multiple hotkeys = multiple DCs.

See [Node Registration](NODE-REGISTRATION.md) for the RKE2 node registration command and the full enrolled-cluster binding contract, and the README [For Miners (Infrastructure)](../README.md#for-miners-infrastructure) section for the onboarding flow.

---

## Resources

### Official Documentation

- **[NVIDIA DGX H100/H200 Firmware Update Guide](https://docs.nvidia.com/dgx/dgxh100-fw-update-guide/)** - MANDATORY reading for firmware updates
- **[NVIDIA Trusted Computing Solutions — Guides](https://docs.nvidia.com/nvtrust/index.html#guides)** — Secure AI Compatibility Matrix and related CC guides (GPU + VBIOS + CUDA driver + Confidential Computing mode; source of truth for CC firmware compatibility)
- **[NODE-REGISTRATION.md](NODE-REGISTRATION.md)** - Complete registration guide

### KubeTEE Documentation

- **Node Registration**: [NODE-REGISTRATION.md](NODE-REGISTRATION.md)
- **Cluster Creation**: see the Rancher documentation for cluster provisioning; KubeTEE miners register existing RKE2 clusters via the node registration command

---

## Summary

**To register a GPU node to KubeTEE**:

1. ✅ **Hardware**: 8x H100, H200, B200, or B300 GPUs on Intel 5th/6th Gen Xeon OR AMD EPYC 4th/5th Gen
2. ✅ **Firmware**: Latest version from [NVIDIA DGX Firmware Guide](https://docs.nvidia.com/dgx/dgxh100-fw-update-guide/)
3. ✅ **BIOS**: TDX/SEV-SNP, PPCIe mode, VFIO/IOMMU enabled
4. ✅ **OS**: Ubuntu 26.04 clean, kernel 7.0.0-3x pin (GPU Operator manages all GPU software)
5. ✅ **Storage**: 800GB OS + 3TB data disks
6. ✅ **Register**: Run registration command with network addresses
7. ✅ **Label**: `kubectl label node <name> nvidia.com/gpu.workload.config=vm-passthrough`
8. ✅ **Wait**: GPU Operator installs drivers automatically (5-15 minutes)

**If ANY requirement is not met, the node will NOT be supported for KubeTEE GPU workloads.**

---

**Last Updated**: 2026-07-18  
**NVIDIA Firmware Version**: 25.10.1+  
**Status**: ✅ Production Ready

