# Node Registration to RKE2 Cluster

This guide is for **miners** who need to register their nodes to an RKE2 cluster managed by Rancher.

> **Validator contract (2026-07-24):** eligibility is the **hotkey** — the
> cluster carries `kubetee.ai/hotkey == your registered hotkey` (one cluster
> per hotkey) and is not banned (`kubetee.ai/ban != "true"`) and is ready.
> The former canonical enrollment binding is no longer required by the
> validator. See `validator/rancher_client.py` for the implemented label
> contract.

## Prerequisites

Before registering your node, ensure the infrastructure setup is complete:

1. ✅ **Kernel settings configured**
2. ✅ **Node meets minimum requirements**:
   - Ubuntu 26.04
   - etcd user/group created
   - Minimum resources: 8 CPU cores, 16 GB RAM
   - Minimum storage: 1.92 TB OS disk in RAID 1 + 21 TB raw block device (unpartitioned, unformatted)
3. ✅ **Network connectivity** to Rancher management cluster
4. ✅ **GPU worker nodes** (at least one for production eligibility):
   - **CPU with TDX (Intel 5th/6th Gen) or SEV-SNP (AMD 4th/5th Gen)** - MANDATORY for GPU nodes
   - **Exactly 8x NVIDIA H100, H200, B200, B300, or 8x RTX PRO 6000 Blackwell Server Edition GPUs** - MANDATORY for GPU nodes
   - **Latest firmware installed** - See [NVIDIA DGX Firmware Guide](https://docs.nvidia.com/dgx/dgxh100-fw-update-guide/)
   - VFIO/IOMMU configured for passthrough
5. ✅ **100 TAO deposit** held as on-chain registration collateral on the mining
   hotkey — see [Miner deposit](../README.md#miner-deposit-registration-collateral).
   The deposit stays on your own hotkey (KubeTEE never holds it and cannot move
   it) and is released back to withdrawable stake as the hotkey earns emission.
   A hotkey below the requirement is scored 0 after a grace window, which stops
   emission and therefore freezes the deposit until you top up — nothing is
   confiscated, and the freeze reverses as soon as you are back in compliance.

## Enrolled Cluster Binding and Validation

The platform enrollment flow identifies the cluster through the canonical
`kubetee.ai/hotkey` label and writes the full binding contract: binding ID,
hotkey, coldkey, provider ID, binding status, generation, netuid, network,
origin fingerprint prefix, and the `kubetee.ai/enrollment-uid` annotation.
These are operator-controlled trust metadata; miners must not hand-edit them.

`kubetee.ai/binding-status=ENROLLED` confirms onboarding only. On every
complete cycle, the subnet validator compares the binding to the fresh
metagraph and validates the Rancher cluster/node inventory. The production
profile requires Ready HA topology (3 etcd and 3 control-plane nodes), a
schedulable worker, at least 8 CPU cores and 16 GiB per active node, and at
least one schedulable eight-GPU H100/H200/B200/B300/RTX PRO 6000 worker with
`vm-passthrough` and `kata-qemu-nvidia-gpu-tdx`. Any explicit missing,
malformed, ambiguous, or unhealthy evidence scores **0**. A Rancher outage
skips the whole weight cycle instead of blaming miners.

This infrastructure verdict does not prove current TEE attestation, a live
tunnel and end-to-end probe, expected workload identity, Armada readiness,
or an unexpired KeyLease. Those remain separate serving requirements. The
validator implementation lives in the `validator/` directory — see
`validator/infrastructure_validation.py` for the running readiness policy.

## Cluster Architecture Requirements

**IMPORTANT**: For a production RKE2 cluster, you need:

- **Minimum 3 etcd nodes** - For quorum and high availability
- **Minimum 3 control-plane nodes** - For Kubernetes control plane HA
- **Worker nodes** - Can be combined with control-plane if resources allow

### Node Role Combinations

| Configuration | etcd | control-plane | worker | Recommended For |
|---------------|------|---------------|--------|-----------------|
| **All-in-One** | ✅ | ✅ | ✅ | Small clusters (3+ nodes with adequate resources) |
| **Separated** | ✅ | ✅ | ❌ | Large clusters (dedicated control plane + worker nodes) |
| **Worker Only** | ❌ | ❌ | ✅ | Scaling workload capacity only |

### Recommended Setup

**For most KubeTEE clusters (Small to Medium)**:
- **3+ nodes** running `--etcd --controlplane --worker`
- Each node serves all roles (if resources permit)
- Simple to manage, cost-effective

**Minimum Resources per All-in-One Node**:
- **CPU**: 8 cores
- **RAM**: 16 GB
- **OS Disk**: **1.92 TB minimum (RAID 1)**

	- Two mirrored drives (mirror array), no stripe — OS must survive a single-disk failure
	- Used for system, container images, containerd data, and OS overhead
- **Data Disk**: **21 TB minimum** (raw block device — **no partition, no filesystem, no mount**)

**For Large Clusters**:
- **3 dedicated control-plane nodes**: `--etcd --controlplane` (no `--worker`)
- **N worker nodes**: `--worker` only
- Better resource isolation

### Why 3 Nodes Minimum?

- **etcd quorum**: Requires (N/2)+1 nodes to maintain quorum
  - 3 nodes = tolerates 1 failure
  - 5 nodes = tolerates 2 failures
- **Control plane HA**: Load balancing across multiple API servers
- **Production stability**: No single point of failure

---

## Step 1: Get Registration Command

The KubeTEE infrastructure team will provide you with a registration command after creating your cluster.

**Cluster Naming Convention**: `<continent-2letter>-<country-2letter>-<city-fullname>-<miner-uid>`

**Examples**:
- `eu-fr-paris-123` - Europe, France, Paris, Miner UID 123
- `na-us-newyork-456` - North America, USA, New York, Miner UID 456
- `as-jp-tokyo-789` - Asia, Japan, Tokyo, Miner UID 789

The registration command will look like:

```bash
# All-in-One node (recommended for KubeTEE clusters)
curl -fL https://rancher.example.com/system-agent-install.sh | sudo sh -s - \
  --server https://rancher.example.com \
  --token <your-cluster-token> \
  --ca-checksum <checksum> \
  --address <public-ip-address> \
  --internal-address <local-network-ip> \
  --etcd --controlplane --worker

# OR Worker-only node (for scaling workloads)
curl -fL https://rancher.example.com/system-agent-install.sh | sudo sh -s - \
  --server https://rancher.example.com \
  --token <your-cluster-token> \
  --ca-checksum <checksum> \
  --address <public-ip-address> \
  --internal-address <local-network-ip> \
  --worker
```

**Important Network Flags**:
- `--address` - External/public IP address (used for external communication). The system-agent maps this to RKE2 `--node-external-ip`, so it becomes the Kubernetes node `status.addresses.ExternalIP` — the IP that **ServiceLB** advertises on `LoadBalancer` services and that **external-dns** writes to DNS A records. For a generic onboarding script that works on every node without hardcoding an IP, use the dynamic value `--address ipify` (auto-detects the public IP via `https://api.ipify.org`).
- `--internal-address` - Internal/private IP address (used for internal cluster communication). Can also be an interface name (e.g. `eth0`); if omitted, it auto-detects the default-route source IP.

These flags are **required** for proper node networking, especially in multi-network environments. A node registered without `--address` has no `ExternalIP`, so `LoadBalancer` services get no routable address and external-dns cannot publish them.

---

## Step 2: Run Registration Command

On your node, execute the registration command provided by the infrastructure team:

```bash
# Example registration command (use the actual command provided to you)
curl -fL https://rancher.example.com/system-agent-install.sh | sudo sh -s - \
  --server https://rancher.example.com \
  --token <your-token> \
  --ca-checksum <checksum> \
  --address <public-ip-address> \
  --internal-address <local-network-ip> \
  --etcd --controlplane --worker
```

**Important Flags**:
- `--server` - Rancher server URL
- `--token` - Cluster registration token
- `--ca-checksum` - CA certificate checksum for validation
- `--address` - External/public IP address of this node
- `--internal-address` - Internal/private IP address of this node
- `--etcd` - Run etcd (required for control plane nodes)
- `--controlplane` - Run Kubernetes control plane components
- `--worker` - Run workloads on this node

### Which Flags to Use?

**For the first 3+ nodes** (establishing the cluster):
```bash
--etcd --controlplane --worker
```
This creates an all-in-one node that serves all roles. **Recommended for most KubeTEE clusters.**

**For additional worker nodes** (scaling workload capacity):
```bash
--worker
```
This adds pure worker nodes without etcd or control-plane responsibilities.

**Important**:
- **Always register at least 3 nodes with `--etcd --controlplane`** to establish quorum
- You can add more all-in-one nodes or worker-only nodes after the initial 3
- Do NOT register fewer than 3 etcd nodes in production

### Understanding Network Addresses

**`--address` (External/Public IP)**:
- IP address that external clients and other clusters use to reach this node
- Used for external communication (e.g., accessing services from outside)
- Can be a public IP or the IP reachable from other networks

**`--internal-address` (Internal/Private IP)**:
- IP address used for internal cluster communication
- Used for pod-to-pod, node-to-node communication within the cluster
- Should be the IP on your private/internal network
- Typically provides better performance and lower latency

### How to Find Your IP Addresses

```bash
# Find your public/external IP
curl -4 ifconfig.me

# OR
curl -4 icanhazip.com

# Find your internal/private IP
ip addr show | grep 'inet ' | grep -v '127.0.0.1'

# OR for a specific interface (e.g., eth0, ens3, enp0s3)
ip addr show eth0 | grep 'inet ' | awk '{print $2}' | cut -d/ -f1

# OR using hostname -I
hostname -I | awk '{print $1}'
```

> **Tip:** you can skip the manual public-IP lookup by passing `--address ipify` directly in the registration command — the system-agent runs `curl https://api.ipify.org` for you and registers that as the node `ExternalIP`.

### Network Configuration Examples

#### Example 1: Cloud Provider (AWS, GCP, Azure)
```bash
# Node has both public and private IPs
--address 203.0.113.10          # Public IP (external)
--internal-address 10.0.1.5     # Private VPC IP (internal)
```

#### Example 2: On-Premise with DMZ
```bash
# Node in DMZ with public-facing IP and internal network
--address 198.51.100.25         # DMZ IP (external)
--internal-address 192.168.1.10 # Internal network IP
```

#### Example 3: Private Network Only
```bash
# Node only has private IP (no public internet)
--address 10.0.1.5              # Private IP (external)
--internal-address 10.0.1.5     # Same private IP (internal)
```

#### Example 4: Multiple Network Interfaces
```bash
# Node has multiple NICs
--address 203.0.113.10              # WAN interface (public)
--internal-address <local-network-ip>   # LAN/cluster interface (private)
```

### Verification

After registration, verify the addresses are correctly configured:

```bash
# Check node details
kubectl get node <your-node-name> -o wide

# Check internal and external IPs
kubectl get node <your-node-name> -o jsonpath='{.status.addresses[*].type}: {.status.addresses[*].address}{"\n"}'

# Expected output:
# InternalIP ExternalIP Hostname: <local-network-ip> <public-ip-address> node-name
```

---

## Step 3: Verify Node Registration

After running the registration command, verify the node has joined the cluster:

```bash
# Check system-agent status
sudo systemctl status system-agent

# Check RKE2 status
sudo systemctl status rke2-server  # For control plane nodes
# OR
sudo systemctl status rke2-agent   # For worker-only nodes

# Check node status (from management cluster or another cluster node)
kubectl get nodes
```

Expected output:
```
NAME              STATUS   ROLES                       AGE   VERSION
your-node-name    Ready    control-plane,etcd,worker   5m    v1.33.4+rke2r1
```

---

## Step 4: Prepare Storage Disks (Raw Block Device)

KubeTEE miner clusters use **raw block storage** — a dedicated data device is exposed directly to the hypervisor/guest as a raw block device. There is no distributed storage layer on miner nodes; the device is consumed **unpartitioned, unformatted, and unmounted**.

**IMPORTANT Storage Requirements**:
- **OS Disk**: **1.92 TB minimum (RAID 1)** (system, container images, containerd data, logs)
- **Data Device**: **21 TB minimum** (raw block device — no partition, no filesystem, no mount)

### Raw Block Device (REQUIRED)

You **must** have a dedicated raw block device with at least **21 TB** capacity.

**This is NOT optional** — KubeTEE GPU-class workloads require the raw block device for:
- AI/ML model weights and training state
- Confidential computing encrypted volumes
- Multi-epoch checkpoints and data pipelines

#### Option A: Automated Disk Setup (Recommended)

Use the provided Ansible playbook (infrastructure team):

```bash
# From the kubetee repository
cd ansible
ansible-playbook -i inventory.yaml prepare-disks.yaml
```

#### Option B: Manual Disk Setup

If you prefer manual setup:

##### 1. Identify the Disk

```bash
# List all block devices
lsblk

# Expected output:
# NAME   MAJ:MIN RM  SIZE RO TYPE MOUNTPOINT
# sda      8:0    0  1.9T  0 disk  ← OS (RAID 1, mirrored)
# ├─sda1   8:1    0  1.9T  0 part /
# └─sda2   8:2    0    1G  0 part [SWAP]
# sdb      8:16   0 21.5T  0 disk  ← Your GPU data device (min 21TB)
```

##### 2. DO NOT Partition or Format

The device must remain **unpartitioned, unformatted, and unmounted**. KubeTEE consumes the block device raw — the hypervisor/guest handles any internal layout. Do **not** run `fdisk`, `mkfs`, `mount`, or add it to `/etc/fstab`.

##### 3. Verify the Device

```bash
# Confirm the device is present with no partitions, no mountpoint, no filesystem
lsblk /dev/sdb

# Expected output: a plain disk with NO sub-partitions and NO MOUNTPOINT
# NAME   MAJ:MIN RM  SIZE RO TYPE MOUNTPOINT
# sdb      8:16   0 21.5T  0 disk
```

If the device was previously partitioned or formatted, wipe it back to a clean state before registering:

```bash
# Wipe partition table + filesystem signatures (does NOT touch the OS drive)
sudo wipefs -a /dev/sdb
```

### Verify Disk Setup

```bash
# List all block devices — the data device must show NO sub-partitions, NO mountpoint
lsblk /dev/sdb

# Confirm there is no filesystem and nothing mounted from the device
df -h | grep sdb     # Should return nothing
blkid /dev/sdb       # Should return nothing
```

---

## Step 5: Configure Storage (After Cluster Join)

After your node joins the cluster, the infrastructure team configures storage for your raw block device. You only need to ensure the device is visible to the host (e.g., `/dev/sdb`) and NOT partitioned or mounted.

### What Gets Configured

The infrastructure team handles all storage configuration:

1. Verifies your raw block device is present and unpartitioned
2. Provisions the appropriate storage configuration for your cluster

**Note**: You do not need to configure anything yourself — just leave the raw block device unpartitioned and unmounted.

---

## Step 6: Configure GPU Nodes (If Applicable)

**IMPORTANT**: KubeTEE has **strict requirements** for GPU nodes. Your GPU node MUST meet ALL of these:

### GPU Node Requirements Summary

**✅ MUST Have ALL of:**
1. **CPU**: Intel 5th/6th Gen Xeon OR AMD EPYC 4th/5th Gen
2. **Confidential Computing**: 
   - **Intel**: TDX (Trust Domain Extensions)
   - **AMD**: SEV-SNP **ONLY** (Secure Encrypted Virtualization - Secure Nested Paging)
     - ⚠️ Older AMD SEV and SEV-ES are NOT supported (use SEV-SNP only)
3. **GPU Model**: NVIDIA H100, H200, B200, B300, or RTX PRO 6000 Blackwell Server Edition (Hopper/Blackwell architecture)
4. **GPU Count**: Exactly 8 GPUs (all same model)
5. **Latest Firmware**: Updated per [NVIDIA DGX H100/H200 Firmware Update Guide](https://docs.nvidia.com/dgx/dgxh100-fw-update-guide/)
6. **GPU Mode**: PPCIe (Protected PCIe) enabled
7. **VFIO/IOMMU**: Enabled for GPU passthrough

**❌ NOT Supported:**
- Older CPUs (Intel 4th Gen, AMD 3rd Gen or earlier)
- Other GPU models (A100, V100, RTX series, etc.)
- Nodes with fewer or more than 8 GPUs
- Mixed GPU models (e.g., 4x H100 + 4x H200)
- Outdated firmware versions

---

### Supported CPU Platforms (MANDATORY)

| Vendor | Technology | Generation | Codename | Series | Status |
|--------|------------|------------|----------|--------|--------|
| **Intel** | **TDX** | **6th Gen Xeon Scalable** | **Granite Rapids** | Xeon 6xxx | ✅ Supported |
| **Intel** | **TDX** | **5th Gen Xeon Scalable** | **Emerald Rapids** | Xeon 5xxx | ✅ Supported |
| Intel | TDX | 4th Gen Xeon Scalable | Sapphire Rapids | - | ❌ NOT Supported |
| **AMD** | **SEV-SNP** | **5th Gen EPYC** | **Turin** | **EPYC 9xx5** | ✅ Supported |
| **AMD** | **SEV-SNP** | **4th Gen EPYC** | **Genoa** | **EPYC 9xx4** | ✅ Supported |
| AMD | SEV / SEV-ES | 3rd Gen EPYC | Milan | EPYC 7xx3 | ❌ NOT Supported |

**GPU nodes MUST have one of the supported CPU generations listed above.**

**⚠️ AMD SEV Evolution**:
- **SEV-SNP** (Secure Nested Paging) - ✅ Supported - Latest and most secure
- SEV-ES (Encrypted State) - ❌ NOT Supported - Older technology with vulnerabilities
- SEV (Basic) - ❌ NOT Supported - Deprecated, has known security issues

**Only AMD EPYC 4th/5th Gen with SEV-SNP are accepted.** Earlier EPYC generations (1st-3rd Gen) with older SEV/SEV-ES are NOT supported.

If your node has NVIDIA GPUs with confidential computing support (TDX or SNP) that will be used for **confidential VM workloads** (GPU passthrough), you need to label the node appropriately.

### GPU Hardware Requirements

**Supported GPU Models**:
- ✅ **NVIDIA H100 (Hopper)** - 80GB HBM3
- ✅ **NVIDIA H200 (Hopper)** - 141GB HBM3e
- ✅ **NVIDIA B200 (Blackwell)** - 180GB HBM3e
- ✅ **NVIDIA B300 (Blackwell)** - 288GB HBM3e
- ✅ **NVIDIA RTX PRO 6000 Blackwell Server Edition** - 96GB GDDR7 ECC (CC mode on)

**Requirements**:
- **Exactly 8 GPUs per node** - No more, no less
- **PPCIe (Protected PCIe) mode enabled** - Required for confidential computing
- **All GPUs must be the same model** - No mixing models

**Examples of Valid Configurations**:
- ✅ 8x NVIDIA H100 80GB
- ✅ 8x NVIDIA H200 141GB
- ✅ 8x NVIDIA B200 180GB
- ✅ 8x NVIDIA B300 288GB
- ✅ 8x NVIDIA RTX PRO 6000 96GB GDDR7 ECC
- ❌ 4x NVIDIA H100 (not enough GPUs)
- ❌ 8x NVIDIA A100 (wrong GPU model)
- ❌ 4x H100 + 4x H200 (mixed models)
- ❌ 8x NVIDIA A100 (wrong GPU model)



### GPU Node Prerequisites

**CRITICAL REQUIREMENTS**:

**1. Confidential Computing Support (MANDATORY)**

Your node MUST have one of these:

**Intel TDX (Trust Domain Extensions)**:
```bash
# Check for TDX support
dmesg | grep -i tdx

# Expected output should show TDX initialization
# Example: "tdx: TDX module initialized"

# Verify CPU is 5th or 6th Gen Xeon (MANDATORY)
lscpu | grep -i "Model name"
# MUST show one of:
# - Intel(R) Xeon(R) ... (Emerald Rapids) - 5th Gen
# - Intel(R) Xeon(R) ... (Granite Rapids) - 6th Gen

# Check CPU family/model
cat /proc/cpuinfo | grep -E "cpu family|model\s|model name" | head -3
```

**AMD SEV-SNP (Secure Encrypted Virtualization - Secure Nested Paging)**:
```bash
# Check for SEV-SNP support (MUST be SEV-SNP, not older SEV or SEV-ES)
dmesg | grep -i "sev-snp\|snp"

# Expected output should show SEV-SNP enabled
# Example: "SEV-SNP supported" or "AMD Secure Nested Paging (SEV-SNP) active"

# Additional check
cat /sys/module/kvm_amd/parameters/sev_snp
# Should output: Y or 1

# Verify CPU is 4th or 5th Gen EPYC (MANDATORY)
lscpu | grep -i "Model name"
# MUST show one of:
# - AMD EPYC 9xx4 series (Genoa) - 4th Gen
# - AMD EPYC 9xx5 series (Turin) - 5th Gen

# Check CPU family/model
cat /proc/cpuinfo | grep -E "cpu family|model\s|model name" | head -3
```

**⚠️ Important**: KubeTEE requires **SEV-SNP** specifically. Older AMD SEV and SEV-ES technologies are NOT supported due to known security vulnerabilities. Only EPYC 4th Gen (Genoa) and 5th Gen (Turin) with SEV-SNP are accepted.

**2. NVIDIA GPU Requirements (MANDATORY)**

KubeTEE has specific GPU requirements:

**Supported GPUs**:
- ✅ **NVIDIA H100 (Hopper)** with PPCIe protected mode
- ✅ **NVIDIA H200 (Hopper)** with PPCIe protected mode
- ✅ **NVIDIA B200 (Blackwell)** with CC mode on
- ✅ **NVIDIA B300 (Blackwell)** with CC mode on
- ✅ **NVIDIA RTX PRO 6000 Blackwell Server Edition** with CC mode on
- ❌ Other GPU models - Not supported

**GPU Configuration Requirements**:
- **Exactly 8 GPUs per node** (MANDATORY)
- **PPCIe (Protected PCIe) mode enabled** (MANDATORY)
- **Latest firmware installed** (MANDATORY) - See [NVIDIA DGX H100/H200 Firmware Update Guide](https://docs.nvidia.com/dgx/dgxh100-fw-update-guide/)
- GPUs must support confidential computing

```bash
# Verify GPU count (MUST be exactly 8)
lspci | grep -i nvidia | grep -i "3D controller\|VGA" | wc -l
# Expected output: 8

# List all GPUs and identify model
lspci | grep -i nvidia

# Expected output (8 GPUs):
# 17:00.0 3D controller: NVIDIA Corporation Device 2330 (rev a1)  ← H100
# 65:00.0 3D controller: NVIDIA Corporation Device 2330 (rev a1)
# ... (6 more lines for total of 8 GPUs)

# For H100: Device ID 2330 or 2331
# For H200: Device ID 2331 (check lspci -nn for device IDs)
```

**Note**: Do NOT install NVIDIA drivers or CUDA. The GPU Operator will install drivers automatically after the node joins the cluster.

**3. Latest Firmware (MANDATORY)**

**Before registering GPU nodes**, ensure you have the latest firmware installed:

```bash
# Check current firmware version (if nvfwupd is available on DGX systems)
# For DGX H100/H200 systems:
nvfwupd --query

# Update firmware following the official guide:
# https://docs.nvidia.com/dgx/dgxh100-fw-update-guide/
```

**Critical firmware components to update**:
- BMC (Baseboard Management Controller)
- BIOS/UEFI
- GPU firmware
- PCIe switches and retimers
- Network adapter firmware (ConnectX-7, Intel NIC)

**Refer to the official guide**: [NVIDIA DGX H100/H200 Firmware Update Guide](https://docs.nvidia.com/dgx/dgxh100-fw-update-guide/)

**Important**: Firmware updates are typically done on DGX systems. If you're using custom-built servers with H100/H200 GPUs, consult with your hardware vendor for firmware update procedures.

**4. VFIO/IOMMU enabled** (for GPU passthrough)
```bash
# Check IOMMU groups
ls /sys/kernel/iommu_groups/

# Verify IOMMU is enabled
dmesg | grep -i iommu

# For Intel (VT-d)
dmesg | grep -i "Intel-IOMMU"

# For AMD (AMD-Vi)
dmesg | grep -i "AMD-Vi"
```

**What you do NOT need to do**:
- ❌ Install NVIDIA drivers manually (GPU Operator does this automatically)
- ❌ Install the GPU Operator (deployed automatically via Fleet)
- ❌ Configure GPU device plugins (GPU Operator handles this)

**What you MUST do**:
- ✅ **Verify CPU is one of the supported generations** (MANDATORY):
  - Intel 5th Gen Xeon (Emerald Rapids) OR 6th Gen Xeon (Granite Rapids)
  - AMD EPYC 4th Gen (Genoa 9xx4) OR 5th Gen (Turin 9xx5)
- ✅ **Verify TDX or SEV-SNP is enabled in BIOS** (MANDATORY)
- ✅ **Verify TDX or SEV-SNP support in kernel** (MANDATORY)
- ✅ **Verify exactly 8 NVIDIA H100, H200, B200, B300, or RTX PRO 6000 Blackwell Server Edition GPUs are installed** (MANDATORY)
- ✅ **Update to latest firmware** (MANDATORY) - [NVIDIA DGX H100/H200 Firmware Update Guide](https://docs.nvidia.com/dgx/dgxh100-fw-update-guide/)
- ✅ Enable VFIO/IOMMU in BIOS and kernel
- ✅ Label the node after registration

**⚠️ CRITICAL**: 
- Older CPU generations (Intel 4th Gen Xeon, AMD 3rd Gen EPYC or earlier) are NOT supported
- Only H100/H200 GPUs with PPCIe mode are supported
- Nodes MUST have exactly 8 GPUs (no more, no less)
- Latest firmware MUST be installed before registration

### GPU Operator - Automatic Installation

**Important**: You do NOT need to install the GPU Operator manually. It is **automatically deployed by Fleet/GitOps** to all clusters.

**What happens automatically**:
1. ✅ GPU Operator is deployed by the infrastructure team via Fleet
2. ✅ NVIDIA drivers are automatically installed on GPU nodes
3. ✅ GPU Operator detects the `vm-passthrough` label and configures GPUs accordingly
4. ✅ All GPU resources are automatically configured

---

## Troubleshooting

### Node Not Joining Cluster

**Problem**: Node doesn't appear in `kubectl get nodes`

**Solutions**:
```bash
# Check system-agent logs
sudo journalctl -u system-agent -f

# Check RKE2 logs
sudo journalctl -u rke2-server -f  # Control plane
sudo journalctl -u rke2-agent -f   # Worker

# Restart services
sudo systemctl restart system-agent
sudo systemctl restart rke2-server  # or rke2-agent

# Check firewall (ensure required ports are open)
sudo ufw status
```

### Incorrect IP Addresses

**Problem**: Node registered with wrong IP addresses or nodes can't communicate

**Symptoms**:
- Node shows wrong IP in `kubectl get nodes -o wide`
- Pods can't communicate across nodes
- etcd cluster not forming

**Solutions**:

1. **Verify current node IPs**:
```bash
# Check node addresses
kubectl get node <node-name> -o jsonpath='{.status.addresses}'

# Should show both InternalIP and ExternalIP
```

2. **Re-register with correct IPs**:
```bash
# 1. First, drain and delete the node from cluster
kubectl drain <node-name> --ignore-daemonsets --delete-emptydir-data
kubectl delete node <node-name>

# 2. On the node, stop and clean up RKE2
sudo systemctl stop rke2-server  # or rke2-agent
sudo systemctl stop system-agent
sudo rm -rf /var/lib/rancher/rke2
sudo rm -rf /etc/rancher/rke2

# 3. Re-register with correct IPs
curl -fL https://rancher.example.com/system-agent-install.sh | sudo sh -s - \
  --server https://rancher.example.com \
  --token <your-token> \
  --ca-checksum <checksum> \
  --address <CORRECT-PUBLIC-IP> \
  --internal-address <CORRECT-PRIVATE-IP> \
  --etcd --controlplane --worker
```

3. **Common IP mistakes**:
```bash
# Wrong: Using 127.0.0.1 or localhost
--internal-address 127.0.0.1  # ❌ DON'T USE

# Wrong: Using Docker bridge IP
--internal-address 172.17.0.1  # ❌ DON'T USE

# Correct: Using actual network interface IP
--internal-address <local-network-ip>  # ✅ CORRECT

# Find correct IP
ip addr show | grep 'inet ' | grep -v '127.0.0.1' | grep -v '172.17'
```

### Network Connectivity Issues

**Problem**: Nodes can't communicate with each other

**Solutions**:
```bash
# Test connectivity between nodes
ping <other-node-internal-ip>

# Test specific ports (from another node)
# etcd: 2379, 2380
# kube-apiserver: 6443
# kubelet: 10250
nc -zv <node-internal-ip> 6443
nc -zv <node-internal-ip> 2379

# Check firewall rules
sudo ufw status verbose

# Required ports for RKE2:
# 6443/tcp - Kubernetes API
# 2379-2380/tcp - etcd
# 10250/tcp - kubelet
# 9345/tcp - RKE2 supervisor API
# 4789/udp - Calico VXLAN
```

### Raw Block Device Not Recognized

**Problem**: The GPU data device is not visible to the host.

**Solutions**:
```bash
# Confirm the device exists at the block level
lsblk

# Confirm the device has no sub-partitions (must be raw)
lsblk /dev/sdb

# If the device was previously partitioned, wipe it back to raw
sudo wipefs -a /dev/sdb

# If still not visible, check RAID/disk controller with smartctl
sudo smartctl -a /dev/sdb
```

### Raw Block Device Not Usable

**Problem**: The device shows partitions or a filesystem.

**Solutions**:
```bash
# Confirm current state
lsblk /dev/sdb
blkid /dev/sdb        # Must return nothing

# Wipe filesystem signatures (keeps data, removes metadata)
sudo wipefs -a /dev/sdb

# Verify clean state
blkid /dev/sdb       # Must return nothing
lsblk /dev/sdb       # Must show no sub-partitions
```

---

## Storage Configuration Reference

### Disk Paths

| Path | Purpose | Required | Minimum Size | Recommended Size |
|------|---------|----------|--------------|------------------|
| `/` (OS Disk) | System + containerd data | ✅ Yes (RAID 1) | **1.92 TB** | 1.92 TB (RAID 1) |
| `/dev/sdX` | Raw block storage (unpartitioned) | ✅ **Required** | **21 TB** | 21 TB+ |

### Reserved Space

Set aside enough free space on the OS disk to keep the system stable:

- **OS Disk**: keep at least **500 GB free** — avoids filling up from container images and logs
- **Data Disk**: primary workload storage; plan capacity for your models and data

### Disk Tags (optional)

Label your disk for easier identification (e.g., `/dev/sdb1`, `/dev/nvme0n1`). This helps when the infrastructure team provisions storage for your cluster.

---

## Best Practices

### Storage

1. **Use a dedicated data disk** as a raw block device (not partitions of the OS disk)
2. **Keep the data disk as a raw block device** (no partitions, no filesystem, no mountpoint) — the hypervisor/guest sees the block device directly for maximum performance
3. **Mark the data disk unambiguously** (e.g., `echo "KUBETEE-DATA" | sudo tee /dev/sdX | head -c 16`) so it's easy to identify among devices — **do NOT label it with filesystem tools** (`mkfs`/`e2label`) as that adds metadata to the device
4. **Monitor disk health** using SMART tools:
   ```bash
   sudo apt install smartmontools
   sudo smartctl -a /dev/sdb
   ```

### Networking

1. **Ensure low latency** between nodes (<10ms for best performance)
2. **Use private networks** for inter-node communication
3. **Open required ports** (RKE2, monitoring)

### Security

1. **Keep kernel up to date** (security patches)
2. **Enable automatic security updates**:
   ```bash
   sudo apt install unattended-upgrades
   sudo dpkg-reconfigure -plow unattended-upgrades
   ```
3. **Use SSH keys** instead of passwords
4. **Configure firewall** (ufw, iptables)

### Monitoring

1. **Check node resources** regularly:
   ```bash
   # CPU, memory, disk
   top
   free -h
   df -h
   ```

2. **Monitor storage metrics** via Prometheus/Grafana (provided by infrastructure team)

3. **Set up alerts** for disk space, node health, pod failures

---

## Quick Reference Commands

### Registration
```bash
# Find your IPs
curl -4 ifconfig.me                          # Public IP
hostname -I | awk '{print $1}'               # Private IP

# Register all-in-one node (first 3+ nodes)
curl -fL https://rancher.example.com/system-agent-install.sh | sudo sh -s - \
  --server https://rancher.example.com \
  --token <token> \
  --ca-checksum <checksum> \
  --address <public-ip> \
  --internal-address <private-ip> \
  --etcd --controlplane --worker

# Register worker-only node (additional nodes)
curl -fL https://rancher.example.com/system-agent-install.sh | sudo sh -s - \
  --server https://rancher.example.com \
  --token <token> \
  --ca-checksum <checksum> \
  --address <public-ip> \
  --internal-address <private-ip> \
  --worker
```

### Verification
```bash
# Check node status
kubectl get nodes
kubectl get nodes -o wide

# Check node IPs
kubectl get node <node-name> -o jsonpath='{.status.addresses}'

# Check node labels (including GPU labels if applicable)
kubectl get node <node-name> --show-labels

# Check raw block devices (no mounts expected)
lsblk
lsblk /dev/sdb

# For GPU nodes: Check GPU configuration
kubectl get node <node-name> -o json | jq '.metadata.labels | to_entries | map(select(.key | contains("nvidia")))'
```

### Service Management
```bash
# Restart system-agent
sudo systemctl restart system-agent

# Restart RKE2
sudo systemctl restart rke2-server  # Control plane
sudo systemctl restart rke2-agent   # Worker

# Check logs
sudo journalctl -u system-agent -f
sudo journalctl -u rke2-server -f
sudo journalctl -u rke2-agent -f
```

### Networking
```bash
# Test connectivity to other nodes
ping <other-node-internal-ip>

# Test cluster ports
nc -zv <node-ip> 6443   # API server
nc -zv <node-ip> 2379   # etcd
nc -zv <node-ip> 10250  # kubelet
```

### GPU Nodes (with TDX/SNP)
```bash
# FIRST: Verify confidential computing support (MANDATORY)
# For Intel TDX (5th or 6th Gen Xeon):
dmesg | grep -i tdx
lscpu | grep -i "Model name"  # MUST show Emerald Rapids or Granite Rapids

# For AMD SEV-SNP (4th or 5th Gen EPYC):
dmesg | grep -i "sev-snp\|snp"  # Look specifically for SEV-SNP, not just SEV
lscpu | grep -i "Model name"  # MUST show EPYC 9xx4 (Genoa) or 9xx5 (Turin)

# SECOND: Verify GPU requirements (MANDATORY)
# Must have exactly 8 GPUs
lspci | grep -i nvidia | grep -i "3D controller\|VGA" | wc -l  # MUST output: 8

# Verify GPU model via PCI device ID
lspci -nn | grep -i nvidia
# For H100: Look for Device ID [10de:2330] or [10de:2331]
# For H200: Look for Device ID [10de:2331]
# All 8 GPUs must have the same device ID

# Label GPU node for VM passthrough (only if all requirements verified)
kubectl label node <node-name> nvidia.com/gpu.workload.config=vm-passthrough

# Check GPU labels
kubectl get node <node-name> --show-labels | grep gpu

# Verify GPU Operator is running (optional)
kubectl get pods -n gpu-operator-system
```

---

## Getting Help

If you encounter issues:

1. **Check this guide** for troubleshooting steps
2. **Review logs** using journalctl commands above
3. **Contact infrastructure team** with:
   - Node name and cluster name
   - Error messages from logs
   - Output of diagnostic commands
4. **Provide system info**:
   ```bash
   # Gather diagnostic info
   uname -a
   df -h
   free -h
   kubectl get nodes
   sudo systemctl status system-agent
   sudo systemctl status rke2-server
   ```

---

## Additional Resources

- **[RKE2 Documentation](https://docs.rke2.io/)** - Official RKE2 docs
- **[Rancher Documentation](https://rancher.com/docs/)** - Official Rancher docs
- **Infrastructure Team**: Internal storage configuration guide at `fleet-gitops/infrastructure/`

---

**Last Updated**: 2026-08-02  
**For**: KubeTEE Miners  
**Cluster Type**: RKE2 via Rancher  
**Storage**: Raw disk dedicated storage
