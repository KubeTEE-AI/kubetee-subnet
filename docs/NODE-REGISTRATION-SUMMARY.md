# Node Registration Documentation - Summary of Changes

## Overview

Comprehensive documentation for KubeTEE miners to register their nodes to RKE2 clusters managed by Rancher.

**Location**: `kubetee-subnet/docs/NODE-REGISTRATION.md`

---

## Key Requirements Documented

### 1. Minimum Node Resources

| Resource | Minimum | Purpose |
|----------|---------|---------|
| **CPU** | 8 cores | etcd + control-plane + worker |
| **RAM** | 16 GB | All cluster components |
| **OS Disk** | **800 GB** | System + `/var/lib/longhorn/` |
| **Data Disk** | **3 TB** | `/data` - Longhorn storage (REQUIRED) |

### 2. Cluster Architecture

- **Minimum 3 nodes** with `--etcd --controlplane --worker`
- All-in-one configuration for cost-effectiveness
- etcd quorum: 3 nodes = tolerates 1 failure

### 3. Network Configuration

**Required registration flags**:
```bash
--address <public-ip-address>      # External/public IP
--internal-address <local-network-ip>  # Internal/private IP
--etcd --controlplane --worker     # For first 3+ nodes
```

**IP Discovery Commands**:
- Public IP: `curl -4 ifconfig.me`
- Private IP: `hostname -I | awk '{print $1}'`

**Network Examples**:
- Cloud Provider: Public + Private VPC IP
- On-Premise DMZ: DMZ + Internal network
- Private Network: Same IP for both
- Multiple NICs: WAN + LAN interfaces

### 4. Storage Requirements

**OS Disk (800 GB minimum)**:
- Operating system and applications
- `/var/lib/longhorn/` - Default Longhorn storage
- System overhead and logs

**Data Disk (3 TB minimum) - REQUIRED**:
- `/data` - Additional Longhorn storage
- AI/ML model storage
- Training data and checkpoints
- Application persistent volumes
- Database storage

**Disk Setup Process**:
1. Identify disk via `lsblk`
2. Partition with `fdisk`
3. Format with `ext4` or `xfs`
4. Mount at `/data`
5. Add to `/etc/fstab` for persistence

### 5. GPU Node Requirements (Confidential Computing ONLY)

#### CPU Requirements (MANDATORY for GPU nodes)

**Supported CPUs**:

| Vendor | Technology | Generation | Codename | Series | Status |
|--------|------------|------------|----------|--------|--------|
| **Intel** | TDX | **6th Gen Xeon Scalable** | **Granite Rapids** | Xeon 6xxx | ✅ Supported |
| **Intel** | TDX | **5th Gen Xeon Scalable** | **Emerald Rapids** | Xeon 5xxx | ✅ Supported |
| **AMD** | SEV-SNP | **5th Gen EPYC** | **Turin** | **EPYC 9xx5** | ✅ Supported |
| **AMD** | SEV-SNP | **4th Gen EPYC** | **Genoa** | **EPYC 9xx4** | ✅ Supported |

**NOT Supported**:
- Intel 4th Gen Xeon (Sapphire Rapids) or older
- AMD 3rd Gen EPYC (Milan) or older

#### GPU Requirements (MANDATORY for GPU nodes)

**Supported GPU Models**:
- ✅ **NVIDIA H100 (Hopper)** - 80GB HBM3
- ✅ **NVIDIA H200 (Hopper)** - 141GB HBM3e
- ⏳ **NVIDIA B200 (Blackwell)** - Coming soon (not yet supported)

**GPU Configuration**:
- **Exactly 8 GPUs per node** (MANDATORY)
- **Latest firmware installed** (MANDATORY) - [NVIDIA DGX H100/H200 Firmware Guide](https://docs.nvidia.com/dgx/dgxh100-fw-update-guide/)
- **PPCIe (Protected PCIe) mode enabled** (MANDATORY)
- **All GPUs must be the same model** (no mixing)

**Valid Configurations**:
- ✅ 8x NVIDIA H100 80GB
- ✅ 8x NVIDIA H200 141GB
- ❌ 4x NVIDIA H100 (wrong count)
- ❌ 8x NVIDIA A100 (wrong model)
- ❌ 4x H100 + 4x H200 (mixed models)
- ❌ 8x NVIDIA B200 (not yet supported)

#### GPU Node Label

```bash
kubectl label node <node-name> nvidia.com/gpu.workload.config=vm-passthrough
```

**What NOT to Install**:
- ❌ DO NOT install NVIDIA drivers
- ❌ DO NOT install CUDA toolkit
- ❌ DO NOT install nvidia-docker or nvidia-container-toolkit
- ❌ DO NOT install GPU Operator

**All GPU software is installed automatically by GPU Operator (deployed via Fleet)**

#### GPU Verification (WITHOUT drivers)

```bash
# Verify exactly 8 GPUs (no drivers needed)
lspci | grep -i nvidia | grep -i "3D controller\|VGA" | wc -l
# MUST output: 8

# Verify GPU model via PCI device ID
lspci -nn | grep -i nvidia
# For H100: Look for [10de:2330] or [10de:2331]
# For H200: Look for Device ID [10de:2331]
# All 8 GPUs must have the same device ID
```

**Note**: `nvidia-smi` will NOT work until GPU Operator installs drivers (happens automatically after node registration).

---

## Documentation Structure

### Main Sections

1. **Prerequisites** - Kernel, resources, network, GPU requirements
2. **Cluster Architecture** - 3+ nodes, roles, quorum
3. **Step 1**: Get Registration Command - From infrastructure team
4. **Step 2**: Run Registration Command - With network flags
5. **Step 3**: Verify Node Registration - Check node joined
6. **Step 4**: Prepare Storage Disks - 800GB OS + 3TB data
7. **Step 5**: Longhorn Disk Configuration - Done by infrastructure team
8. **Step 6**: Configure GPU Nodes - Label for vm-passthrough
9. **Step 7**: Verify Deployment - Final checks
10. **Troubleshooting** - Common issues and solutions
11. **Best Practices** - Storage, networking, security, monitoring
12. **Quick Reference** - All commands in one place

### Supporting Documentation

- **MINER_INFRA.md** - Initial kernel and etcd setup
- **CREATE-CLUSTER-GUIDE.md** - Infrastructure team cluster creation process

---

## Key Workflows

### For Miners (Step-by-Step)

1. ✅ Complete kernel setup (MINER_INFRA.md)
2. ✅ Verify minimum resources (8 cores, 16GB RAM, 800GB + 3TB disks)
3. ✅ Find public and private IPs
4. ✅ Run registration command (provided by infrastructure team)
5. ✅ Verify node joined cluster
6. ✅ Prepare `/data` disk (3TB minimum)
7. ✅ (GPU nodes only) Verify TDX/SNP, 8x H100/H200, label node
8. ✅ Wait for infrastructure team to configure Longhorn disks
9. ✅ Verify deployment complete

### For Infrastructure Team

1. ✅ Create cluster via Rancher API
2. ✅ Get registration command
3. ✅ Provide command to miners
4. ✅ Wait for miners to register nodes (3+ nodes minimum)
5. ✅ Run `./configure-longhorn-disks.sh` to configure storage
6. ✅ Verify StorageClasses and Longhorn configuration
7. ✅ Verify GPU Operator is running (for GPU nodes)

---

## Critical Points Emphasized

### ⚠️ DO NOT Install on Nodes

- ❌ NVIDIA drivers
- ❌ CUDA toolkit
- ❌ nvidia-docker or nvidia-container-toolkit
- ❌ GPU Operator

**Reason**: All GPU software is installed automatically by GPU Operator via Fleet.

### ✅ What Miners MUST Do

**All Nodes**:
- Ubuntu 24.04 (clean OS)
- 8 cores, 16GB RAM minimum
- 800GB OS disk + 3TB data disk
- Kernel settings configured
- etcd user/group created
- Network connectivity

**GPU Nodes (Additional)**:
- CPU: Intel 5th/6th Gen Xeon OR AMD EPYC 4th/5th Gen
- TDX or SEV-SNP enabled in BIOS
- Exactly 8x H100 or H200 GPUs (all same model)
- PPCIe mode enabled
- VFIO/IOMMU enabled
- Verify via `lspci` (not nvidia-smi)

### ✅ What Infrastructure Team Does Automatically

- Deploy Longhorn via Fleet
- Deploy GPU Operator via Fleet
- Install NVIDIA drivers on GPU nodes
- Configure GPU device plugins
- Set up StorageClasses
- Configure Longhorn multi-disk storage

---

## Verification Commands (No GPU Drivers Needed)

### CPU Verification

```bash
# Intel TDX
dmesg | grep -i tdx
lscpu | grep -i "Model name"

# AMD SEV-SNP
dmesg | grep -i sev
lscpu | grep -i "Model name"
```

### GPU Verification (Without nvidia-smi)

```bash
# Count GPUs (must be exactly 8)
lspci | grep -i nvidia | grep -i "3D controller\|VGA" | wc -l

# Identify GPU model via device ID
lspci -nn | grep -i nvidia
# H100: [10de:2330] or [10de:2331]
# H200: [10de:2331]
```

### Network Verification

```bash
# Check node IPs
kubectl get node <node-name> -o wide
kubectl get node <node-name> -o jsonpath='{.status.addresses}'
```

### Storage Verification

```bash
# Check disk sizes
df -h /
df -h /data

# Verify Longhorn configuration
kubectl get nodes.longhorn.io -n longhorn-system
kubectl describe node.longhorn.io <node-name> -n longhorn-system
```

---

## Files Modified

### Created/Updated

- ✅ `kubetee-subnet/docs/NODE-REGISTRATION.md` - Complete miner registration guide (1219 lines)
- ✅ `kubetee-subnet/docs/MINER_INFRA.md` - Updated with link to NODE-REGISTRATION.md
- ✅ `CREATE-CLUSTER-GUIDE.md` - Updated for infrastructure team with miner references
- ✅ `configure-longhorn-disks.sh` - Automated Longhorn disk configuration script

### Documentation Coverage

- ✅ Cluster architecture (3+ nodes, etcd quorum)
- ✅ Resource requirements (8 cores, 16GB, 800GB + 3TB)
- ✅ Network configuration (public/private IPs)
- ✅ Storage setup (OS + data disks)
- ✅ GPU requirements (TDX/SNP, H100/H200, 8 GPUs)
- ✅ Troubleshooting (common issues and solutions)
- ✅ Best practices (storage, networking, security)
- ✅ Quick reference (all commands in one place)

---

## Testing Checklist

Before deploying to production, miners should verify:

- [ ] CPU meets generation requirements (Intel 5th/6th Gen OR AMD EPYC 4th/5th Gen for GPU nodes)
- [ ] TDX or SEV-SNP enabled and verified (GPU nodes only)
- [ ] OS disk is 800 GB minimum
- [ ] Data disk is 3 TB minimum and mounted at `/data`
- [ ] Network connectivity to Rancher management cluster
- [ ] Public and private IP addresses identified
- [ ] For GPU nodes: Exactly 8x H100 or H200 detected via lspci
- [ ] For GPU nodes: Latest firmware installed (DGX H100/H200 firmware guide)
- [ ] NO NVIDIA drivers or CUDA installed (clean Ubuntu 24.04)

---

**Last Updated**: 2025-10-29  
**Version**: 1.0  
**Target Audience**: KubeTEE Miners  
**Status**: ✅ Complete and Ready for Use

