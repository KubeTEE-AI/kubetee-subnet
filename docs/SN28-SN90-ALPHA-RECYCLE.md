# SN28→SN90 Alpha Recycler

**Status:** Live on `na-us-oakland-56` as of 2026-08-23. Hourly CronJob swaps remaining SN28 on `sn28` with `allow_partial=True` and recycles the SN90 fill.  
**Channel:** SN28 sayGM is live as idle-capacity inference — [SN28-SAYGM.md](./SN28-SAYGM.md). This doc is only the Alpha swap/recycle job.  
**Cluster:** `na-us-oakland-56` only (`kata-qemu-tdx-runtime-rs`).  
**Bundle:** `fleet-gitops/infrastructure/alpha-recycler/`

Each SN28 epoch (~360 blocks / ~72 min), a CPU-TDX CronJob:

1. Attests to Trustee KBS and fetches **proxy** seeds (not the main coldkey).
2. `swap_stake_limit` SN28→SN90 on hotkey `sn28` with `rate_tolerance=0.001`, `allow_partial=True` (full remaining origin; optional `MAX_ORIGIN_RAO` cap).
3. `recycle_alpha` on netuid **90** for SN90 alpha on that hotkey.

Main kubetee coldkey stays offline after a one-time `AddProxy`.

## Identities (locked)

| Role | Value |
|------|--------|
| Main coldkey (offline) | `5C9y6fnLPSzBeh1Np7f4DnGen42xV29nL9qZTDuwpVC4iTEE` |
| SN28 hotkey `sn28` (uid 44) | `5EvosuiYGEf8xqDfHVyQcyPD1BjN1fDjyqLdhHMRMawPo42Y` |
| Proxy A | `Staking` → `swap_stake_limit` |
| Proxy B | `NonFungible` → `recycle_alpha` |
| KBS paths | `default/proxy-staking/seed`, `default/proxy-nonfungible/seed` |
| Initdata role | `alpha-recycler` |
| KBS URL | `http://kbs-service.trustee-operator-system.svc.cluster.local:8080` |

Never put seeds, mnemonics, or coldkey material in Git or in Kubernetes Secrets.

## One-time setup (laptop)

Follow [`scripts/sn28-add-proxy-and-seed-kbs.md`](../../scripts/sn28-add-proxy-and-seed-kbs.md):

1. Generate proxy keypairs A and B (local only).
2. `AddProxy` Staking + NonFungible from the **main** coldkey (then coldkey offline).
3. Seed both seeds into Trustee KBS with admin JWT (`kbs-client set-resource`).
4. Build/push **private** `ghcr.io/kubetee-ai/alpha-recycler:v0.1.0`. CronJob uses out-of-band `ghcr-kubetee` (`imagePullSecrets`). Do not host-pull on TDX nodes.
5. Apply GitRepo on stagingrancher (Gotcha #8).

## Deploy / resync

```bash
# After push to kubetee-fleet main:
kubectl --context stagingrancher apply -f \
  fleet-gitops/infrastructure/alpha-recycler/gitrepo-staging.yaml
kubectl --context stagingrancher annotate gitrepo alpha-recycler-staging -n fleet-default \
  fleet.cattle.io/force-update="$(date +%s)" --overwrite

kubectl --context na-us-oakland-56-direct -n kubetee-ops get cronjob,job,pods
kubectl --context na-us-oakland-56-direct -n kubetee-ops logs -l app.kubernetes.io/name=alpha-recycler --tail=200
```

Schedule: `0 * * * *` with `concurrencyPolicy: Forbid` (hourly; SN28 tempo ≈ 72 min).

## Initdata

```bash
python3 nim/eastwest/encode-initdata.py \
  --role alpha-recycler \
  --policy nim/eastwest/policy-recycler.rego \
  --write-toml nim/eastwest/initdata-recycler.toml
```

Paste stdout into CronJob annotation `io.katacontainers.config.hypervisor.cc_init_data` (already baked for first cut). Agent policy denies `ExecProcessRequest` (same posture as LiteLLM).

## Ops notes

- **Never** `kubectl delete --force --grace-period=0` on the CronJob pods (Kata TDX). Graceful delete or wait.
- Trustee KBS resource store is `emptyDir` memory — a trustee pod restart **wipes** seeded proxy seeds. Re-seed after every trustee roll (same as east-west certs). See `fleet-gitops/infrastructure/trustee/KubeTEE.md`.
- If a guest is suspected compromised: `remove_proxy` for A and B from the main coldkey, rotate seeds in KBS, rebuild initdata if role/policy changes.
- Dust: if SN28 stake &lt; `DUST_RAO` (default `1000000`), the job exits 0 without submitting.
- Stock SDK `SwapStake` hardcodes `allow_partial=False`; `recycle.py` composes `swap_stake_limit` with `allow_partial=True` via `submit_call` + `Proxy.proxy`.
- Image rebuild is only needed for SDK bumps; script changes go through ConfigMap (`scripts/_embed_configmap.py`).

## How to see recycled alpha

`recycle_alpha` does **not** show up as a TAO transfer. It emits `SubtensorModule.AlphaRecycled(coldkey, hotkey, amount, netuid)` and increments `AlphaAssets.AlphaRecycled[netuid]` (circulating SN90 alpha down; emission runway up). The swap that feeds it **does** show as a dTAO trade (SN28 → SN90).

**Public (anyone):**

| What | Where |
|------|--------|
| First live swap (2026-08-23 13:00:36Z) | [tao.app extrinsic `8907772-0011`](https://www.tao.app/extrinsic/8907772-0011) · [block 8907772](https://www.tao.app/block/8907772) |
| Coldkey stake + trades | [tao.app account](https://www.tao.app/account/5C9y6fnLPSzBeh1Np7f4DnGen42xV29nL9qZTDuwpVC4iTEE) · [TaoStats account](https://taostats.io/account/5C9y6fnLPSzBeh1Np7f4DnGen42xV29nL9qZTDuwpVC4iTEE) |
| SN90 subnet | [tao.app / subnet 90](https://www.tao.app/subnet/90) · [TaoStats SN90](https://taostats.io/subnets/90) |

That first fill: **134.452694 SN28 α → 52.576115 SN90 α** (~τ2.24 / ~$507), then `recycle_alpha` on hotkey `sn28` (uid 44). Recycle is the next `Proxy.proxy` after the swap (same coldkey; inner call `SubtensorModule.recycle_alpha`). TaoStats lists the swap as a dTAO trade `from_name=SN28` `to_name=SN90`.

```bash
# Remaining SN28 on sn28; SN90 on that hotkey should be dust/zero after recycle
btcli stake list \
  --coldkey 5C9y6fnLPSzBeh1Np7f4DnGen42xV29nL9qZTDuwpVC4iTEE \
  --network finney --dust

btcli query block-info --block 8907772 --network finney
```

**Operator (cluster):**

```bash
kubectl --context na-us-oakland-56-direct -n kubetee-ops get cronjob,job
kubectl --context na-us-oakland-56-direct -n kubetee-ops logs \
  -l app.kubernetes.io/name=alpha-recycler -c recycle --tail=80
```

Look for `swap done dest_before=… dest_after=… filled=…` then `recycle done`. Never `--force` delete the Kata pod.

## Announcement (paste for @KubeTEEAI)

SN28 miner emissions we earn on sayGM idle capacity are now swapped SN28→SN90 and recycled on SN90 each hour (`allow_partial`). Recycled alpha returns to unissued supply — it is not a TAO burn and not a transfer off the coldkey.

First fill (2026-08-23): 134.45 SN28 α → 52.58 SN90 α recycled (~τ2.24). Verify: https://www.tao.app/extrinsic/8907772-0011

Coldkey: `5C9y6fnLPSzBeh1Np7f4DnGen42xV29nL9qZTDuwpVC4iTEE`  
Hotkey `sn28` (uid 44): `5EvosuiYGEf8xqDfHVyQcyPD1BjN1fDjyqLdhHMRMawPo42Y`

## Related

- East-west AA/KBS pattern: [EAST-WEST-ATTESTED-MTLS.md](./EAST-WEST-ATTESTED-MTLS.md)
- Trustee ops: `fleet-gitops/infrastructure/trustee/KubeTEE.md`
- SayGM / SN28 miner context: [SN28-SAYGM.md](./SN28-SAYGM.md)
- Recycling: [TaoStats recycling](https://docs.taostats.io/docs/recycling)
