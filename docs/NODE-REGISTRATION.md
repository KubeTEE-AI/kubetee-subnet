# Node Registration to RKE2 Cluster

This guide is for **miners** who need to register their nodes to an RKE2 cluster managed by Rancher.

## Prerequisites

Before registering your node, ensure the infrastructure setup is complete:

1. ✅ **Kernel settings configured**
2. ✅ **Node meets minimum requirements**:
   - Ubuntu 26.04
   - etcd user/group created
   - Minimum resources: 8 CPU cores, 16 GB RAM
   - Minimum storage: 800 GB OS disk + 3 TB data disk
3. ✅ **Network connectivity** to Rancher management cluster
4. ✅ **GPU nodes** (optional): 
   - **CPU with TDX (Intel 5th/6th Gen) or SEV-SNP (AMD 4th/5th Gen)** - MANDATORY for GPU nodes
   - **Exactly 8x NVIDIA H100 or H200 GPUs with PPCIe mode** - MANDATORY for GPU nodes
   - **Latest firmware installed** - See [NVIDIA DGX Firmware Guide](https://docs.nvidia.com/dgx/dgxh100-fw-update-guide/)
   - VFIO/IOMMU configured for passthrough

## Miner Hotkey Label (Early Access scoring requirement)

The subnet validator finds your cluster through the
`kubetee.ai/miner-hotkey` **cluster label**, whose value is your miner
hotkey SS58. In Early Access this label is applied **by the KubeTEE
operator** as a manual step when your cluster is registered (registration
is operator-performed, not permissionless). A registered miner whose
cluster is missing the label — or whose label holds a stale hotkey — scores
**0** and earns no miner share; exactly one cluster may carry a given
hotkey value. See [SUBNET.md](../SUBNET.md) ("Manual cluster label step")
for the labeling procedure and the scoring rule.

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
- **OS Disk**: 800 GB minimum (for system, `/var/lib/longhorn/`, and OS overhead)
- **Data Disk**: 3 TB minimum (for `/data` - Longhorn additional storage)

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
curl -fL https://staging-rancher.kubetee.ai/system-agent-install.sh | sudo sh -s - \
  --server https://staging-rancher.kubetee.ai \
  --token <your-cluster-token> \
  --ca-checksum <checksum> \
  --address <public-ip-address> \
  --internal-address <local-network-ip> \
  --etcd --controlplane --worker

# OR Worker-only node (for scaling workloads)
curl -fL https://staging-rancher.kubetee.ai/system-agent-install.sh | sudo sh -s - \
  --server https://staging-rancher.kubetee.ai \
  --token <your-cluster-token> \
  --ca-checksum <checksum> \
  --address <public-ip-address> \
  --internal-address <local-network-ip> \
  --worker
```

**Important Network Flags**:
- `--address` - External/public IP address (used for external communication)
- `--internal-address` - Internal/private IP address (used for internal cluster communication)

These flags are **required** for proper node networking, especially in multi-network environments.

---

## Step 2: Run Registration Command

On your node, execute the registration command provided by the infrastructure team:

```bash
# Example registration command (use the actual command provided to you)
curl -fL https://staging-rancher.kubetee.ai/system-agent-install.sh | sudo sh -s - \
  --server https://staging-rancher.kubetee.ai \
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

## Step 4: Prepare Storage Disks for Longhorn

Longhorn is the distributed block storage system used in KubeTEE clusters. It requires properly mounted storage.

**IMPORTANT Storage Requirements**:
- **OS Disk**: **800 GB minimum** (contains `/var/lib/longhorn/`)
- **Data Disk**: **3 TB minimum** (mounted at `/data`)

### Default Storage: `/var/lib/longhorn/`

Longhorn uses `/var/lib/longhorn/` by default on the OS disk. 

**Ensure your OS disk has at least 800 GB total capacity** to accommodate:
- Operating system and applications
- Longhorn default storage
- System overhead and logs

### Additional Storage on `/data` (REQUIRED)

You **must** have a dedicated disk for `/data` with at least **3 TB** capacity.

**This is NOT optional** - KubeTEE clusters require the `/data` disk for adequate Longhorn volume storage, especially for:
- AI/ML model storage
- Training data and checkpoints
- Application persistent volumes
- Database storage

#### Option A: Automated Disk Setup (Recommended)

Use the provided Ansible playbook (infrastructure team):

```bash
# From the kubetee repository
cd ansible
ansible-playbook -i inventory.yaml prepare-longhorn-disks.yaml
```

#### Option B: Manual Disk Setup

If you prefer manual setup:

##### 1. Identify the Disk

```bash
# List all block devices
lsblk

# Expected output:
# NAME   MAJ:MIN RM  SIZE RO TYPE MOUNTPOINT
# sda      8:0    0  800G  0 disk 
# ├─sda1   8:1    0  799G  0 part /
# └─sda2   8:2    0    1G  0 part [SWAP]
# sdb      8:16   0  3.5T  0 disk  ← This is your data disk (min 3TB)
```

##### 2. Partition the Disk

```bash
# Use fdisk to partition
sudo fdisk /dev/sdb

# Interactive commands:
# n - new partition
# p - primary partition
# 1 - partition number 1
# <enter> - first sector (default)
# <enter> - last sector (use entire disk)
# w - write changes and exit
```

##### 3. Format the Partition

```bash
# Format with ext4 and add a label
sudo mkfs.ext4 -L longhorn-data /dev/sdb1

# Or use XFS for better performance
sudo mkfs.xfs -L longhorn-data /dev/sdb1
```

##### 4. Mount the Disk

```bash
# Create mount point
sudo mkdir -p /data

# Mount the partition
sudo mount /dev/sdb1 /data

# Verify mount
df -h /data
```

##### 5. Add to /etc/fstab for Persistence

```bash
# Get the UUID of the partition
sudo blkid /dev/sdb1

# Add to /etc/fstab
echo 'UUID=<your-uuid> /data ext4 defaults 0 2' | sudo tee -a /etc/fstab

# Or using device path (less reliable)
echo '/dev/sdb1 /data ext4 defaults 0 2' | sudo tee -a /etc/fstab

# Test fstab
sudo mount -a
df -h /data
```

##### 6. Set Permissions

```bash
# Longhorn will manage permissions, but you can set initial permissions
sudo chmod 755 /data
sudo chown root:root /data
```

### Verify Disk Setup

```bash
# Check mount
df -h /data

# Expected output (minimum 3 TB):
# Filesystem      Size  Used Avail Use% Mounted on
# /dev/sdb1       3.5T   77M  3.4T   1% /data

# Check in /etc/fstab
grep /data /etc/fstab
```

---

## Step 5: Configure Longhorn Disks (After Cluster Join)

After your node joins the cluster and Longhorn is deployed, the infrastructure team will configure Longhorn to use your disks.

### What Gets Configured

The infrastructure team will run a script that:
1. Labels your node: `node.longhorn.io/create-default-disk=config`
2. Annotates your node with disk configuration:
   - Default disk: `/var/lib/longhorn/` (always)
   - Additional disk: `/data` (if mounted)

### Disk Annotation Example

If you have `/data` mounted, the annotation will be:

```json
node.longhorn.io/default-disks-config: '[
  {
    "path": "/var/lib/longhorn",
    "allowScheduling": true,
    "storageReserved": 536870912000,
    "tags": ["default"]
  },
  {
    "name": "data-disk",
    "path": "/data",
    "allowScheduling": true,
    "storageReserved": 53687091200,
    "tags": ["fast", "nvme"]
  }
]'
```

**Note**: The infrastructure team handles this configuration automatically. You only need to ensure `/data` is properly mounted.

### Verify Longhorn Configuration

Once Longhorn is configured, verify from the management cluster:

```bash
# Check node labels
kubectl get nodes -o custom-columns=\
NAME:.metadata.name,\
DISK-LABEL:.metadata.labels.node\.longhorn\.io/create-default-disk

# Check Longhorn node status
kubectl get nodes.longhorn.io -n longhorn-system

# Describe your node
kubectl describe node.longhorn.io <your-node-name> -n longhorn-system
```

Or via Longhorn UI:
```bash
kubectl port-forward -n longhorn-system svc/longhorn-frontend 8080:80
# Open http://localhost:8080
# Navigate to: Node > Select your node > Disks
# Should show: /var/lib/longhorn and /data (if configured)
```

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
3. **GPU Model**: NVIDIA H100 or H200 (Hopper architecture)
4. **GPU Count**: Exactly 8 GPUs (all same model)
5. **Latest Firmware**: Updated per [NVIDIA DGX H100/H200 Firmware Update Guide](https://docs.nvidia.com/dgx/dgxh100-fw-update-guide/)
6. **GPU Mode**: PPCIe (Protected PCIe) enabled
7. **VFIO/IOMMU**: Enabled for GPU passthrough

**❌ NOT Supported:**
- Older CPUs (Intel 4th Gen, AMD 3rd Gen or earlier)
- Other GPU models (A100, V100, B200, etc.)
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
- ⏳ **NVIDIA B200 (Blackwell)** - Coming soon (not yet supported)

**Requirements**:
- **Exactly 8 GPUs per node** - No more, no less
- **PPCIe (Protected PCIe) mode enabled** - Required for confidential computing
- **All GPUs must be the same model** - No mixing H100/H200

**Examples of Valid Configurations**:
- ✅ 8x NVIDIA H100 80GB
- ✅ 8x NVIDIA H200 141GB
- ❌ 4x NVIDIA H100 (not enough GPUs)
- ❌ 8x NVIDIA A100 (wrong GPU model)
- ❌ 4x H100 + 4x H200 (mixed models)
- ❌ 8x NVIDIA B200 (not yet supported)

### GPU Workload Configuration Label

For GPU nodes that will run confidential VMs with GPU passthrough:

```bash
# Label the GPU node for VM passthrough mode
kubectl label node <your-node-name> nvidia.com/gpu.workload.config=vm-passthrough
```

**What this does**:
- Tells the GPU Operator (automatically installed via Fleet) to configure GPUs for VM passthrough mode
- Enables GPU access for confidential containers and VMs
- Required for Kata Containers with GPU support

**Note**: The GPU Operator is **automatically deployed by Fleet** - you don't need to install it. Just label your node.

### When to Use This Label

| Use Case | Label Required | CPU Requirement | GPU Requirement | Notes |
|----------|----------------|-----------------|-----------------|-------|
| **Confidential VMs with GPU** | ✅ Yes | TDX or SEV-SNP | 8x H100/H200 with PPCIe | `vm-passthrough` mode |
| **Standard containers with GPU** | ❌ Not Supported | N/A | N/A | KubeTEE requires TDX/SNP + H100/H200 |
| **Non-GPU workloads** | ❌ No | Any supported CPU | N/A | Regular workloads |

**Important**: 
- KubeTEE only accepts GPU nodes with Intel TDX or AMD SEV-SNP confidential computing support
- For AMD: **Only SEV-SNP is supported** (not older SEV or SEV-ES)
- GPU nodes MUST have exactly 8x NVIDIA H100 or H200 GPUs with PPCIe mode enabled

### Verification

```bash
# Check node labels
kubectl get node <your-node-name> --show-labels | grep gpu.workload.config

# Expected output:
# nvidia.com/gpu.workload.config=vm-passthrough

# Verify GPU Operator configuration
kubectl get nodes -o json | jq '.items[] | {name: .metadata.name, labels: .metadata.labels | to_entries | map(select(.key | contains("nvidia"))) | from_entries}'
```

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
- ❌ **NVIDIA B200 (Blackwell)** - Not yet supported (coming soon)
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
- ✅ **Verify exactly 8 NVIDIA H100 or H200 GPUs are installed** (MANDATORY)
- ✅ **Update to latest firmware** (MANDATORY) - [NVIDIA DGX H100/H200 Firmware Update Guide](https://docs.nvidia.com/dgx/dgxh100-fw-update-guide/)
- ✅ **Enable PPCIe (Protected PCIe) mode on all GPUs** (MANDATORY)
- ✅ Enable VFIO/IOMMU in BIOS and kernel
- ✅ Label the node after registration

**⚠️ CRITICAL**: 
- Older CPU generations (Intel 4th Gen Xeon, AMD 3rd Gen EPYC or earlier) are NOT supported
- Only H100/H200 GPUs with PPCIe mode are supported
- Nodes MUST have exactly 8 GPUs (no more, no less)
- Latest firmware MUST be installed before registration

### Multiple GPU Nodes

Label all GPU nodes that meet the requirements:

```bash
# Each GPU node with 8x H100 or H200 (with TDX/SNP CPU)
kubectl label node gpu-node-01 nvidia.com/gpu.workload.config=vm-passthrough
kubectl label node gpu-node-02 nvidia.com/gpu.workload.config=vm-passthrough
kubectl label node gpu-node-03 nvidia.com/gpu.workload.config=vm-passthrough

# Do NOT label nodes that don't meet ALL requirements:
# - Wrong CPU generation
# - Wrong GPU model (not H100/H200)
# - Wrong GPU count (not exactly 8)
# - PPCIe mode not enabled
```

### Removing the Label

If you need to change the GPU workload configuration:

```bash
# Remove the label
kubectl label node <your-node-name> nvidia.com/gpu.workload.config-

# The GPU Operator will reconfigure the GPUs to default mode
```

**Note**: After removing or changing the label, GPU pods may need to be restarted for the new configuration to take effect.

### GPU Operator - Automatic Installation

**Important**: You do NOT need to install the GPU Operator manually. It is **automatically deployed by Fleet/GitOps** to all clusters.

**What happens automatically**:
1. ✅ GPU Operator is deployed by the infrastructure team via Fleet
2. ✅ NVIDIA drivers are automatically installed on GPU nodes
3. ✅ GPU Operator detects the `vm-passthrough` label and configures GPUs accordingly
4. ✅ All GPU resources are automatically configured

**Your only action**: Label your GPU nodes with `nvidia.com/gpu.workload.config=vm-passthrough`

**To verify GPU Operator is running** (optional):
```bash
# Check if GPU Operator pods are running
kubectl get pods -n gpu-operator-system

# Expected output:
# gpu-operator-xxx          1/1     Running
# nvidia-driver-daemonset   1/1     Running  (on GPU nodes)
# nvidia-device-plugin      1/1     Running  (on GPU nodes)
```

If GPU Operator is not installed or not working, contact the infrastructure team.

---

## Step 7: Verify Deployment

After registration and Longhorn configuration, verify everything is working:

### Check Node Status

```bash
# Check if node is Ready
kubectl get nodes

# Check node details
kubectl describe node <your-node-name>

# Check node labels
kubectl get node <your-node-name> --show-labels
```

### Check Longhorn Storage

```bash
# Check Longhorn pods on your node
kubectl get pods -n longhorn-system -o wide | grep <your-node-name>

# Check Longhorn node disks
kubectl get nodes.longhorn.io -n longhorn-system <your-node-name> -o yaml
```

### Test Volume Creation

Create a test PVC to verify storage is working:

```bash
kubectl apply -f - <<EOF
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: test-pvc
  namespace: default
spec:
  accessModes:
    - ReadWriteOnce
  storageClassName: longhorn
  resources:
    requests:
      storage: 1Gi
EOF

# Check PVC status
kubectl get pvc test-pvc

# Should show STATUS: Bound

# Cleanup
kubectl delete pvc test-pvc
```

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
curl -fL https://staging-rancher.kubetee.ai/system-agent-install.sh | sudo sh -s - \
  --server https://staging-rancher.kubetee.ai \
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
# 8472/udp - Flannel VXLAN (if using Flannel)
# 4789/udp - Calico VXLAN (if using Calico)
```

### Longhorn Disk Not Recognized

**Problem**: `/data` disk not showing in Longhorn

**Solutions**:
```bash
# Verify /data is mounted
df -h /data

# Check disk permissions
ls -la /data

# Check node annotation
kubectl describe node <your-node-name> | grep -A 20 "node.longhorn.io/default-disks-config"

# If annotation is missing, contact infrastructure team
```

### Storage Permission Issues

**Problem**: Longhorn can't write to `/data`

**Solutions**:
```bash
# Check permissions
ls -la /data

# Fix permissions (Longhorn needs root access)
sudo chown root:root /data
sudo chmod 755 /data

# Check SELinux/AppArmor (if enabled)
sudo getenforce  # SELinux
sudo aa-status   # AppArmor

# Restart Longhorn manager
kubectl rollout restart daemonset/longhorn-manager -n longhorn-system
```

### Disk Full Issues

**Problem**: Longhorn reports disk full

**Solutions**:
```bash
# Check actual disk usage
df -h /var/lib/longhorn
df -h /data

# Check Longhorn disk settings
kubectl get nodes.longhorn.io -n longhorn-system <node-name> -o yaml

# Clean up unused volumes
# Via Longhorn UI: Navigate to Volume > Select unused volumes > Delete

# Adjust storage reserved percentage (contact infrastructure team)
```

---

## Storage Configuration Reference

### Disk Paths

| Path | Purpose | Required | Minimum Size | Recommended Size |
|------|---------|----------|--------------|------------------|
| `/` (OS Disk) | System + `/var/lib/longhorn/` | ✅ Yes | **800 GB** | 1 TB+ |
| `/data` | Additional Longhorn storage | ✅ **Required** | **3 TB** | 5 TB - 10 TB+ |

### Storage Reserved

The infrastructure team configures `storageReserved` (in **bytes**, not percentage) to prevent disks from filling completely:

- **OS Disk** (`/var/lib/longhorn/`): 500 GB reserved = `536870912000` bytes (~62.5% of 800GB)
- **Data Disk** (`/data`): 50 GB reserved = `53687091200` bytes (~1.6% of 3TB)

**Note**: Longhorn uses **absolute values in bytes** for per-disk reservation. The value represents how much space to keep free on each disk.

**Why reserve space on OS disk?**
- OS disk (800 GB) reserves 500 GB, leaving ~300 GB usable for Longhorn
- This ensures the OS disk doesn't fill up from Longhorn volumes
- Primary storage should be on the `/data` disk (3 TB)
- Prevents system instability from full OS disk
- Recommended: Reserve majority of OS disk to keep Longhorn volumes on `/data`

### Disk Tags

Tags help Longhorn schedule replicas on appropriate disks:

| Tag | Meaning | Used For |
|-----|---------|----------|
| `default` | Default disk | General workloads |
| `fast` | Fast storage | Performance-critical volumes |
| `nvme` | NVMe SSD | High-performance workloads |
| `ssd` | SSD storage | Better than HDD performance |
| `hdd` | HDD storage | Cost-effective bulk storage |

---

## Cloud Provider Specific Notes

### AWS EC2

```bash
# Attach EBS volume
aws ec2 attach-volume \
  --volume-id vol-xxxxxxxxx \
  --instance-id i-xxxxxxxxx \
  --device /dev/sdf

# Wait for volume to attach
# Then follow manual disk setup steps above
```

### GCP Compute Engine

```bash
# Attach persistent disk
gcloud compute instances attach-disk INSTANCE_NAME \
  --disk DISK_NAME \
  --device-name longhorn-data

# Follow manual disk setup steps above
```

### Azure VMs

```bash
# Attach managed disk
az vm disk attach \
  --resource-group myResourceGroup \
  --vm-name myVM \
  --name myDataDisk

# Follow manual disk setup steps above
```

### Bare Metal / On-Premise

- Ensure disk is physically installed
- Verify BIOS/UEFI detects the disk
- Follow manual disk setup steps above

---

## Best Practices

### Storage

1. **Use dedicated disks** for `/data` (not partitions of the OS disk)
2. **XFS or ext4** filesystems (XFS preferred for performance)
3. **Label disks** for easier identification: `sudo mkfs.ext4 -L longhorn-data /dev/sdX1`
4. **Monitor disk health** using SMART tools:
   ```bash
   sudo apt install smartmontools
   sudo smartctl -a /dev/sdb
   ```

### Networking

1. **Ensure low latency** between nodes (<10ms for best performance)
2. **Use private networks** for inter-node communication
3. **Open required ports** (RKE2, Longhorn, monitoring)

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

2. **Monitor Longhorn metrics** via Prometheus/Grafana (provided by infrastructure team)

3. **Set up alerts** for disk space, node health, pod failures

---

## Quick Reference Commands

### Registration
```bash
# Find your IPs
curl -4 ifconfig.me                          # Public IP
hostname -I | awk '{print $1}'               # Private IP

# Register all-in-one node (first 3+ nodes)
curl -fL https://staging-rancher.kubetee.ai/system-agent-install.sh | sudo sh -s - \
  --server https://staging-rancher.kubetee.ai \
  --token <token> \
  --ca-checksum <checksum> \
  --address <public-ip> \
  --internal-address <private-ip> \
  --etcd --controlplane --worker

# Register worker-only node (additional nodes)
curl -fL https://staging-rancher.kubetee.ai/system-agent-install.sh | sudo sh -s - \
  --server https://staging-rancher.kubetee.ai \
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

# Check Longhorn disks
kubectl get nodes.longhorn.io -n longhorn-system
kubectl describe node.longhorn.io <node-name> -n longhorn-system

# Check disk mounts
df -h
lsblk
df -h /data

# Check Longhorn pods
kubectl get pods -n longhorn-system -o wide

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
   kubectl get nodes.longhorn.io -n longhorn-system
   sudo systemctl status system-agent
   sudo systemctl status rke2-server
   ```

---

## Additional Resources

- **[Longhorn Documentation](https://longhorn.io/docs/)** - Official Longhorn docs
- **[RKE2 Documentation](https://docs.rke2.io/)** - Official RKE2 docs
- **[Rancher Documentation](https://rancher.com/docs/)** - Official Rancher docs
- **Infrastructure Team**: Longhorn configuration guide at `fleet-gitops/infrastructure/longhorn/CONFIGURE-DATA-DISK.md`

---

**Last Updated**: 2025-10-29  
**For**: KubeTEE Miners  
**Cluster Type**: RKE2 via Rancher  
**Storage**: Longhorn with multi-disk support

