# KubeTEE GitHub Linking: Testing & Deployment Guide

This comprehensive manual guides you through testing the GitHub linking feature and deploying the smart contracts to Bittensor EVM networks.

## Table of Contents

1. [Prerequisites](#prerequisites)
2. [Local Development Setup](#local-development-setup)
3. [Running Tests](#running-tests)
   - [Python Unit Tests](#python-unit-tests)
   - [Smart Contract Tests](#smart-contract-tests)
   - [Integration Tests](#integration-tests)
   - [Acceptance Tests](#acceptance-tests)
4. [Smart Contract Deployment](#smart-contract-deployment)
   - [Bittensor EVM Testnet](#bittensor-evm-testnet)
   - [Bittensor EVM Mainnet](#bittensor-evm-mainnet)
5. [Post-Deployment Verification](#post-deployment-verification)
6. [Troubleshooting](#troubleshooting)

---

## Prerequisites

### System Requirements

- **Node.js**: v18.x or higher
- **Python**: 3.10+
- **npm** or **yarn**
- **Git**

### Required Tools

```bash
# Check versions
node --version    # Should be >= 18.x
python --version  # Should be >= 3.10
npm --version     # Should be >= 8.x
```

### Bittensor Wallet

You need a Bittensor wallet with:
- **Coldkey**: For signing transactions
- **Hotkey**: For validator/miner identity

```bash
# Install Bittensor CLI (if not installed)
pip install bittensor

# Create wallet (if you don't have one)
btcli wallet new_coldkey --wallet.name my_wallet
btcli wallet new_hotkey --wallet.name my_wallet --wallet.hotkey default
```

---

## Local Development Setup

### Step 1: Clone and Install Python Dependencies

```bash
cd kubetee-subnet

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install Python dependencies
pip install -e .
pip install -r requirements.txt
```

### Step 2: Install Hardhat and Contract Dependencies

```bash
cd kubetee/contracts

# Install Node dependencies
npm install

# Verify Hardhat installation
npx hardhat --version
```

### Step 3: Environment Configuration

Create a `.env` file in `kubetee/contracts/`:

```bash
# kubetee/contracts/.env

# For local testing (Hardhat generates these automatically)
# PRIVATE_KEY is only needed for testnet/mainnet deployment

# Testnet deployment (get TAO from faucet)
TESTNET_PRIVATE_KEY=your_private_key_for_testnet

# Mainnet deployment (use with caution!)
MAINNET_PRIVATE_KEY=your_private_key_for_mainnet

# Optional: For Etherscan-like verification
EXPLORER_API_KEY=your_api_key
```

⚠️ **SECURITY WARNING**: Never commit `.env` files to version control!

---

## Running Tests

### Python Unit Tests

Run all Python tests with coverage:

```bash
cd kubetee-subnet

# Run all tests
pytest tests/ -v

# Run with coverage report
pytest tests/ --cov=kubetee --cov-report=html --cov-report=term

# Run specific test files
pytest tests/test_github_verifier.py -v
pytest tests/test_github_api.py -v

# Run only fast tests (skip slow integration tests)
pytest tests/ -v -m "not slow"
```

**Expected Output:**
```
tests/test_github_verifier.py::TestValidationCheckA::test_check_a_passes ... PASSED
tests/test_github_verifier.py::TestValidationCheckB::test_check_b_passes ... PASSED
...
============== 45 passed in 12.34s ==============
```

#### View Coverage Report

```bash
# Open HTML coverage report
open htmlcov/index.html  # macOS
xdg-open htmlcov/index.html  # Linux
start htmlcov/index.html  # Windows
```

### Smart Contract Tests

Run Hardhat tests for the Solidity contracts:

```bash
cd kubetee/contracts

# Run all contract tests
npx hardhat test

# Run with gas reporting
REPORT_GAS=true npx hardhat test

# Run specific test file
npx hardhat test test/KubeTEEGitHubRegistry.test.js

# Run with verbose output
npx hardhat test --verbose
```

**Expected Output:**
```
  KubeTEEGitHubRegistry
    Deployment
      ✓ Should deploy with correct initial values
      ✓ Should set the deployer as owner
      ✓ Should initialize as upgradeable proxy
    Validator Management
      ✓ Should allow owner to add validator
      ✓ Should emit ValidatorAdded event
      ...

  23 passing (4s)
```

#### Test Coverage for Contracts

```bash
cd kubetee/contracts

# Generate coverage report
npx hardhat coverage

# Coverage report will be in coverage/index.html
```

### Integration Tests

Integration tests verify Python ↔ Contract interaction:

```bash
cd kubetee-subnet

# Run integration tests (requires local Hardhat node)
pytest tests/acceptance/test_contract_integration.py -v

# Or run with a separate terminal running Hardhat node:
# Terminal 1:
cd kubetee/contracts && npx hardhat node

# Terminal 2:
pytest tests/acceptance/test_contract_integration.py -v
```

### Acceptance Tests

End-to-end acceptance tests:

```bash
cd kubetee-subnet

# Run all acceptance tests
pytest tests/acceptance/ -v

# Run specific acceptance test
pytest tests/acceptance/test_e2e_github_linking.py -v
pytest tests/acceptance/test_cli_acceptance.py -v
```

### Run All Tests Together

```bash
cd kubetee-subnet

# Run everything in one command
./run_all_tests.sh

# Or manually:
# 1. Start Hardhat node in background
cd kubetee/contracts && npx hardhat node &
HARDHAT_PID=$!

# 2. Run contract tests
npx hardhat test

# 3. Run Python tests
cd ../..
pytest tests/ -v --cov=kubetee

# 4. Cleanup
kill $HARDHAT_PID
```

---

## Smart Contract Deployment

### Network Information

| Network | Chain ID | RPC URL | Explorer |
|---------|----------|---------|----------|
| **Bittensor EVM Testnet** | 945 | `https://test.chain.opentensor.ai` | TBD |
| **Bittensor EVM Mainnet** | 964 | `https://chain.opentensor.ai` | TBD |

### Bittensor EVM Testnet

#### Step 1: Get Testnet TAO

Get testnet TAO from the Bittensor faucet:

```bash
# Visit Bittensor Discord or testnet faucet
# Request testnet TAO for your wallet address
```

#### Step 2: Configure Testnet Deployment

Verify `hardhat.config.js` has testnet configuration:

```javascript
// kubetee/contracts/hardhat.config.js
networks: {
  bittensorTestnet: {
    url: "https://test.chain.opentensor.ai",
    chainId: 945,
    accounts: process.env.TESTNET_PRIVATE_KEY 
      ? [process.env.TESTNET_PRIVATE_KEY] 
      : [],
  },
}
```

#### Step 3: Deploy to Testnet

```bash
cd kubetee/contracts

# Compile contracts first
npx hardhat compile

# Deploy to testnet
npx hardhat run scripts/deploy.js --network bittensorTestnet
```

**Expected Output:**
```
Deploying KubeTEEGitHubRegistry to Bittensor Testnet...
Deploying implementation contract...
Implementation deployed at: 0x1234...abcd
Deploying proxy contract...
Proxy deployed at: 0x5678...efgh
Initializing contract...
Contract initialized successfully!

========================================
DEPLOYMENT SUMMARY
========================================
Network: Bittensor EVM Testnet (chainId: 945)
Proxy Address: 0x5678...efgh
Implementation Address: 0x1234...abcd
Owner: 0xYourWalletAddress
========================================

Save these addresses for configuration!
```

#### Step 4: Save Contract Addresses

Save the deployed addresses in your configuration:

```bash
# Create or update config file
cat > kubetee/config/testnet.json << EOF
{
  "network": "bittensor_testnet",
  "chainId": 945,
  "rpcUrl": "https://test.chain.opentensor.ai",
  "contracts": {
    "githubRegistry": {
      "proxy": "0x5678...efgh",
      "implementation": "0x1234...abcd"
    }
  },
  "deployedAt": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
  "deployedBy": "your_address"
}
EOF
```

### Bittensor EVM Mainnet

⚠️ **MAINNET DEPLOYMENT CHECKLIST**:

- [ ] All tests pass locally
- [ ] Testnet deployment verified and works
- [ ] Smart contract audited (recommended)
- [ ] Sufficient TAO for gas fees
- [ ] Private key secured properly
- [ ] Team review completed

#### Step 1: Verify Mainnet Configuration

```javascript
// kubetee/contracts/hardhat.config.js
networks: {
  bittensorMainnet: {
    url: "https://chain.opentensor.ai",
    chainId: 964,
    accounts: process.env.MAINNET_PRIVATE_KEY 
      ? [process.env.MAINNET_PRIVATE_KEY] 
      : [],
  },
}
```

#### Step 2: Estimate Gas Costs

```bash
cd kubetee/contracts

# Estimate deployment gas
npx hardhat run scripts/estimate-gas.js --network bittensorMainnet
```

#### Step 3: Deploy to Mainnet

```bash
cd kubetee/contracts

# Final compilation
npx hardhat compile

# Deploy to mainnet
npx hardhat run scripts/deploy.js --network bittensorMainnet
```

#### Step 4: Save Mainnet Configuration

```bash
cat > kubetee/config/mainnet.json << EOF
{
  "network": "bittensor_mainnet",
  "chainId": 964,
  "rpcUrl": "https://chain.opentensor.ai",
  "contracts": {
    "githubRegistry": {
      "proxy": "DEPLOYED_PROXY_ADDRESS",
      "implementation": "DEPLOYED_IMPL_ADDRESS"
    }
  },
  "deployedAt": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
  "deployedBy": "your_address"
}
EOF
```

---

## Post-Deployment Verification

### Verify Contract Deployment

```bash
cd kubetee/contracts

# Verify on testnet
npx hardhat verify --network bittensorTestnet PROXY_ADDRESS

# Verify on mainnet
npx hardhat verify --network bittensorMainnet PROXY_ADDRESS
```

### Test Contract Functionality

Create a test script to verify the deployed contract:

```javascript
// scripts/verify-deployment.js
const { ethers } = require("hardhat");

async function main() {
  const proxyAddress = "YOUR_PROXY_ADDRESS";
  
  const Registry = await ethers.getContractFactory("KubeTEEGitHubRegistry");
  const registry = Registry.attach(proxyAddress);
  
  // Check owner
  const owner = await registry.owner();
  console.log("Contract owner:", owner);
  
  // Check version
  const version = await registry.version();
  console.log("Contract version:", version);
  
  // Test read functions
  const validators = await registry.getValidators();
  console.log("Registered validators:", validators.length);
  
  console.log("\n✅ Contract verification successful!");
}

main().catch(console.error);
```

Run verification:

```bash
npx hardhat run scripts/verify-deployment.js --network bittensorTestnet
```

### Configure Python Application

Update the Python configuration to use deployed contract:

```python
# kubetee/config.py or environment variables

import os

NETWORK = os.getenv("KUBETEE_NETWORK", "testnet")

NETWORKS = {
    "testnet": {
        "rpc_url": "https://test.chain.opentensor.ai",
        "chain_id": 945,
        "github_registry": "YOUR_TESTNET_PROXY_ADDRESS",
    },
    "mainnet": {
        "rpc_url": "https://chain.opentensor.ai",
        "chain_id": 964,
        "github_registry": "YOUR_MAINNET_PROXY_ADDRESS",
    },
}

def get_config():
    return NETWORKS[NETWORK]
```

### Test CLI with Deployed Contract

```bash
# Set environment for testnet
export KUBETEE_NETWORK=testnet
export KUBETEE_RPC_URL=https://test.chain.opentensor.ai
export KUBETEE_REGISTRY_ADDRESS=YOUR_PROXY_ADDRESS

# Test the CLI
kubetee link-github --hotkey 5FHneW46xR...abc123 --dry-run
```

---

## Troubleshooting

### Common Issues

#### 1. "Insufficient funds for gas"

```bash
# Check your wallet balance
npx hardhat run scripts/check-balance.js --network bittensorTestnet

# Solution: Get more TAO from faucet (testnet) or transfer TAO (mainnet)
```

#### 2. "Nonce too low"

```bash
# Reset nonce in Hardhat config or wait for pending transactions
# Or manually specify nonce in deployment script
```

#### 3. "Contract deployment failed"

```bash
# Check gas price and increase if needed
# Verify RPC endpoint is accessible
curl -X POST https://test.chain.opentensor.ai \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","method":"eth_blockNumber","params":[],"id":1}'
```

#### 4. "Python tests failing with Web3 errors"

```bash
# Ensure Hardhat node is running for local tests
cd kubetee/contracts && npx hardhat node

# Or mock Web3 in tests (see conftest.py)
```

#### 5. "Import errors in Python"

```bash
# Reinstall package in editable mode
pip install -e .

# Verify installation
python -c "from kubetee.validator import GitHubRegistry; print('OK')"
```

### Debug Mode

Enable verbose logging for debugging:

```bash
# Python
export KUBETEE_LOG_LEVEL=DEBUG
pytest tests/ -v -s

# Hardhat
DEBUG=hardhat:* npx hardhat test
```

### Getting Help

- **GitHub Issues**: https://github.com/KubeTEE-AI/kubetee-subnet/issues
- **Discord**: KubeTEE AI Discord server
- **Documentation**: `docs/GITHUB_LINKING_ARCHITECTURE.md`

---

## Quick Reference

### Test Commands

| Command | Description |
|---------|-------------|
| `pytest tests/ -v` | Run all Python tests |
| `pytest tests/ --cov=kubetee` | Run with coverage |
| `npx hardhat test` | Run contract tests |
| `npx hardhat coverage` | Contract coverage |

### Deployment Commands

| Command | Description |
|---------|-------------|
| `npx hardhat compile` | Compile contracts |
| `npx hardhat run scripts/deploy.js --network bittensorTestnet` | Deploy to testnet |
| `npx hardhat run scripts/deploy.js --network bittensorMainnet` | Deploy to mainnet |
| `npx hardhat verify --network <network> <address>` | Verify contract |

### Environment Variables

| Variable | Description | Example |
|----------|-------------|---------|
| `TESTNET_PRIVATE_KEY` | Wallet private key for testnet | `0x...` |
| `MAINNET_PRIVATE_KEY` | Wallet private key for mainnet | `0x...` |
| `KUBETEE_NETWORK` | Active network | `testnet` or `mainnet` |
| `KUBETEE_RPC_URL` | RPC endpoint override | `https://...` |
| `KUBETEE_REGISTRY_ADDRESS` | Contract address override | `0x...` |

---

## Next Steps

After successful deployment:

1. **Add validators** to the contract via owner functions
2. **Configure validators** to use the deployed contract address
3. **Test the full flow** with a real GitHub gist verification
4. **Monitor events** from the contract for debugging
5. **Set up monitoring** for contract interactions

For the complete user guide, see [`docs/GITHUB_LINKING_GUIDE.md`](../GITHUB_LINKING_GUIDE.md).
