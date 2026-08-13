# Deploying in a TEE — Challenge and debugging

A confidential pod is a virtual machine with an encrypted, attested memory boundary, not a namespaced process on the host. Workloads run on **miner clusters**. Every node on the subnet-owner **staging cluster** is TEE CC capable. Staging is a **debug target** when a workload fails — not a required promotion workflow.

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
