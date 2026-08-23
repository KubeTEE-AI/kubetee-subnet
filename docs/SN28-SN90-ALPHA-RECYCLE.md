# SN28→SN90 Alpha Recycler

**Status:** Live as of 2026-08-23.  
**Channel:** SN28 sayGM idle-capacity inference — [SN28-SAYGM.md](./SN28-SAYGM.md).

Miner alpha we earn on SN28 is swapped to SN90 and recycled there. Recycled alpha returns to unissued supply (it is not a TAO transfer and not a burn of TAO). Swaps may fill partially; leftover SN28 is tried again on the next run.

## See it on chain

The swap shows as a dTAO trade **SN28 → SN90**. Recycle is the following call on the same coldkey (`recycle_alpha` on netuid 90 / hotkey `sn28`).

| | |
|--|--|
| Coldkey | `5C9y6fnLPSzBeh1Np7f4DnGen42xV29nL9qZTDuwpVC4iTEE` |
| Hotkey `sn28` (uid 44) | `5EvosuiYGEf8xqDfHVyQcyPD1BjN1fDjyqLdhHMRMawPo42Y` |
| Account | [tao.app](https://www.tao.app/account/5C9y6fnLPSzBeh1Np7f4DnGen42xV29nL9qZTDuwpVC4iTEE) · [TaoStats](https://taostats.io/account/5C9y6fnLPSzBeh1Np7f4DnGen42xV29nL9qZTDuwpVC4iTEE) |
| First fill (2026-08-23) | [tao.app `8907772-0011`](https://www.tao.app/extrinsic/8907772-0011) — 134.45 SN28 α → 52.58 SN90 α recycled (~τ2.24) |
| SN90 | [tao.app](https://www.tao.app/subnet/90) · [TaoStats](https://taostats.io/subnets/90) |

On TaoStats, filter that account’s trades by **from SN28 / to SN90**. After a recycle, SN90 on hotkey `sn28` is dust or zero.

```bash
btcli stake list \
  --coldkey 5C9y6fnLPSzBeh1Np7f4DnGen42xV29nL9qZTDuwpVC4iTEE \
  --network finney --dust
```

## Related

- SayGM / SN28: [SN28-SAYGM.md](./SN28-SAYGM.md)
- What “recycle” means: [TaoStats recycling](https://docs.taostats.io/docs/recycling)
