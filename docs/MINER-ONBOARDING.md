# Miner Node Onboarding

> **Status:** DRAFT — pending review. Not yet merged or deployed.
> **Applies to:** miner production clusters.

This guide covers the complete node-onboarding workflow: the miner prepares hardware, BIOS, a clean OS installation, storage, and access; KubeTEE performs host preparation and RKE2 registration.

**Miner responsibilities:** supported hardware, GPU/VBIOS firmware, BIOS configuration, plain Ubuntu 26.04 LTS, storage baseline, `ubuntu` SSH access, and remote power recovery.

**KubeTEE responsibilities:** OS hardening and updates, kernel selection, TDX/SGX services, PCK registration, storage formatting, GPU CC mode and drivers, VFIO host configuration, GPU Operator deployment, and RKE2 registration.

Do not run registration commands, edit platform labels, or manually install host services unless KubeTEE explicitly asks you to do so.

---

## 1. Operational ownership

The operator provides the hardware and a clean OS installation. KubeTEE automation performs the remaining host preparation.

| Layer | Required state at handoff |
|---|---|
| Compute | At least **128 CPU cores and 2 TB RAM per active node** |
| BIOS | TDX + SGX enabled, compatible performance profile, SGX auto-registration **disabled** |
| GPUs | Supported hardware with miner-updated and validated GPU/VBIOS firmware; KubeTEE handles CC mode and drivers |
| OS | Plain Ubuntu 26.04 LTS with no NVIDIA drivers or other NVIDIA software installed |
| Storage | OS disk with **>784 GB** of usable capacity; unformatted data drives, each **>3.84 TB**, totaling **>7 TB** |
| Access | SSH as `ubuntu` with the KubeTEE public key and passwordless `sudo`; remote cold-reboot capability through Redfish, IPMI, or a power-management API |

KubeTEE automation owns OS hardening and package updates, security hardening, kernel selection and parameters, TDX/SGX software and services, PCK registration, storage formatting and mounts, VFIO/GPU host configuration, GPU CC mode, and the components required by the GPU Operator.

Do not install kernel updates, edit kernel boot parameters, configure PCCS/QGS/AESM, install NVIDIA drivers or CUDA, bind GPUs to `vfio-pci`, or create RAID devices, filesystems, or mounts on the data drives. KubeTEE configures and verifies these during automated preparation.

## 2. Hardware and GPU firmware

- A supported server with 8 identical NVIDIA GPUs per [GPU-NODE-REQUIREMENTS.md](GPU-NODE-REQUIREMENTS.md)
- At least **128 CPU cores and 2 TB RAM per active node**
- Intel Xeon 6th Gen with TDX support (Granite Rapids) — 5th Gen (Emerald Rapids) is DEPRECATED (existing nodes only)
- Three nodes of the same GPU type per cluster for high availability; see [GPU-NODE-REQUIREMENTS.md](GPU-NODE-REQUIREMENTS.md)
- Co-locate all nodes in one data center and provide connectivity to the Rancher management endpoint and addresses KubeTEE can reach for onboarding
- OS disk: **>784 GB** of usable capacity
- Data drives: **each >3.84 TB**, with **>7 TB total raw capacity**
- Remote cold-reboot capability for KubeTEE; Redfish access is preferred but optional when another method is available

Before handoff, the miner must update and validate GPU firmware and VBIOS using the OEM/HGX or DGX procedure appropriate to the server. Confirm that all GPUs and their VBIOS are at the required versions and meet the compatibility requirements in [GPU-NODE-REQUIREMENTS.md](GPU-NODE-REQUIREMENTS.md).

Where the compatibility matrix includes CC mode, treat that as a firmware-compatibility check only: **the miner must not change CC mode or install NVIDIA drivers.** KubeTEE handles these during automated preparation.

## 3. BIOS configuration (TDX + SGX)

The BIOS must be configured in **dependency order** — some attributes are gated behind others and cannot be applied in one pass. Apply the following set (Dell attribute names):

**Phase 1 — base performance / platform attributes:**

| Attribute | Value |
|---|---|
| `SysProfile` | `PerfOptimized` |
| `NodeInterleave` | `Disabled` |
| `ProcX2Apic` | `Enabled` |
| `CpuPaLimit` | `Disabled` |
| `IntelTxt` | `Off` |
| `TpmSecurity` | `On` |
| `EnergyPerformanceBias` | `MaxPower` |

**Phase 2 — TDX base:**

| Attribute | Value |
|---|---|
| `MemoryEncryption` | `MultipleKeys` |
| `EnableTdx` | `Enabled` |
| `KeySplit` | `1` |
| `EnableTdxSeamldr` | `Enabled` |
| `IntelSgx` | `On` |

**Phase 3 — TME dependency + SGX:**

| Attribute | Value |
|---|---|
| `GlbMemIntegrity` | `Disabled` |
| `PrmrrSize` | `2G` |
| `SgxAutoRegistrationAgent` | **`Disabled`** — see the warning below |
| `SgxPackageInfoInBandAccess` | `On` |

**Order matters:** `NodeInterleave=Disabled` + `ProcX2Apic=Enabled` + `CpuPaLimit=Disabled` must be active before the TDX attributes can be set; `MemoryEncryption=MultipleKeys` must be active before `GlbMemIntegrity` can be changed; `IntelSgx=On` must be active before `PrmrrSize` can be changed. A reboot is required between phases; re-query the attribute list after each reboot to confirm persistence (some BMCs drop attributes after a reboot — see [BIOS recovery guidance](#bios-recovery-guidance)).

### 3.1 SGX auto-registration must stay disabled

**Never enable firmware SGX auto-registration** (Dell `SgxAutoRegistrationAgent`; equivalent settings on other OEMs). Enabling it consumes the multi-package platform manifest at POST and prevents KubeTEE's automated in-band PCK registration.

KubeTEE registers the platform in-band after OS handoff. If firmware auto-registration has already consumed the manifest, report it to KubeTEE; do not perform an SGX factory reset yourself.

---

## 4. Plain OS installation

Install a **plain Ubuntu 26.04 LTS** system:

- **Do not install NVIDIA drivers, CUDA, or any other NVIDIA software.** KubeTEE automation and the GPU Operator manage the GPU software stack.
- Leave OS hardening, package upgrades, kernel selection, and kernel parameters to KubeTEE automation. Do not apply a custom kernel, custom boot parameters, or a third-party hardening profile before handoff.
- The stock Ubuntu kernel is sufficient at handoff. KubeTEE selects and pins the supported kernel during automated preparation.
- Install the OS on a disk with **>784 GB of usable capacity**. Do not place the data drives in the OS LVM volume group.
- Use the existing `ubuntu` user for KubeTEE SSH access. Root SSH access is not used. Follow [Grant KubeTEE SSH access](#6-grant-kubetee-ssh-access) below.

```bash
lsb_release -ds
# Ubuntu 26.04 LTS

command -v nvidia-smi || echo "PASS: no NVIDIA driver installed"
# PASS: no NVIDIA driver installed
```

## 5. Storage and remote power access

### 5.1 Data-drive requirements

All of the following are required per GPU node:

| Requirement | Value |
|---|---|
| OS disk usable capacity | **>784 GB** |
| Capacity of each data drive | **>3.84 TB** |
| Combined raw data capacity | **>7 TB** |
| Data-drive state | **Unformatted, unpartitioned, and unmounted** |

For example, two 4 TB data drives meet the per-drive requirement and provide 8 TB of raw capacity. If providing multiple data drives, use identical drives. Raw capacity means unformatted capacity, not the smaller usable capacity after KubeTEE creates its storage layout.

Leave every data drive completely free of partitions, filesystems, RAID signatures, LVM metadata, mounts, and disk labels. **Do not run `fdisk`, `parted`, `mkfs`, `mdadm`, or add the data drives to `/etc/fstab`.** KubeTEE automation creates and validates the storage layout during onboarding.

Before handoff, check:

```bash
lsblk -o NAME,SIZE,TYPE,FSTYPE,MOUNTPOINTS,MODEL
findmnt
```

Each intended data drive must appear as a disk larger than 3.84 TB with blank `FSTYPE` and `MOUNTPOINTS` fields and no child partitions. Add the raw capacities of those disks and confirm the total exceeds 7 TB. Do not include the OS disk in this total.

### 5.2 Remote power management

KubeTEE needs a way to cold-reboot the node if automated preparation or recovery cannot proceed over SSH.

- **Redfish access to the BMC is preferred but optional.** For Dell systems this is typically iDRAC Redfish; equivalent vendor implementations are also suitable.
- If Redfish is unavailable, provide reachable **IPMI** access or a **power-management API** capable of power-on, power-off, and cold-reboot operations.
- Provide the chosen endpoint and its credentials securely to the KubeTEE onboarding operator, never through Git.
- If you cannot provide any of these methods, a wedged node will not earn incentives until rebooted and ready.

## 6. Grant KubeTEE SSH access

Use the existing `ubuntu` user for KubeTEE onboarding; **root SSH access is not used**. Add only the KubeTEE SSH public key, supplied through a secure channel, to `/home/ubuntu/.ssh/authorized_keys`. Do not create another onboarding account or add unrelated SSH keys for KubeTEE.

As the `ubuntu` user, validate and append the KubeTEE public key, then configure passwordless `sudo` for unattended host preparation:

```bash
export KUBETEE_SSH_PUBLIC_KEY='<SSH-PUBLIC-KEY-PROVIDED-BY-KUBETEE>'
printf '%s\n' "$KUBETEE_SSH_PUBLIC_KEY" | ssh-keygen -l -f -
install -d -m 700 -o ubuntu -g ubuntu /home/ubuntu/.ssh
touch /home/ubuntu/.ssh/authorized_keys
chown ubuntu:ubuntu /home/ubuntu/.ssh/authorized_keys
chmod 600 /home/ubuntu/.ssh/authorized_keys
printf '%s\n' "$KUBETEE_SSH_PUBLIC_KEY" >> /home/ubuntu/.ssh/authorized_keys

printf 'ubuntu ALL=(ALL) NOPASSWD:ALL\n' | sudo visudo -cf /dev/stdin >/dev/null
printf 'ubuntu ALL=(root) NOPASSWD:ALL\n' | sudo tee /etc/sudoers.d/90-kubetee-ubuntu >/dev/null
sudo visudo -cf /etc/sudoers.d/90-kubetee-ubuntu >/dev/null
sudo chmod 0440 /etc/sudoers.d/90-kubetee-ubuntu
sudo -n true
```

`ssh-keygen -l -f -` must print the key fingerprint successfully, and `sudo -n true` must return without a password prompt before handoff. Replace the key placeholder with the complete KubeTEE public key. Keep the sudoers rule available while KubeTEE manages the node; do not change it without coordinating with KubeTEE.

The SSH key command preserves existing `ubuntu`-user keys that you already manage. Add only KubeTEE's key for this onboarding workflow.

## 7. Miner deposit

Every miner posts a **10 TAO per node deposit** as on-chain registration collateral on the mining hotkey (for example, 30 TAO for a three-node cluster) — see [Miner Deposit (Registration Collateral)](MINER-DEPOSIT.md).

**Status:** not collected during Early Access; this is a Phase 1 requirement.

When in effect, the deposit stays on your own hotkey. KubeTEE never holds it and cannot move it, and it is released back to withdrawable stake as the hotkey earns emission. A hotkey below the requirement is scored 0 after a grace window, which stops emission and therefore freezes the deposit until you top up. Nothing is confiscated, and the freeze reverses when you return to compliance.

## 8. Pre-handoff checklist

Before handing the node to KubeTEE, confirm:

- [ ] Supported hardware with 8 identical GPUs per [GPU-NODE-REQUIREMENTS.md](GPU-NODE-REQUIREMENTS.md)
- [ ] Each active node has at least **128 CPU cores and 2 TB RAM**
- [ ] Three-node, same-GPU-type topology for high availability; all nodes are co-located
- [ ] Intel 6th Gen Xeon with TDX support; BIOS TDX and SGX enabled
- [ ] BIOS `SgxAutoRegistrationAgent` = **Disabled** (verified in iDRAC/BMC)
- [ ] GPU firmware and VBIOS have been updated and validated against [GPU-NODE-REQUIREMENTS.md](GPU-NODE-REQUIREMENTS.md)
- [ ] CC mode has not been changed by the miner; no NVIDIA drivers or other NVIDIA software is installed
- [ ] Plain Ubuntu 26.04 LTS is installed with the stock kernel
- [ ] No manual kernel tuning, TDX/SGX services, VFIO bindings, or custom hardening applied
- [ ] OS disk has >784 GB of usable capacity
- [ ] Every data drive is >3.84 TB and unformatted, unpartitioned, and unmounted
- [ ] Total raw data-drive capacity is >7 TB
- [ ] The KubeTEE public key is installed for `ubuntu`, and passwordless `sudo` works
- [ ] Remote cold-reboot access has been arranged: Redfish preferred, or IPMI / an equivalent power-management API

## 9. KubeTEE prepares and registers the node

**Until permissionless onboarding is fully tested and deployed**, KubeTEE performs automated host preparation and RKE2 registration on your behalf.

KubeTEE automation connects as `ubuntu` and uses passwordless `sudo` to harden and update Ubuntu, configure the kernel and TDX/SGX services, prepare storage, and configure GPUs and VFIO.

Do not modify the node while automated preparation or registration is running. KubeTEE manages OS hardening, storage, GPU configuration, registration, monitoring, and workload services.

KubeTEE then performs RKE2 registration and platform enrollment. Wait for confirmation before assuming the node is ready for workloads.

Keep SSH and remote power access available. Do not run registration commands, manually restart services, add node labels, or change GPU or host configuration. Coordinate maintenance through KubeTEE.

## 10. Getting help

Before contacting KubeTEE, review the [pre-handoff checklist](#8-pre-handoff-checklist), SSH key fingerprint, and `sudo` checks above.

For onboarding or node issues, provide:

- Node name and cluster name
- Ubuntu version and hardware configuration
- Disk capacity, partition, and mount output
- SSH key fingerprint output and the result of the `sudo` check
- Error messages and diagnostic output requested by KubeTEE

Do not run registration or service commands to work around stalled onboarding. Contact KubeTEE before changing prepared nodes or access settings.

## BIOS recovery guidance

- **iDRAC drops SGX attribute keys after a BIOS reboot:** use a BMC-only `GracefulRestart` of the iDRAC management controller, not another host reboot. Re-check all BIOS attributes afterward.
- **Consumed SGX platform manifest:** this results from enabling firmware auto-registration and blocks in-band PCK registration. Report the condition to KubeTEE rather than performing a factory reset yourself; recovery requires a controlled, one-node-at-a-time procedure.
- **An attribute fails to persist:** inspect the iDRAC Lifecycle Logs and verify the host's Redfish system (`System.Embedded.1`), never the NVIDIA `HGX_Baseboard_0` GPU tray.

## Additional resources

- **[GPU Node Requirements](GPU-NODE-REQUIREMENTS.md)** — supported hardware and firmware
- **[KubeTEE Miner Deposit](MINER-DEPOSIT.md)** — registration-collateral requirements and status
- **[RKE2 Documentation](https://docs.rke2.io/)** — official RKE2 documentation
- **[Rancher Documentation](https://rancher.com/docs/)** — official Rancher documentation

**Last Updated:** 2026-11-08

**For:** KubeTEE Miners

**Cluster Type:** RKE2 via Rancher

**Storage:** KubeTEE-managed storage preparation
