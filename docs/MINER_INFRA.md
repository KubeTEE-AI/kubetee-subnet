# Miner Infrastructure Setup

## Kernel Ubuntu 24.04

> Kubelet kernel settings

```sh
cat > /etc/sysctl.d/90-kubelet.conf << EOF
vm.overcommit_memory=1
kernel.panic=10
kernel.panic_on_oops=1
EOF
sysctl -p /etc/sysctl.d/90-kubelet.conf
```

> Check if etcd user/group exist

```sh
id etcd
```

Expected output

```txt
uid=997(etcd) gid=997(etcd) groups=997(etcd)
```

Create if not exist

```sh
sudo groupadd --system etcd
sudo useradd --system -g etcd -s /sbin/nologin -M etcd
```

---

## Next Steps

After completing the infrastructure setup, proceed to node registration:

**See**: [NODE-REGISTRATION.md](NODE-REGISTRATION.md) for:
- Registering your node to the RKE2 cluster
- Setting up storage disks for Longhorn
- Verifying node and storage configuration
- Troubleshooting common issues

**For GPU nodes**, also see: [GPU-NODE-REQUIREMENTS.md](GPU-NODE-REQUIREMENTS.md) for:
- Complete GPU hardware requirements (H100/H200 only)
- CPU requirements (Intel 5th/6th Gen, AMD 4th/5th Gen)
- Firmware update requirements (MANDATORY)
- PPCIe mode and VFIO/IOMMU configuration