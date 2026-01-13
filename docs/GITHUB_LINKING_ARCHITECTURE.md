# GitHub Linking Architecture

## Overview

Links miner hotkeys to GitHub accounts for bounty attribution and contribution-based rewards.

---

## High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                                                                             │
│     MINER                              VALIDATOR                  CONTRACT  │
│     ─────                              ─────────                  ────────  │
│                                                                             │
│  1. Create public gist                                                      │
│     └─ HOTKEY.md with hotkey                                                │
│                                                                             │
│  2. kubetee link-github                                                     │
│     ├─ Sign message with hotkey                                             │
│     └─ POST to validator API ──────▶  3. Validator checks:                  │
│        {                                 ├─ [A] Is hotkey registered?       │
│          hotkey: "5Grw...",              ├─ [B] Is signature valid?         │
│          gist_url: "...",                ├─ [C] Does gist exist?            │
│          signature: "0x...",             ├─ [D] Does gist contain hotkey?   │
│          message: "..."                  ├─ [E] Do all hotkeys match?       │
│        }                                 └─ [F] Does GitHub user exist?     │
│                                                                             │
│                                       4. If ALL pass ──────────────────────▶│
│                                          └─ emit GitHubLinked(hotkey, user) │
│                                                                             │
│  ON STARTUP:                                                                │
│     Validator loads all GitHubLinked events → in-memory cache              │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Project Structure

```
kubetee-subnet/
├── kubetee/                          # Main package
│   ├── __init__.py
│   ├── cli/                          # CLI commands
│   │   ├── __init__.py
│   │   └── github.py                 # kubetee link-github
│   │
│   ├── api/                          # Validator REST API
│   │   ├── __init__.py
│   │   └── github.py                 # POST /api/github/link
│   │
│   ├── validator/                    # Validator logic
│   │   ├── __init__.py
│   │   └── github_registry.py        # Validation + event loading
│   │
│   ├── miner/                        # Miner logic
│   │   └── __init__.py
│   │
│   └── contracts/                    # Solidity + Hardhat
│       ├── contracts/
│       │   ├── KubeTEEGitHubRegistry.sol
│       │   └── KubeTEEGitHubRegistryV2.sol  # For upgrades
│       ├── scripts/
│       │   └── deploy.js
│       ├── test/
│       │   └── KubeTEEGitHubRegistry.test.js
│       ├── hardhat.config.js
│       └── package.json
│
├── neurons/                          # Bittensor neurons
│   ├── validator.py
│   └── miner.py
│
└── docs/
    └── GITHUB_LINKING_ARCHITECTURE.md
```

---

## Smart Contract: Events-Based Storage

### Why Events Instead of Storage?

| Approach | Gas Cost | Read Cost | Implementation |
|----------|----------|-----------|----------------|
| **Storage (mapping)** | ~20,000 gas per write | Direct call | Simple |
| **Events only** ⭐ | ~2,000 gas per emit | Off-chain indexing | Cheaper |

**Decision:** Use events for storage. Validator loads all events on startup into in-memory cache.

### Contract Design

```solidity
// SPDX-License-Identifier: MIT
pragma solidity ^0.8.19;

import "@openzeppelin/contracts-upgradeable/access/OwnableUpgradeable.sol";
import "@openzeppelin/contracts-upgradeable/proxy/utils/Initializable.sol";
import "@openzeppelin/contracts-upgradeable/proxy/utils/UUPSUpgradeable.sol";

/**
 * @title KubeTEEGitHubRegistry
 * @notice Links Bittensor hotkeys to GitHub accounts via events
 * @dev Upgradeable (UUPS pattern), events-based storage for gas efficiency
 */
contract KubeTEEGitHubRegistry is 
    Initializable, 
    OwnableUpgradeable, 
    UUPSUpgradeable 
{
    // Validator whitelist
    mapping(address => bool) public isValidator;
    
    // Events (primary data storage)
    event GitHubLinked(
        string indexed hotkeyHash,    // Indexed for filtering
        string hotkey,                // Full hotkey
        uint256 mechanismId,
        string githubUsername,
        address validator,
        uint256 timestamp
    );
    
    event ValidatorAdded(address indexed validator);
    event ValidatorRemoved(address indexed validator);
    
    modifier onlyValidator() {
        require(isValidator[msg.sender], "Only validators");
        _;
    }
    
    /// @custom:oz-upgrades-unsafe-allow constructor
    constructor() {
        _disableInitializers();
    }
    
    function initialize() public initializer {
        __Ownable_init(msg.sender);
        __UUPSUpgradeable_init();
    }
    
    function _authorizeUpgrade(address newImplementation) internal override onlyOwner {}
    
    /**
     * @notice Add a validator to whitelist
     */
    function addValidator(address validator) external onlyOwner {
        isValidator[validator] = true;
        emit ValidatorAdded(validator);
    }
    
    /**
     * @notice Remove a validator from whitelist
     */
    function removeValidator(address validator) external onlyOwner {
        isValidator[validator] = false;
        emit ValidatorRemoved(validator);
    }
    
    /**
     * @notice Link hotkey to GitHub (emits event, no storage)
     * @param hotkey Bittensor SS58 hotkey
     * @param mechanismId Mechanism ID (0 = bounty, etc.)
     * @param githubUsername GitHub username
     */
    function linkGitHub(
        string calldata hotkey,
        uint256 mechanismId,
        string calldata githubUsername
    ) external onlyValidator {
        emit GitHubLinked(
            hotkey,              // Will be hashed for indexing
            hotkey,              // Full value
            mechanismId,
            githubUsername,
            msg.sender,
            block.timestamp
        );
    }
}
```

---

## Validator: Event Loading on Startup

```python
# kubetee/validator/github_registry.py

from web3 import Web3
from typing import Dict, Optional

class GitHubRegistry:
    """
    Manages GitHub-hotkey links via smart contract events.
    
    On startup, loads all GitHubLinked events into memory.
    New links are written to contract and cached locally.
    """
    
    def __init__(self, web3: Web3, contract_address: str, contract_abi: list):
        self.web3 = web3
        self.contract = web3.eth.contract(
            address=contract_address, 
            abi=contract_abi
        )
        
        # In-memory cache: hotkey → {mechanism_id → github_username}
        self._cache: Dict[str, Dict[int, str]] = {}
        
    async def load_events_on_startup(self):
        """
        Load all GitHubLinked events from contract into cache.
        Called once when validator starts.
        """
        # Get all events from block 0 to latest
        events = self.contract.events.GitHubLinked.get_logs(
            fromBlock=0,
            toBlock='latest'
        )
        
        for event in events:
            hotkey = event.args.hotkey
            mechanism_id = event.args.mechanismId
            github = event.args.githubUsername
            
            if hotkey not in self._cache:
                self._cache[hotkey] = {}
            
            # Latest event wins (in case of updates)
            self._cache[hotkey][mechanism_id] = github
        
        print(f"Loaded {len(events)} GitHubLinked events into cache")
    
    def get_github(self, hotkey: str, mechanism_id: int = 0) -> Optional[str]:
        """Get cached GitHub username for hotkey."""
        return self._cache.get(hotkey, {}).get(mechanism_id)
    
    def is_linked(self, hotkey: str, mechanism_id: int = 0) -> bool:
        """Check if hotkey is already linked."""
        return self.get_github(hotkey, mechanism_id) is not None
    
    async def link_github(
        self,
        hotkey: str,
        mechanism_id: int,
        github_username: str,
        validator_key: str
    ) -> tuple[str | None, str]:
        """
        Write link to contract if new or changed.
        
        Returns:
            (tx_hash, status) where status is: "created", "updated", "unchanged"
        
        Logic:
            1. Check cache - is hotkey already linked?
            2. If not linked → write new event ("created")
            3. If linked but GitHub URL changed → write update event ("updated")
            4. If same → skip ("unchanged", no gas spent)
        """
        existing = self.get_github(hotkey, mechanism_id)
        
        # Same link already exists - no write needed
        if existing == github_username:
            return (None, "unchanged")
        
        # Determine status
        status = "created" if existing is None else "updated"
        
        # Build transaction
        tx = self.contract.functions.linkGitHub(
            hotkey,
            mechanism_id,
            github_username
        ).build_transaction({
            'from': self.web3.eth.account.from_key(validator_key).address,
            'nonce': self.web3.eth.get_transaction_count(
                self.web3.eth.account.from_key(validator_key).address
            ),
            'gas': 100000,
            'gasPrice': self.web3.eth.gas_price
        })
        
        # Sign and send
        signed = self.web3.eth.account.sign_transaction(tx, validator_key)
        tx_hash = self.web3.eth.send_raw_transaction(signed.rawTransaction)
        
        # Update local cache immediately
        if hotkey not in self._cache:
            self._cache[hotkey] = {}
        self._cache[hotkey][mechanism_id] = github_username
        
        return (tx_hash.hex(), status)
```

---

## Hardhat Setup

### `kubetee/contracts/package.json`

```json
{
  "name": "kubetee-contracts",
  "version": "1.0.0",
  "scripts": {
    "compile": "hardhat compile",
    "test": "hardhat test",
    "node": "hardhat node",
    "deploy:local": "hardhat run scripts/deploy.js --network localhost",
    "deploy:testnet": "hardhat run scripts/deploy.js --network bittensor_testnet"
  },
  "devDependencies": {
    "@nomicfoundation/hardhat-toolbox": "^4.0.0",
    "@openzeppelin/contracts-upgradeable": "^5.0.0",
    "@openzeppelin/hardhat-upgrades": "^3.0.0",
    "hardhat": "^2.19.0"
  }
}
```

### `kubetee/contracts/hardhat.config.js`

```javascript
require("@nomicfoundation/hardhat-toolbox");
require("@openzeppelin/hardhat-upgrades");

module.exports = {
  solidity: "0.8.19",
  networks: {
    // Local in-memory node for testing
    hardhat: {
      chainId: 31337
    },
    localhost: {
      url: "http://127.0.0.1:8545"
    },
    // Bittensor EVM
    bittensor_evm: {
      url: "https://evm.bittensor.network",
      chainId: 945,
      accounts: process.env.DEPLOYER_KEY ? [process.env.DEPLOYER_KEY] : []
    }
  }
};
```

### `kubetee/contracts/test/KubeTEEGitHubRegistry.test.js`

```javascript
const { expect } = require("chai");
const { ethers, upgrades } = require("hardhat");

describe("KubeTEEGitHubRegistry", function () {
  let registry;
  let owner, validator, nonValidator;
  
  beforeEach(async function () {
    [owner, validator, nonValidator] = await ethers.getSigners();
    
    const Registry = await ethers.getContractFactory("KubeTEEGitHubRegistry");
    registry = await upgrades.deployProxy(Registry, [], { 
      initializer: 'initialize' 
    });
    await registry.waitForDeployment();
    
    // Add validator to whitelist
    await registry.addValidator(validator.address);
  });
  
  describe("Validator Management", function () {
    it("should add validator", async function () {
      expect(await registry.isValidator(validator.address)).to.be.true;
    });
    
    it("should remove validator", async function () {
      await registry.removeValidator(validator.address);
      expect(await registry.isValidator(validator.address)).to.be.false;
    });
    
    it("should reject non-owner adding validator", async function () {
      await expect(
        registry.connect(nonValidator).addValidator(nonValidator.address)
      ).to.be.reverted;
    });
  });
  
  describe("GitHub Linking", function () {
    it("should emit GitHubLinked event", async function () {
      const hotkey = "5GrwvaEF5zXb26Fz9rcQpDWS57CtERHpNehXCPcNoHGKutQY";
      const mechanismId = 0;
      const github = "alice";
      
      await expect(
        registry.connect(validator).linkGitHub(hotkey, mechanismId, github)
      ).to.emit(registry, "GitHubLinked")
        .withArgs(
          hotkey,  // indexed
          hotkey,  // full
          mechanismId,
          github,
          validator.address,
          // timestamp is dynamic
        );
    });
    
    it("should reject non-validator linking", async function () {
      await expect(
        registry.connect(nonValidator).linkGitHub("hotkey", 0, "user")
      ).to.be.revertedWith("Only validators");
    });
  });
  
  describe("Upgradeability", function () {
    it("should upgrade to V2", async function () {
      const RegistryV2 = await ethers.getContractFactory("KubeTEEGitHubRegistryV2");
      const upgraded = await upgrades.upgradeProxy(
        await registry.getAddress(),
        RegistryV2
      );
      
      // V2 should have new functionality
      expect(await upgraded.version()).to.equal("2.0.0");
    });
  });
});
```

---

## Validation Checks

```
┌─────────────────────────────────────────────────────────────────┐
│                    6 VALIDATION CHECKS                          │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  [A] SUBNET REGISTRATION                                        │
│      Query Substrate: Is hotkey registered on subnet?           │
│                                                                 │
│  [B] SIGNATURE VERIFICATION                                     │
│      Verify signature matches the claimed hotkey                │
│                                                                 │
│  [C] GIST EXISTS                                                │
│      GET api.github.com/gists/{id} → status 200, public        │
│                                                                 │
│  [D] HOTKEY IN GIST                                             │
│      Parse HOTKEY.md, extract hotkey field                      │
│                                                                 │
│  [E] HOTKEY MATCH                                               │
│      claimed == signed == gist (all three identical)            │
│                                                                 │
│  [F] GITHUB USER EXISTS                                         │
│      GET api.github.com/users/{owner} → status 200             │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## Security Summary

| Threat | Prevention |
|--------|------------|
| Claim someone else's GitHub | Gist owner = your account |
| Use unregistered hotkey | Check subnet registration |
| Forge signature | Cryptographic verification |
| Spam contract | Validator-only writes |
| Hotkey mismatch | Three-way check |
| Contract bugs | Upgradeable (UUPS proxy) |

---

## Implementation Tasks (for Orchestrator)

### Task 1: Project Structure Setup
**Mode:** Code
**Priority:** 1 (First)
**Description:** Create the `kubetee/` package structure with empty `__init__.py` files.

```
kubetee-subnet/kubetee/
├── __init__.py
├── cli/__init__.py
├── api/__init__.py
├── validator/__init__.py
├── miner/__init__.py
└── contracts/   (empty dir for now)
```

**Acceptance:** All directories and `__init__.py` files exist.

---

### Task 2: Hardhat Project Setup
**Mode:** Code
**Priority:** 2
**Description:** Initialize Hardhat project inside `kubetee/contracts/` with OpenZeppelin upgrades.

**Files to create:**
- `kubetee/contracts/package.json`
- `kubetee/contracts/hardhat.config.js`
- `kubetee/contracts/.gitignore`

**Commands to document:**
```bash
cd kubetee/contracts
npm install
```

**Acceptance:** `npm install` succeeds, `npx hardhat compile` works (even with no contracts yet).

---

### Task 3: Smart Contract Implementation
**Mode:** Code
**Priority:** 3
**Description:** Implement the upgradeable GitHub registry contract.

**Files to create:**
- `kubetee/contracts/contracts/KubeTEEGitHubRegistry.sol`
- `kubetee/contracts/contracts/KubeTEEGitHubRegistryV2.sol` (stub for upgrade tests)
- `kubetee/contracts/scripts/deploy.js`

**Requirements:**
- UUPS upgradeable (OpenZeppelin)
- Events-based storage (no mapping for links)
- `onlyValidator` modifier
- `linkGitHub(hotkey, mechanismId, githubUsername)` function

**Acceptance:** `npx hardhat compile` succeeds with no errors.

---

### Task 4: Smart Contract Tests
**Mode:** Code
**Priority:** 4
**Description:** Write comprehensive Hardhat tests for the contract.

**Files to create:**
- `kubetee/contracts/test/KubeTEEGitHubRegistry.test.js`

**Test cases:**
- Validator management (add/remove)
- Event emission on linkGitHub
- Non-validator rejection
- Upgrade to V2

**Acceptance:** `npx hardhat test` passes all tests.

---

### Task 5: Validator GitHub Registry (Python)
**Mode:** Code
**Priority:** 5
**Description:** Implement the validator-side GitHub registry with event loading and caching.

**Files to create:**
- `kubetee/validator/github_registry.py`

**Requirements:**
- `load_events_on_startup()` - Load all events into cache
- `get_github(hotkey, mechanism_id)` - Read from cache
- `is_linked(hotkey, mechanism_id)` - Check if linked
- `link_github(...)` - Write to contract if new/changed, update cache
- Cache decision logic: skip if unchanged, write if new/updated

**Dependencies:** `web3`, `httpx`

**Acceptance:** Unit tests pass (mock contract).

---

### Task 6: GitHub Verification Logic (Python)
**Mode:** Code
**Priority:** 6
**Description:** Implement the 6 validation checks for link requests.

**Add to `kubetee/validator/github_registry.py` or create `kubetee/validator/github_verifier.py`**

**Functions:**
- `verify_subnet_registration(hotkey, subtensor, netuid)` - Check A
- `verify_signature(message, signature, hotkey)` - Check B
- `verify_gist(gist_url, expected_hotkey)` - Checks C, D, E
- `verify_github_user(username)` - Check F

**Acceptance:** All verification functions work, tested with mocks.

---

### Task 7: Validator API Endpoint
**Mode:** Code
**Priority:** 7
**Description:** Create FastAPI endpoint for miner registration.

**Files to create:**
- `kubetee/api/github.py`

**Endpoint:**
```
POST /api/github/link
Body: {hotkey, gist_url, signature, message}
Response: {success, github_username?, tx_hash?, error?}
```

**Requirements:**
- Call all 6 verification checks
- Call `link_github()` if all pass
- Return appropriate error codes

**Acceptance:** API endpoint responds correctly to valid/invalid requests.

---

### Task 8: CLI Command
**Mode:** Code
**Priority:** 8
**Description:** Implement `kubetee link-github` CLI command.

**Files to create:**
- `kubetee/cli/github.py`
- Update `kubetee/cli/__init__.py` to register command

**Commands:**
```bash
kubetee link-github --generate --hotkey 5Grw...
kubetee link-github --hotkey 5Grw... --gist https://gist.github.com/...
```

**Requirements:**
- `--generate` mode outputs HOTKEY.md content
- Normal mode signs message and POSTs to validator API
- Load hotkey from wallet or via `--hotkey` flag

**Acceptance:** CLI works end-to-end with running validator.

---

### Task 9: Integration Tests
**Mode:** Code
**Priority:** 9
**Description:** End-to-end integration tests with local Hardhat node.

**Files to create:**
- `kubetee/tests/test_github_linking_integration.py`

**Test flow:**
1. Start Hardhat node
2. Deploy contract
3. Start validator API
4. Run CLI command
5. Verify event emitted
6. Verify cache updated

**Acceptance:** Full flow works locally.

---

### Task 10: Documentation
**Mode:** Code
**Priority:** 10 (Last)
**Description:** Update README and add usage examples.

**Files to update/create:**
- `kubetee-subnet/README.md` - Add GitHub linking section
- `kubetee/contracts/README.md` - Contract deployment guide

**Acceptance:** New user can follow docs to set up and use feature.

---

## Task Dependencies

```
Task 1 (Structure)
    ↓
Task 2 (Hardhat)
    ↓
Task 3 (Contract) ────────────────┐
    ↓                             │
Task 4 (Contract Tests)           │
                                  ↓
Task 5 (Validator Registry) ←─────┘
    ↓
Task 6 (Verification Logic)
    ↓
Task 7 (API Endpoint)
    ↓
Task 8 (CLI)
    ↓
Task 9 (Integration Tests)
    ↓
Task 10 (Documentation)
```
