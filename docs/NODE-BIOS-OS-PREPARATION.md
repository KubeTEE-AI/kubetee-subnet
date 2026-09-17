# Node BIOS & OS Preparation (Pre-Registration)

> **Status:** DRAFT — pending review. Not yet merged or deployed.
> **Applies to:** miner production clusters (first: `na-us-michigan-97` — **BTLABS, UID 97**, the first KubeTEE production miner; onboarding complete 2026-09-14).

This document describes how to prepare the **BIOS and OS** of nodes that will join a KubeTEE production cluster, up to the point where [NODE-REGISTRATION.md](NODE-REGISTRATION.md) takes over (RKE2 node registration). It is a procedure description, not a script — KubeTEE operators automate these steps with Ansible, but miners following this document manually achieve the same result.

**Audience:** node operators preparing hardware for a production cluster registration.

---

## 0. Scope and outcome

After completing this document, each node has:

| Layer | End state |
|---|---|
| BIOS | TDX + SGX enabled and active, PPCIe-compatible perf profile, SGX auto-registration **disabled** |
| Firmware / TDX module | Intel TDX module loaded at boot (SEAM loader init OK), PCK registered in-band |
| OS | Ubuntu 26.04 LTS, kernel `7.0.0-3x-generic` pin, clean of any NVIDIA stack |
| Kernel params | `kvm_intel.tdx=1`, IOMMU/VFIO on, no hibernate |
| Services | PCCS + QGS + AESM running, QGS in Unix-domain-socket mode |
| Storage | RAID0 across data NVMe, split raw (Longhorn V2) + XFS (Kata direct volumes) |
| GPUs | Bound to `vfio-pci`, no host `nvidia-smi` (expected) |

A node in this state is ready to receive the RKE2 registration command.

---

## 1. Hardware baseline

- Dell PowerEdge XE9680, 8× NVIDIA H100 SXM5 80GB (or H200/B200/B300 per [GPU-NODE-REQUIREMENTS.md](GPU-NODE-REQUIREMENTS.md))
- Intel Xeon 5th/6th Gen with TDX support (Emerald/Granite Rapids)
- OS disk: ≥1.92 TB mirrored (RAID 1)
- Data disks: ≥14 TB raw block across NVMe, no filesystem
- BMC (iDRAC) reachable over Redfish; credentials on hand

Verify the platform before starting:

```bash
lscpu | grep -i "Model name"   # Xeon 5xxx/6xxx (Emerald/Granite Rapids)
lspci -nn | grep -i nvidia     # 8× [10de:2330]/[10de:2331] 3D controllers
```

> GPU VBIOS/CC-mode compatibility: consult the [NVIDIA Trusted Computing Solutions — Secure AI Compatibility Matrix](https://docs.nvidia.com/nvtrust/index.html#guides) before labeling nodes (PPCIe mode for Hopper, per the matrix).

---

## 2. BIOS configuration (TDX + SGX)

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
| `SgxAutoRegistrationAgent` | **`Disabled`** — see warning below |
| `SgxPackageInfoInBandAccess` | `On` |

**Order matters:** `NodeInterleave=Disabled` + `ProcX2Apic=Enabled` + `CpuPaLimit=Disabled` must be active before the TDX attributes can be set; `MemoryEncryption=MultipleKeys` must be active before `GlbMemIntegrity` can be changed; `IntelSgx=On` must be active before `PrmrrSize` can be changed. A reboot is required between phases; re-query the attribute list after each reboot to confirm persistence (some BMCs drop attributes after a reboot — see §2.1).

### ⚠️ SGX auto-registration MUST stay Disabled

**Never enable firmware SGX auto-registration (Dell `SgxAutoRegistrationAgent`).** Enabling it consumes the multi-package platform manifest at POST, leaving the node permanently unable to register its PCK certificates: `mpa_manage` reports "Registration process completed successfully", but `PCKIDRetrievalTool` prints "platform manifest is not available" (often with rc=0), local PCCS shows `platforms=0` / `pck_cert=0`, QGS returns 404 on `/pckcert`, and TDX guests attest with an **empty quote** (Trustee 401). This is not a sandbox mismatch — Intel PCS production is behaving as designed; the manifest is simply consumed.

Recovery from a consumed manifest requires a per-host SGX factory reset (one node at a time) — avoid entirely by keeping the agent **Disabled** on every OEM (Dell, AIVRES, Supermicro, ASRockRack). Fill PCCS **in-band** instead (§4.3).

### 2.1 iDRAC quirks

- **Attribute list drop after reboot:** on some iDRACs (observed once in the field), the SGX attribute keys (`IntelSgx`, `PrmrrSize`, `SgxAutoRegistrationAgent`, `SgxPackageInfoInBandAccess`) disappear from the Redfish attribute list after a BIOS reboot. Fix: a **BMC-only `GracefulRestart` of the iDRAC management controller** (not a host reboot) repopulates the list. Re-verify the full attribute set after the restart.
- Always verify against the **host** Redfish system (`System.Embedded.1`), never the NVIDIA `HGX_Baseboard_0` GPU tray.
- iDRAC Lifecycle Logs are the first place to look when an attribute fails to apply.

---

### 2.2 GPU mode (PPCIe / CC mode)

Set Confidential Computing mode per the GPU generation:

- **Hopper (H100/H200):** PPCIe mode — set via `nvidia_gpu_tools.py --set-ppcie-mode` with `--reset-after-ppcie-mode-switch`, or via the NVIDIA nvtrust host tools. This is the mode the KubeTEE runtime classes expect on Hopper.
- **Blackwell (B200/B300):** native CC mode (`on`).
- Confirm the chosen VBIOS + CC mode combination is listed in the NVIDIA Secure AI Compatibility Matrix.

> In practice on KubeTEE clusters, CC mode is set by the GPU Operator's cc-manager after node join, reading the `nvidia.com/cc.mode` node label. Manual pre-join PPCIe setting is still recommended to validate the firmware accepts the mode.

---

## 3. OS installation

Install Ubuntu 26.04 LTS clean:

- **No pre-existing NVIDIA software** — the GPU Operator installs the entire GPU stack after node join; a pre-existing install conflicts with what it deploys. `which nvidia-smi` must return "not found" before registration.
- OS disk mirrored RAID 1, ≥1.92 TB.
- etcd user/group created (required by RKE2 etcd).
- Kernel pin: `7.0.0-31-generic` (Ubuntu 26.04 pin; `-27` or newer still works, do not drift onto `-28`/`-30` without the pin). KubeTEE operators currently deploy `7.0.0-38-generic` via `resolute-proposed` with an apt pin — the pin is what matters, the exact patch number is operator choice.

```bash
lsb_release -ds   # Ubuntu 26.04 LTS
uname -r         # 7.0.0-31-generic (pin) or newer
which nvidia-smi # not found — clean baseline
```

---

## 4. OS configuration (TDX/SGX stack)

This section describes the target state; operators automate with `site-2604.yaml`. The result should be verified per the checklist at the end.

### 4.1 Kernel and bootloader

- `kvm_intel.tdx=1` and `nohibernate` on the kernel command line (via a GRUB drop-in, not inline `GRUB_CMDLINE_LINUX` — avoid duplication).
- IOMMU enabled for the GPU passthrough: VT-d active (BIOS `snoop control` etc. is fine, Intel-VIOMMU activated by default on these kernels).
- Install the **Intel TDX module** (SEAM) — 2.0.18 for Xeon 6th Gen (Granite Rapids), 1.5.34 for 5th Gen (Emerald Rapids) — into `/boot/efi/EFI/TDX/TDX-SEAM.so` **and** `/lib/firmware/intel/tdx/` (kernel 7.0+ `request_firmware` path). One boot after install, verify:

```bash
journalctl -k -b --no-pager | grep -i tdx
# virt/tdx: module initialized   <- SEAM loader up
dmesg | grep -i tdx               # KeyID [32,64) allocated, PAMT allocation lines
```

### 4.2 SGX services

Install the Intel DCAP stack: `sgx-dcap-pccs` (local PCCS), `sgx-dcap-default-qpls`, `sgx-dcap-qpl-effective`, QGS (`qgsd`), AESM (`aesmd`).

**PCCS configuration:**

- The local PCCS fetches platform certs from Intel PCS (`api.trustedservices.intel.com`, production).
- **In-band registration only** (§2 warning): after services are up, run `PCKIDRetrievalTool -tcb_update_type standard` **from the host**. Success looks like:

```
Platform  --- Registration --- succeeded ---
pckid_retrieval_tool ..... completed successfully
Database connection established
PCK ID retrieval started
  processors retrieved: 1
  pck_cert: 8, pck_crl: 0
```

- QGS must run in **Unix-domain-socket mode** (comment out the `port` in `qgs.conf` so qgsd serves `/var/run/tdx-qgs/qgs.socket`) — this is the preparation the Kata guest expects (vsock → UDS bridge). TCP mode widens the DoS surface against qgsd and is not used on KubeTEE clusters.
- TCB update type `standard` matches the Trustee verifier configuration (TCB-R 20 channel). Do not use `early` unless the Trustee `dcap_verifier.tcb_update_type` is flipped to match (TCB-R 22, `standard` on 2027-08-11).


### 4.3 PCK registration verification

Verify from the host:

```bash
# pccs local db: platform and PCK cert counts
sqlite3 /opt/intel/sgx-dcap-pccs/pckcache.db 'select count(*) from PCKCertificate;'
# expect >= 8 (platforms=1, pck_cert=8 on a dual-socket XE9680)

# QGS responds on the socket
curl -s --unix-socket /var/run/tdx-qgs/qgs.socket http://localhost/pc
```

> A node with `platforms=0` / `pck_cert=0` after in-band registration has a consumed manifest or unreachable Intel PCS — do not proceed.

---

## 5. Storage layout (kata=true profile)

KubeTEE GPU nodes run a dual storage stack on the data NVMe:

1. **RAID0** across the data NVMe devices (e.g. 6× NVMe → `md1`), no filesystem.
2. **Partition** the RAID device into two:
   - `md1p1` (~20%, raw block) — Longhorn V2 SPDK data engine (AIO bdev) + udev stable symlink
   - `md1p2` (~80%, XFS, mounted at `/var/lib/kata-direct-volumes`) — Kata CSI Direct Volume backing files

```bash
lsblk /dev/md1
# md1p1  raw block, no fs  -> Longhorn V2 (registered post-join by the longhorn-disk-annotator)
# md1p2  xfs /var/lib/kata-direct-volumes -> kata direct volumes
```

On the first miner cluster's 4× H100 nodes the split is **md1p1 1 TB raw + md1p2 4.2 TB XFS**.

Kernel modules loaded at boot: `vfio_pci`, `uio_pci_generic`, `nvme_tcp`, plus 2 GiB hugepages for SPDK (`nr_hugepages=1024`).

> `/data` is NOT mounted on nodes with this layout — do not create or mount a `/data` filesystem.

---

## 5.1 GPU/VFIO state at handoff

At handoff to registration, GPUs are bound to `vfio-pci`:

```bash
lspci -nnk -d 10de:  # kernel driver in use: vfio-pci
```

Host `nvidia-smi` shows nothing (no host driver by design on CC nodes). This is **expected** — the in-guest driver is provided inside the Kata VM. Do not install host drivers to "fix" this.

---

## 6. Pre-flight checklist (all nodes)

Before requesting the registration command, verify every node:

- [ ] `dmesg | grep -i tdx` → module initialized, KeyID range + PAMT alloc
- [ ] `/proc/cpuinfo` flags contain `sgx` (SGX CPUID enabled)
- [ ] `systemctl is-active pccs qgsd aesmd` → all `active`
- [ ] PCK registered: PCCS `pck_cert >= 8` / `platforms=1`
- [ ] `cat /sys/module/kvm_intel/parameters/tdx` → `Y`
- [ ] `kata=true` storage: RAID0 md device + `md1p1` raw + `md1p2` XFS at `/var/lib/kata-direct-volumes`
- [ ] GPUs on `vfio-pci`, no host `nvidia-smi`
- [ ] Ubuntu 26.04, kernel 7.0.0-3x pin
- [ ] No pre-existing NVIDIA stack
- [ ] etcd user/group created
- [ ] OS disk ≥1.92 TB RAID1, data disk ≥14 TB raw
- [ ] BIOS `SgxAutoRegistrationAgent` = **Disabled** (verify in iDRAC, not just on paper)

---

## 7. What comes next

Once every node passes §6, proceed to [NODE-REGISTRATION.md](NODE-REGISTRATION.md) for the RKE2 node registration command and the enrolled-cluster binding contract.

Cluster-side minimums (documented in [GPU-NODE-REQUIREMENTS.md](GPU-NODE-REQUIREMENTS.md#cluster-architecture--high-availability) and enforced by the validator):

- **7 nodes minimum** per cluster — 5 control-plane+etcd+worker combined nodes + 2 dedicated 8-GPU workers (per GPU type)
- All nodes in a single data center, same L2/low-latency fabric
- One cluster per hotkey

### Decision record — 7-node minimum (2026-09-13)

The minimum cluster topology was reduced from 8 to 7 nodes: Rationale: the 5-node combined core remains the minimum for etcd quorum with 2-failure tolerance and tech-stack hosting; 2 dedicated GPU workers keep HA for the GPU type (losing 1 of 2 leaves 1 dedicated worker serving) while lowering the entry capital cost for production clusters. The first production cluster (`na-us-michigan-97` — BTLABS, UID 97) registered with 7-node shape with the two additional workers.

### Milestone — first production miner live (2026-09-14)

`na-us-michigan-97` (**BTLABS, UID 97**) completed onboarding and entered production: 7 nodes Ready, all Intel TDX + NVIDIA CC, full Fleet GitOps infrastructure (Longhorn V2, GPU Operator, Kata 4.2.0, monitoring), hotkey binding `5DviRt3e…`, validator verdict **validated**, earning emissions every epoch. The onboarding path — BIOS/OS prep (this document) → node registration → Fleet infrastructure → hotkey binding → infrastructure validation → scoring → payout — is proven end to end on external hardware. Early Access onboarding remains hand-reviewed (KubeTEE-applied binding); permissionless registration follows in Phase 1.

---

## Appendix — known issues encountered during preparation

- **iDRAC dropped SGX attribute keys after a BIOS reboot** (observed on one H100 node) — fixed via BMC-only `GracefulRestart` of the iDRAC management controller (not a host reboot). Re-verify the full attribute set on any node where a phase fails to persist.
- **PCK registration check fails** with "Authentication failed" / "unable to open database file" against local PCCS (observed on one H200 node) — **still unresolved as of 2026-09-14** (PCKIDRetrievalTool reports `platform manifest is not available`, i.e. the consumed-manifest state; recovery is the BIOS `SgxFactoryReset` + in-band re-registration procedure — one node at a time, `sgx_factory_reset.yaml` `--limit`). The node is in the cluster, Ready, `cc.ready=true`, and counted by the validator; resolve before scheduling attestation-dependent workloads on it.
- **Playbook output truncation** can occur on long runs (site-2604); runs are idempotent — re-run and rely on the verification steps (§6) as the source of truth.
- **SSH host key errors** on fresh nodes: `ssh-keyscan` the new IPs and append to `~/.ssh/known_hosts` before running any automation.
