# GPU Node Requirements for KubeTEE

**Quick Reference**: This document lists ALL requirements for GPU nodes in KubeTEE clusters.

---

## Critical Requirements Checklist

GPU nodes MUST meet **ALL** of these requirements:

### ✅ 1. CPU Platform (MANDATORY)

**Supported CPUs**:

| Vendor | Generation | Codename | Series | Technology |
|--------|------------|----------|--------|------------|
| **Intel** | 6th Gen Xeon Scalable | Granite Rapids | Xeon 6xxx | TDX |
| **Intel** | 5th Gen Xeon Scalable | Emerald Rapids | Xeon 5xxx | TDX |
| **AMD** | 5th Gen EPYC | Turin | EPYC 9xx5 | **SEV-SNP** |
| **AMD** | 4th Gen EPYC | Genoa | EPYC 9xx4 | **SEV-SNP** |

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

**NOT Supported**:
- ❌ NVIDIA A100 (Ampere architecture)
- ❌ NVIDIA V100 (Volta architecture)
- ❌ Any other GPU model

**Verification**:
```bash
# Check GPU via PCI device ID (no drivers needed)
lspci -nn | grep -i nvidia

# For H100: Look for [10de:2330] or [10de:2331]
# For H200: Look for [10de:2331]
# For B200: Look for [10de:2901] (B200) or [10de:2909] (HGX B200)
# For B300: Look for [10de:3182] (B300 SXM6)
```

> **B300 note**: the GPU Operator validator must include device ID `3182` (added by [gpu-operator PR #2441](https://github.com/NVIDIA/gpu-operator/issues/2231)); older validator builds fail to recognize B300 with `failed to find device with id '3182'`. Ensure a GPU Operator release that supports `3182` is deployed before labeling B300 nodes.

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
- ✅ 8x H100 80GB
- ✅ 8x H200 141GB
- ✅ 8x B200 192GB
- ✅ 8x B300 288GB

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

**Confidential Computing firmware compatibility** (authoritative source: **[NVIDIA Secure AI Compatibility Matrix](https://www.nvidia.com/en-us/data-center/solutions/confidential-computing/secure-ai-compatibility-matrix/)**):

The Compatibility Matrix is the source of truth for supported **GPU + VBIOS + CUDA driver + Confidential Computing mode** combinations (and RIM / VBIOS_RIM status). The node operator is responsible for the **GPU VBIOS** and **CC mode** (firmware/BIOS level); the **CUDA driver** is deployed by the GPU Operator after registration. Before registering a node, confirm your GPU's **VBIOS** and chosen **CC mode** (Protected PCIe / CC-Aux / APM) are listed as supported, and that the matrix's supported **CUDA driver** version matches what the GPU Operator will deploy. Key guidance from NVIDIA:
- **Protected PCIe (PPCIe) mode** — use **HGX Hopper FW 1.7.0**; avoid HGX Hopper FW 1.6.0, which has a known issue that can cause the GPU to fall off the bus during boot when PPCIe is enabled.
- **Secure AI with HGX Hopper FW 1.8.0 or later** — rollback to FW 1.7.1 or earlier is **not supported**; plan firmware forward-only.
- For **Blackwell (B200) / Blackwell Ultra (B300)**, check the matrix for the required VBIOS + CUDA driver + CC mode combination before labeling the node.

**Critical firmware components**:
- BMC (Baseboard Management Controller)
- BIOS/UEFI
- GPU firmware
- PCIe switches and retimers
- Network adapter firmware (ConnectX-7, Intel NIC)
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

### ✅ 6. PPCIe Mode (MANDATORY)

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
- ✅ Kernel 7.0.0-27-generic or newer (configured per MINER_INFRA.md)
- ✅ etcd user/group created

---

## Storage Requirements

| Disk | Minimum Size | Purpose |
|------|--------------|---------|
| **OS Disk** | **800 GB** | System + `/var/lib/longhorn/` |
| **Data Disk** | **3 TB** | `/data` - Longhorn storage |

**Both disks are REQUIRED for GPU nodes** due to:
- Large AI/ML models
- Training datasets
- Checkpoints and artifacts
- Database storage

---

## Node Configuration After Registration

### Step 1: Label Node for GPU Passthrough

```bash
kubectl label node <your-node-name> nvidia.com/gpu.workload.config=vm-passthrough
```

**This is the ONLY step required by miners** - everything else is automatic.

### Step 2: GPU Operator Installs Drivers (Automatic)

After labeling, the GPU Operator will automatically:
1. Detect the `vm-passthrough` label
2. Install NVIDIA drivers
3. Install CUDA toolkit
4. Configure GPU device plugins
5. Enable GPU resources in Kubernetes

**Wait time**: 5-15 minutes for driver installation

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
uname -r         # Should show: 7.0.0-27-generic or newer

# 9. Verify a clean baseline (no pre-existing NVIDIA stack)
which nvidia-smi  # Should return: not found (GPU Operator installs it later)
which nvcc        # Should return: not found
```

### After Registration (From Management Cluster)

```bash
# 1. Verify node joined
kubectl get nodes

# 2. Check node IPs
kubectl get node <node-name> -o wide

# 3. Label node for GPU passthrough
kubectl label node <node-name> nvidia.com/gpu.workload.config=vm-passthrough

# 4. Verify GPU Operator is running
kubectl get pods -n gpu-operator-system

# 5. Wait for drivers to install (5-15 minutes)

# 6. Verify GPU resources
kubectl describe node <node-name> | grep nvidia.com/gpu
# Should show: nvidia.com/gpu: 8
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
    ├─ Clean Ubuntu 26.04, kernel 7.0.0-27-generic+ (no pre-existing NVIDIA stack)?
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
| **OS** | Ubuntu 26.04 (clean, kernel 7.0.0-27-generic+) | Pre-existing NVIDIA software |
| **OS Disk** | 800 GB+ | <800 GB |
| **Data Disk** | 3 TB+ | <3 TB |

---

## Resources

### Official Documentation

- **[NVIDIA DGX H100/H200 Firmware Update Guide](https://docs.nvidia.com/dgx/dgxh100-fw-update-guide/)** - MANDATORY reading for firmware updates
- **[NVIDIA Secure AI Compatibility Matrix](https://www.nvidia.com/en-us/data-center/solutions/confidential-computing/secure-ai-compatibility-matrix/)** - Supported GPU + VBIOS + CUDA driver + Confidential Computing mode combinations (source of truth for CC firmware compatibility)
- **[NODE-REGISTRATION.md](NODE-REGISTRATION.md)** - Complete registration guide
- **[MINER_INFRA.md](MINER_INFRA.md)** - Initial infrastructure setup

### KubeTEE Documentation

- **Node Registration**: [NODE-REGISTRATION.md](NODE-REGISTRATION.md)
- **Infrastructure Setup**: [MINER_INFRA.md](MINER_INFRA.md)
- **Cluster Creation**: `../../CREATE-CLUSTER-GUIDE.md`

---

## Summary

**To register a GPU node to KubeTEE**:

1. ✅ **Hardware**: 8x H100, H200, B200, or B300 GPUs on Intel 5th/6th Gen Xeon OR AMD EPYC 4th/5th Gen
2. ✅ **Firmware**: Latest version from [NVIDIA DGX Firmware Guide](https://docs.nvidia.com/dgx/dgxh100-fw-update-guide/)
3. ✅ **BIOS**: TDX/SEV-SNP, PPCIe mode, VFIO/IOMMU enabled
4. ✅ **OS**: Ubuntu 26.04 clean, kernel 7.0.0-27-generic+ (GPU Operator manages all GPU software)
5. ✅ **Storage**: 800GB OS + 3TB data disks
6. ✅ **Register**: Run registration command with network addresses
7. ✅ **Label**: `kubectl label node <name> nvidia.com/gpu.workload.config=vm-passthrough`
8. ✅ **Wait**: GPU Operator installs drivers automatically (5-15 minutes)

**If ANY requirement is not met, the node will NOT be supported for KubeTEE GPU workloads.**

---

**Last Updated**: 2026-07-18  
**NVIDIA Firmware Version**: 25.10.1+  
**Status**: ✅ Production Ready

