# GitHub Linking Guide for KubeTEE Miners

This guide explains how to link your GitHub account to your Bittensor hotkey on the KubeTEE subnet (subnet 62). GitHub linking enables bounty attribution, open-source contribution tracking, and participation in various reward mechanisms.

## Table of Contents

- [Overview](#overview)
- [Prerequisites](#prerequisites)
- [Step 1: Create a HOTKEY.md Gist](#step-1-create-a-hotkeymd-gist)
- [Step 2: Install the CLI](#step-2-install-the-cli)
- [Step 3: Link Your GitHub](#step-3-link-your-github)
- [Step 4: Verify Your Link Status](#step-4-verify-your-link-status)
- [Mechanism IDs](#mechanism-ids)
- [Verification Process](#verification-process)
- [Environment Variables](#environment-variables)
- [CLI Reference](#cli-reference)
- [Troubleshooting](#troubleshooting)
- [FAQ](#faq)

---

## Overview

Linking your GitHub account to your miner hotkey allows the KubeTEE subnet to:

- **Attribute bounty rewards** – When you complete bounties, rewards are correctly assigned to your hotkey
- **Track open-source contributions** – Your GitHub activity can be factored into scoring mechanisms
- **Enable referral tracking** – Link your GitHub for participation in the referral program
- **Verify infrastructure providers** – Prove ownership of repositories containing deployment configurations

The linking process uses a public GitHub gist as a proof of ownership, where you publish your hotkey in a file that can only be created by you (the GitHub account owner).

---

## Prerequisites

Before you begin, ensure you have:

1. **Registered miner on subnet 62** – Your hotkey must be registered on the KubeTEE subnet
2. **GitHub account** – A valid GitHub account (free tier is fine)
3. **Bittensor wallet with hotkey** – Configured on your machine
4. **Python 3.9+** – Required for the CLI tool

### Check Your Registration

Verify your miner is registered:

```bash
btcli subnet metagraph --subtensor.network finney --netuid 62 | grep YOUR_HOTKEY
```

If your hotkey doesn't appear in the metagraph, you need to register first before linking GitHub.

---

## Step 1: Create a HOTKEY.md Gist

A **gist** is a simple way to share text files on GitHub. You will create a public gist containing your hotkey information.

### 1.1 Go to GitHub Gist

Navigate to [https://gist.github.com](https://gist.github.com) and sign in with your GitHub account.

### 1.2 Create the Gist

1. **Filename:** Enter `HOTKEY.md` (case-sensitive, must be exact)
2. **Content:** Copy and paste the following template, replacing the placeholder with your actual hotkey:

```markdown
# KubeTEE Miner Registration

This gist verifies ownership of the following Bittensor hotkey.

hotkey: 5GrwvaEF5zXb26Fz9rcQpDWS57CtERHpNehXCPcNoHGKutQY

Linked to GitHub: @yourusername
Mechanism: bounty (3)
Created: 2026-01-13
```

> ⚠️ **Important:** The `hotkey:` line is the only required field. The format must be exactly:
> ```
> hotkey: YOUR_SS58_HOTKEY_ADDRESS
> ```
> The hotkey must be a valid Bittensor SS58 address starting with `5` and containing 48 characters.

### 1.3 Get Your Hotkey Address

If you're unsure of your SS58 hotkey address, you can find it with:

```bash
btcli wallet list
```

Or by examining your wallet file:

```bash
cat ~/.bittensor/wallets/YOUR_WALLET/hotkeys/YOUR_HOTKEY
```

### 1.4 Make the Gist Public

⚠️ **Critical:** Select **"Create public gist"** (not secret). The gist must be public for verification to work.

### 1.5 Copy the Gist URL

After creating the gist, copy the URL from your browser's address bar. It will look like:

```
https://gist.github.com/yourusername/abc123def456789...
```

---

## Step 2: Install the CLI

The KubeTEE CLI provides the `link-github` command for linking your account.

### Option A: Install from Source (Recommended)

```bash
# Clone the repository
git clone https://github.com/kubetee/kubetee-subnet.git
cd kubetee-subnet

# Install in development mode
pip install -e .
```

### Option B: Install Directly

```bash
pip install kubetee-subnet
```

### Verify Installation

```bash
kubetee --version
# Expected output: kubetee, version 0.1.0
```

---

## Step 3: Link Your GitHub

Now you're ready to link your GitHub account to your hotkey.

### Basic Usage

```bash
kubetee link-github \
    --gist-url https://gist.github.com/yourusername/abc123def456789 \
    --mechanism-id 3
```

### With Explicit Wallet

If you have multiple wallets, specify which one to use:

```bash
kubetee link-github \
    --gist-url https://gist.github.com/yourusername/abc123def456789 \
    --mechanism-id 3 \
    --wallet-name my_wallet \
    --wallet-hotkey my_hotkey
```

### Dry Run Mode

Test the request without actually sending it:

```bash
kubetee link-github \
    --gist-url https://gist.github.com/yourusername/abc123def456789 \
    --mechanism-id 3 \
    --dry-run
```

### Expected Output (Success)

```
Loading wallet 'default' with hotkey 'default'...
Hotkey: 5GrwvaEF5zXb26Fz9rcQpDWS57CtERHpNehXCPcNoHGKutQY
Message: {"hotkey":"5GrwvaEF5zXb26Fz9rcQpDWS57CtERHpNehXCPcNoHGKutQY","timestamp":1736766374}
Signing message with hotkey...
Signature: 0x1234567890abcdef...6789
Sending link request to https://validator.kubetee.io...

✅ GitHub linked successfully!
   Hotkey: 5GrwvaEF5zXb26...GKutQY
   GitHub: yourusername
   Mechanism: bounty (3)
   Status: created
   Transaction: 0xabcdef123456789...
```

---

## Step 4: Verify Your Link Status

After linking, you can verify that your GitHub account is properly linked:

```bash
kubetee status --hotkey 5GrwvaEF5zXb26Fz9rcQpDWS57CtERHpNehXCPcNoHGKutQY
```

### Expected Output

```
✅ Hotkey is linked
   Hotkey: 5GrwvaEF5zXb26...GKutQY
   GitHub: yourusername
   Mechanism: bounty (3)
```

---

## Mechanism IDs

Different mechanisms in the KubeTEE subnet use GitHub linking for different purposes. You should select the mechanism ID that matches your participation type.

| Mechanism ID | Name | Description |
|:------------:|------|-------------|
| **0** | Infrastructure | For miners providing GPU/compute infrastructure. Links GitHub for deployment configuration verification. |
| **1** | Open Source | For contributors to KubeTEE open-source projects. Used for contribution-based rewards. |
| **2** | Referral | For referral program participation. Links GitHub for referral tracking and attribution. |
| **3** | Bounty | For bounty hunters. **Most common.** Links GitHub for bounty completion attribution. |

### Which Mechanism Should I Choose?

- **Bounty hunters** → Use mechanism ID **3**
- **Infrastructure providers** → Use mechanism ID **0**
- **Open source contributors** → Use mechanism ID **1**
- **Referral program participants** → Use mechanism ID **2**

> 💡 **Note:** You can link the same hotkey to multiple mechanisms if needed. Simply run the `link-github` command multiple times with different `--mechanism-id` values.

---

## Verification Process

When you submit a link request, the validator performs **6 security checks** before recording your link on-chain. Understanding these checks helps you troubleshoot issues.

```
┌─────────────────────────────────────────────────────────────────┐
│                    6 VALIDATION CHECKS                          │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  [A] SUBNET REGISTRATION                                        │
│      Verifies your hotkey is registered on subnet 62            │
│      Error: hotkey_not_registered                               │
│                                                                 │
│  [B] SIGNATURE VERIFICATION                                     │
│      Cryptographically verifies you own the hotkey              │
│      Error: invalid_signature                                   │
│                                                                 │
│  [C] GIST EXISTS                                                │
│      Confirms gist URL is valid and gist is public             │
│      Error: gist_not_found                                      │
│                                                                 │
│  [D] HOTKEY IN GIST                                             │
│      Parses HOTKEY.md to extract your hotkey                   │
│      Error: hotkey_md_missing, invalid_hotkey_format            │
│                                                                 │
│  [E] HOTKEY MATCH                                               │
│      Ensures claimed == signed == gist (all three match)        │
│      Error: hotkey_mismatch                                     │
│                                                                 │
│  [F] GITHUB USER EXISTS                                         │
│      Validates the gist owner is a real GitHub account          │
│      Error: github_user_not_found                               │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### Why These Checks Exist

| Check | Security Purpose |
|-------|------------------|
| Registration | Prevents non-miners from claiming rewards |
| Signature | Proves cryptographic ownership of the hotkey |
| Gist existence | Ensures verifiable link between GitHub and hotkey |
| HOTKEY.md | Standardizes the proof format |
| Hotkey match | Prevents claiming someone else's hotkey |
| GitHub user | Prevents links to deleted/banned accounts |

---

## Environment Variables

The CLI supports environment variables for common options, making repeated commands easier.

| Environment Variable | CLI Option | Description |
|---------------------|------------|-------------|
| `KUBETEE_WALLET` | `--wallet-name` | Bittensor wallet name (coldkey name) |
| `KUBETEE_WALLET_HOTKEY` | `--wallet-hotkey` | Wallet hotkey name |
| `KUBETEE_VALIDATOR` | `--validator-url` | Validator API URL |
| `KUBETEE_HOTKEY_ADDRESS` | `--hotkey` | Explicit SS58 hotkey address |

### Example: Using Environment Variables

```bash
# Set environment variables
export KUBETEE_WALLET=my_wallet
export KUBETEE_WALLET_HOTKEY=my_hotkey
export KUBETEE_VALIDATOR=https://validator.kubetee.io

# Now commands are shorter
kubetee link-github -g https://gist.github.com/you/abc123 -m 3
kubetee status -h 5GrwvaEF5zXb26Fz9rcQpDWS57CtERHpNehXCPcNoHGKutQY
```

### Adding to Shell Profile

For persistence, add exports to your `~/.bashrc` or `~/.zshrc`:

```bash
echo 'export KUBETEE_WALLET=my_wallet' >> ~/.bashrc
echo 'export KUBETEE_WALLET_HOTKEY=my_hotkey' >> ~/.bashrc
source ~/.bashrc
```

---

## CLI Reference

### `kubetee link-github`

Link your GitHub account to your miner hotkey.

```
Usage: kubetee link-github [OPTIONS]

Options:
  -h, --hotkey TEXT           SS58 hotkey address (auto-derived from wallet if not provided)
  -m, --mechanism-id INTEGER  Mechanism ID (0=infra, 1=opensource, 2=referral, 3=bounty) [required]
  -g, --gist-url TEXT         URL to public gist containing HOTKEY.md file [required]
  -w, --wallet-name TEXT      Bittensor wallet name (coldkey name) [default: default]
  -k, --wallet-hotkey TEXT    Wallet hotkey name [default: default]
  -v, --validator-url TEXT    Validator API URL [default: https://validator.kubetee.io]
  -t, --timeout INTEGER       Request timeout in seconds [default: 30]
  --dry-run                   Show what would be sent without making the request
  --help                      Show this message and exit
```

### `kubetee status`

Check the GitHub link status for a hotkey.

```
Usage: kubetee status [OPTIONS]

Options:
  -h, --hotkey TEXT           SS58 hotkey address to check [required]
  -m, --mechanism-id INTEGER  Mechanism ID to check [default: 3]
  -v, --validator-url TEXT    Validator API URL [default: https://validator.kubetee.io]
  --help                      Show this message and exit
```

---

## Troubleshooting

### Error Codes Reference

| Error Code | Description | Solution |
|------------|-------------|----------|
| `hotkey_not_registered` | Hotkey is not registered on subnet 62 | Register your miner on the subnet first using `btcli subnet register` |
| `invalid_signature` | Signature doesn't match the hotkey | Ensure you're using the correct wallet and hotkey. Check wallet is properly configured. |
| `gist_not_found` | Gist doesn't exist, is private, or URL is wrong | Make sure the gist is **public** (not secret). Check the URL is correct. |
| `hotkey_md_missing` | No HOTKEY.md file found in gist | Create a file named exactly `HOTKEY.md` in your gist (case-sensitive). |
| `invalid_hotkey_format` | Hotkey in gist is formatted incorrectly | Ensure format is exactly `hotkey: 5...` with a valid SS58 address. No extra characters. |
| `hotkey_mismatch` | Hotkeys don't match between claimed, signed, and gist | Ensure the same hotkey appears in your wallet, the `--hotkey` flag (if used), and the HOTKEY.md file. |
| `github_user_not_found` | GitHub username doesn't exist | Check that your GitHub account is active and hasn't been suspended. |
| `invalid_message_format` | Message JSON is malformed | This is likely a CLI bug. Update to the latest version. |
| `rate_limited` | GitHub API rate limit exceeded | Wait a few minutes and try again. Or use a `GITHUB_TOKEN` environment variable. |

### Common Issues

#### Issue: "Hotkey file not found"

```
Error: Hotkey 'default' not found for wallet 'default'.
Expected at: ~/.bittensor/wallets/default/hotkeys/default
```

**Solution:** Specify the correct wallet and hotkey names:

```bash
kubetee link-github -g YOUR_GIST_URL -m 3 \
    --wallet-name YOUR_WALLET \
    --wallet-hotkey YOUR_HOTKEY
```

#### Issue: "Failed to connect to validator"

```
Error: Failed to connect to validator at https://validator.kubetee.io. Is the validator running?
```

**Solution:** 
1. Check your internet connection
2. Verify the validator URL is correct
3. Try a different validator if one is provided by the network

#### Issue: "Gist not found" but gist exists

**Solution:**
1. Ensure the gist is **public**, not secret
2. Double-check the URL is exact (no extra characters)
3. Wait 1-2 minutes after creating the gist (GitHub API caching)

#### Issue: "Invalid hotkey format"

**Solution:** Ensure your HOTKEY.md contains exactly:

```markdown
hotkey: 5GrwvaEF5zXb26Fz9rcQpDWS57CtERHpNehXCPcNoHGKutQY
```

Common mistakes:
- ❌ `Hotkey: 5...` (wrong capitalization)
- ❌ `hotkey:5...` (missing space)
- ❌ `hotkey = 5...` (wrong separator)
- ✅ `hotkey: 5...` (correct format)

#### Issue: "Signature verification failed"

**Solution:**
1. Ensure you're using the coldkey that owns the hotkey
2. Try regenerating your wallet if keys are corrupted:
   ```bash
   btcli wallet regen_hotkey --wallet.name YOUR_WALLET --wallet.hotkey YOUR_HOTKEY
   ```
3. Verify the hotkey file exists and is readable

---

## FAQ

### Q: Can I change my linked GitHub account?

**A:** Yes. Simply create a new gist with your new GitHub account and run the `link-github` command again. The new link will override the previous one for that mechanism ID.

### Q: Can I link the same GitHub to multiple hotkeys?

**A:** Yes. You can link one GitHub account to multiple hotkeys. This is useful if you operate multiple miners.

### Q: Can I link the same hotkey to multiple mechanisms?

**A:** Yes. Run the `link-github` command multiple times with different `--mechanism-id` values. Each mechanism tracks links independently.

### Q: What happens if I delete the gist after linking?

**A:** The link remains valid. The gist is only used during the initial verification process. Once verified and recorded on-chain, deleting the gist has no effect.

### Q: Is there a cost to link my GitHub?

**A:** No direct cost to you. The validator pays the gas fees for recording the link on-chain. You just need a registered miner hotkey.

### Q: How long does the linking process take?

**A:** Typically 10-30 seconds. The validator needs to verify the gist, check your registration, and submit the on-chain transaction.

### Q: Can I use a GitHub organization account?

**A:** No. Gists are personal resources. You must use an individual GitHub account. However, you can link multiple individual accounts if you run multiple miners.

### Q: What if my gist is rate-limited?

**A:** Wait a few minutes and try again. For frequent operations, you can set a `GITHUB_TOKEN` environment variable with a personal access token to increase rate limits.

### Q: Do I need to keep bittensor running to link?

**A:** No. The CLI only needs access to your wallet files to sign the message. The actual linking is done by the validator.

### Q: How do I unlink my GitHub?

**A:** Currently, unlinking is not supported. Links are permanent on-chain records. If you need to correct a mistake, link again with the correct information (new links override old ones for the same mechanism ID).

---

## Support

If you encounter issues not covered in this guide:

1. **Check the architecture documentation:** [`GITHUB_LINKING_ARCHITECTURE.md`](GITHUB_LINKING_ARCHITECTURE.md)
2. **Open an issue:** [GitHub Issues](https://github.com/kubetee/kubetee-subnet/issues)
3. **Join Discord:** [KubeTEE Discord](https://discord.gg/kubetee)

---

*Last updated: January 13, 2026*
