# SN28→SN90 Alpha Recycler

**Status:** Live as of 2026-08-23. **2026-09-17:** recycle proxy migrated
NonFungible → **NonTransfer** (finney v459 moved `recycle_alpha` out of
NonFungible; see "Proxy grant" below).  
**Channel:** SN28 sayGM idle-capacity inference — [SN28-SAYGM.md](./SN28-SAYGM.md).

Miner alpha we earn on SN28 is swapped to SN90 and recycled there. Recycled alpha returns to unissued supply (it is not a TAO transfer and not a burn of TAO). Swaps may fill partially; leftover SN28 is tried again on the next run.

## Proxy grant (2026-09-17: NonFungible → NonTransfer)

Finney runtime **v459** (live 2026-09-15 ~22:02 UTC, commit `23e00b72b`)
split value-moving calls (`recycle_alpha`, `burn_alpha`, `add_stake_burn`,
`lock_stake`, …) into `SubtensorValueCalls`, granted to **NonTransfer** and
NonCritical only. The old NonFungible grant (proxy B,
`5ECdc67v…`) now hits `System.CallFiltered` on `recycle_alpha` — the
2026-09-17 run swapped 81.74 SN28 α → 52.15 SN90 α and then failed the
recycle (the Job still reported `Complete` because the retry pod
dust-skipped; the stranded dest alpha is swept by the next successful
run — the recycle is independent of the swap checks since 2026-09-17).

On-chain grant (one-time, main coldkey):

```bash
btcli proxy add -w kubetee -n finney \
  --delegate 5ECdc67vzv5XDvXL5bjLedTQXVNxbknEqEdsmVr7CoGvc7Kx \
  --proxy-type NonTransfer --delay 0
```

NonTransfer is the narrowest type that still allows `recycle_alpha`: no
`Balances::transfer*`, no `transfer_stake`, no coldkey-swap lifecycle.
NonCritical also allows it but adds liquid TAO transfers — not used.

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
