# Miner Infrastructure Setup

Initial node setup that must be completed **before** registering a node to an
RKE2 cluster. Covers the kubelet kernel settings and the etcd user/group that
RKE2 expects on the host.

## OS baseline

- Ubuntu 26.04
- Kernel `7.0.0-27-generic` or newer (GPU nodes also require this — see
  [GPU-NODE-REQUIREMENTS.md](GPU-NODE-REQUIREMENTS.md))
- A clean OS install with **no pre-existing NVIDIA drivers / CUDA / GPU
  software** — the GPU Operator installs and manages all of it in-guest.

## Kubelet kernel settings

```sh
cat > /etc/sysctl.d/90-kubelet.conf << EOF
vm.overcommit_memory=1
kernel.panic=10
kernel.panic_on_oops=1
EOF
sysctl -p /etc/sysctl.d/90-kubelet.conf
```

## etcd user/group

Check whether the etcd user/group already exist:

```sh
id etcd
```

Expected output:

```txt
uid=997(etcd) gid=997(etcd) groups=997(etcd)
```

Create them if they do not exist:

```sh
sudo groupadd --system etcd
sudo useradd --system -g etcd -s /sbin/nologin -M etcd
```

## Minimum resources

- 8 CPU cores, 16 GB RAM
- 800 GB OS disk + 3 TB data disk (for Longhorn)

## Next Steps

After completing the infrastructure setup, proceed to node registration:

- **[NODE-REGISTRATION.md](NODE-REGISTRATION.md)** — registering the node to the
  RKE2 cluster, setting up storage disks for Longhorn, verifying node and
  storage configuration, and troubleshooting common issues.
- **[GPU-NODE-REQUIREMENTS.md](GPU-NODE-REQUIREMENTS.md)** (GPU nodes only) —
  complete GPU hardware requirements (H100/H200/B200/B300), CPU requirements
  (Intel 5th/6th Gen TDX, AMD 4th/5th Gen SEV-SNP), firmware update
  requirements, and PPCIe mode / VFIO/IOMMU configuration.
