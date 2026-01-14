# Revert Plan: Restore Deleted Contracts Folder

## Summary

In commit `c17bba7` (wip), the root-level `contracts/` folder containing payment-related smart contracts was removed and replaced with GitHub linking contracts at `kubetee/contracts/`.

## What Was Removed

| File | Purpose |
|------|---------|
| `contracts/KubeTEEBuybackBurn.sol` | Token buyback and burn mechanism |
| `contracts/KubeTEEEscrow.sol` | Escrow payment handling |
| `contracts/KubeTEEPayment.sol` | Payment processing |
| `contracts/KubeTEEReseller.sol` | Reseller functionality |

## What Was Added (current state on feature/oscm)

| File | Purpose |
|------|---------|
| `kubetee/contracts/contracts/KubeTEEGitHubRegistry.sol` | GitHub account linking |
| `kubetee/contracts/contracts/KubeTEEGitHubRegistryV2.sol` | V2 with upgrades |

## Current Branch: `feature/oscm`
- HEAD: `0ec398d feat(cli): Add kubetee CLI with ASCII banner and global install support`
- Contracts removed in: `c17bba7 wip`

---

## Revert Options

### Option 1: Restore Payment Contracts from `origin/main` (RECOMMENDED)
This restores only the deleted contracts folder without affecting other changes.

```bash
cd kubetee-subnet

# Restore the contracts folder from main
git checkout origin/main -- contracts/

# Verify restoration
ls contracts/

# Stage and commit
git add contracts/
git commit -m "restore: Bring back payment contracts from main"
```

### Option 2: Restore from commit before removal
```bash
cd kubetee-subnet

# Get contracts from the parent of c17bba7
git checkout c17bba7~1 -- contracts/

# Stage and commit
git add contracts/
git commit -m "restore: Bring back payment contracts"
```

### Option 3: Full Revert of commit c17bba7 (CAUTION - removes GitHub linking too)
```bash
cd kubetee-subnet

# This will undo ALL changes from c17bba7
git revert c17bba7

# This will also remove:
# - kubetee/contracts/ (GitHub registry)
# - kubetee/api/
# - kubetee/cli/
# - kubetee/validator/
# - All tests and docs
```

---

## Recommended Action

**Use Option 1** to restore the payment contracts while keeping the GitHub linking functionality:

```bash
git checkout origin/main -- contracts/
git add contracts/
git commit -m "restore: Bring back payment contracts (KubeTEEBuybackBurn, KubeTEEEscrow, KubeTEEPayment, KubeTEEReseller)"
```

This gives you both:
- ✅ `contracts/` - Payment/Reseller contracts
- ✅ `kubetee/contracts/` - GitHub Registry contracts
