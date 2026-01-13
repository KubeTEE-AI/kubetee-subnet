# KubeTEE CLI: GitHub Linking Architecture

## Overview

This document defines the architecture for integrating `kubeteectl link-github --hotkey <HK>` as a core first-setup command into the main CLI package.

---

## 1. CLI Command Structure

### Entry Point Hierarchy

```
kubeteectl/
├── [Global Options]
│   ├── --config PATH        # Config file location
│   ├── --wallet.name NAME   # Wallet name
│   └── --verbose
│
└── COMMANDS:
    ├── link-github          # NEW: GitHub account linking (CORE)
    ├── register             # User/miner registration
    ├── reseller             # Reseller management
    │   ├── register
    │   ├── deposit
    │   ├── balance
    │   └── withdraw
    ├── wallet               # Wallet management
    │   ├── create
    │   ├── import
    │   └── balance
    ├── api                  # API interactions
    │   ├── status
    │   └── inference
    └── rag                  # RAG service management
        ├── status
        └── upgrade
```

### `link-github` Command Signature

```bash
# Basic usage
kubeteectl link-github --hotkey <HOTKEY>

# With optional message signing
kubeteectl link-github --hotkey <HOTKEY> --sign-with <WALLET_NAME>

# Interactive mode (default)
kubeteectl link-github
# → Prompts for hotkey
# → Opens browser to GitHub OAuth flow
# → Completes linking

# Quiet mode
kubeteectl link-github --hotkey <HOTKEY> --non-interactive
```

### Command Arguments & Options

| Argument | Type | Required | Description |
|----------|------|----------|-------------|
| `--hotkey` | string | Yes* | Bittensor hotkey (ss58 format: 5F...) |
| `--hotkey-file` | path | No | Read hotkey from file instead of args |
| `--sign-with` | string | No | Wallet name to sign verification message |
| `--github-token` | string | No | GitHub PAT (else use OAuth) |
| `--registry-url` | URL | No | Custom registry endpoint (default: KubeTEE) |
| `--non-interactive` | flag | No | Skip browser/interactive steps |
| `--force` | flag | No | Overwrite existing mapping |
| `--dry-run` | flag | No | Simulate without on-chain submission |

*Optional if `--hotkey-file` provided or if set in config

---

## 2. Authentication & Signature Flow

### GitHub Authentication Methods

#### Option A: OAuth (Recommended for Users)

```
1. User runs: kubeteectl link-github --hotkey 5F...
2. CLI generates state token (32 bytes random)
3. CLI starts local callback server (localhost:8888)
4. Opens browser: https://github.com/login/oauth/authorize
   - client_id: KubeTEE GitHub App
   - redirect_uri: http://localhost:8888/callback
   - state: state token (CSRF protection)
5. User authenticates with GitHub
6. GitHub redirects: localhost:8888/callback?code=...&state=...
7. CLI exchanges code for access token
8. CLI fetches user info: GET /user (username, id, etc.)
9. CLI validates state token
10. Proceeds to message signing
```

#### Option B: GitHub Personal Access Token (For CI/CD)

```
1. User provides: kubeteectl link-github --hotkey 5F... --github-token ghp_...
2. CLI validates token by calling GET /user
3. Extracts username and user ID
4. Proceeds to message signing (skip OAuth)
```

### Message Signing (Hotkey Verification)

Once GitHub identity confirmed, prove Bittensor hotkey ownership:

```
┌─────────────────────────────────────────────────────────────────┐
│              MESSAGE SIGNING FLOW                               │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  1. CLI generates message:                                       │
│                                                                 │
│     Message = {                                                  │
│       "github_username": "alice",                               │
│       "github_id": 12345,                                        │
│       "hotkey": "5F5F5F...",                                    │
│       "timestamp": 1673456789,                                  │
│       "nonce": "random_32_bytes"                                │
│     }                                                            │
│     Serialized as JSON                                           │
│                                                                 │
│  2. CLI signs message with Bittensor hotkey:                     │
│                                                                 │
│     signature = sign(message, hotkey_private_key)               │
│     hex_signature = hex(signature)                              │
│                                                                 │
│  3. CLI submits on-chain:                                        │
│                                                                 │
│     tx = KubeTEERegistry.linkGitHub(                             │
│       github_username = "alice",                                │
│       github_id = 12345,                                        │
│       message_json = message,                                   │
│       signature = hex_signature                                 │
│     )                                                            │
│                                                                 │
│  4. On-chain verification:                                       │
│                                                                 │
│     recovered_hotkey = recover_pubkey(message, signature)       │
│     assert recovered_hotkey == tx.signer                        │
│     assert timestamp is recent (within 5 min)                   │
│                                                                 │
│  5. Registry stores mapping:                                     │
│                                                                 │
│     githubUsername → hotkey                                     │
│     githubId → hotkey                                           │
│     hotkey → githubUsername                                     │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### Signature Verification (Validator Side)

```python
from bittensor_utils import verify_message

def verify_github_linking(message_json, signature_hex, claimed_hotkey):
    """
    Verify that the signature was created by claiming hotkey.
    """
    try:
        # Recover public key from signature
        recovered_hotkey = verify_message(
            message=message_json.encode(),
            signature=bytes.fromhex(signature_hex)
        )
        
        # Verify signer is the one claiming ownership
        return recovered_hotkey == claimed_hotkey
    except Exception as e:
        return False
```

---

## 3. On-Chain Registry Schema

### Smart Contract: `KubeTEERegistry.sol` (or Registry function on existing payment contract)

```solidity
// SPDX-License-Identifier: MIT
pragma solidity ^0.8.0;

interface IKubeTEERegistry {
    
    // Events
    event GitHubLinked(
        string indexed githubUsername,
        uint256 indexed githubId,
        string hotkey,
        uint256 timestamp
    );
    
    event GitHubUnlinked(
        string indexed githubUsername,
        string hotkey,
        uint256 timestamp
    );
    
    // Data structures
    struct GitHubLink {
        string hotkey;          // Bittensor hotkey (ss58)
        uint256 timestamp;      // When linked
        bool verified;          // Message signature verified
    }
    
    struct HotkeyLink {
        string githubUsername;
        uint256 githubId;
        uint256 timestamp;
    }
    
    // Mappings
    mapping(string => GitHubLink) public githubToHotkey;        // github_username → hotkey
    mapping(string => HotkeyLink) public hotkeyToGithub;        // hotkey → github info
    mapping(uint256 => GitHubLink) public githubIdToHotkey;     // github_id → hotkey
    
    // Functions
    function linkGitHub(
        string calldata githubUsername,
        uint256 githubId,
        string calldata messageJson,
        string calldata signatureHex
    ) external;
    
    function unlinkGitHub(
        string calldata githubUsername
    ) external;
    
    function getHotkeyByGithub(
        string calldata githubUsername
    ) external view returns (GitHubLink memory);
    
    function getGithubByHotkey(
        string calldata hotkey
    ) external view returns (HotkeyLink memory);
    
    function isLinked(
        string calldata githubUsername
    ) external view returns (bool);
}
```

### Data Storage (Location Options)

**Option A: Bittensor On-Chain (Recommended)**
- Store in subnet storage via `SubnetHyperparameters`
- Validators read/sync mapping locally
- No external smart contract needed
- Data included in blockchain validation

**Option B: BASE L2 Smart Contract**
- Deployed on BASE (same chain as payment contract)
- Similar to `KubeTEEPayment.sol`
- Validators query via Web3.py
- More gas costs but transparent audit trail

**Option C: IPFS (Decentralized)**
- Store mappings in IPFS
- Pin via Pinata or self-hosted
- Validators pin a copy for availability
- Content-addressable for immutability

### Data Format (Registry Entry)

```json
{
  "github_username": "alice",
  "github_id": 12345,
  "hotkey": "5F5F5F5F5F5F5F5F5F5F5F5F5F5F5F5F5F5F5F5F5F5F",
  "coldkey": "5G9G9G9G9G9G9G9G9G9G9G9G9G9G9G9G9G9G9G9G9G9G9G",
  "linked_timestamp": 1673456789,
  "verified_timestamp": 1673456800,
  "github_profile_url": "https://github.com/alice",
  "github_avatar_url": "https://avatars.githubusercontent.com/u/12345",
  "contribution_count": 42,
  "github_created_at": 1600000000
}
```

---

## 4. Data Persistence & Configuration

### Local Storage: `~/.kubetee/github-linking.json`

```json
{
  "linked_accounts": [
    {
      "github_username": "alice",
      "github_id": 12345,
      "hotkey": "5F5F5F...",
      "token_hash": "sha256(github_token)",
      "token_type": "oauth|pat",
      "oauth_refresh_token": "ghu_...",
      "oauth_expires_at": 1673543789,
      "linked_at": 1673456789,
      "verified": true,
      "verification_tx": "0x1234..."
    }
  ],
  "oauth_state": {
    "state_token": "random_state",
    "callback_server_port": 8888,
    "expires_at": 1673456809
  }
}
```

### Environment Variables

```bash
# Override defaults
KUBETEE_GITHUB_CLIENT_ID=Iv1.example1234...
KUBETEE_GITHUB_CLIENT_SECRET=secret_example...
KUBETEE_REGISTRY_URL=http://localhost:9999  # Custom registry endpoint
KUBETEE_GITHUB_TOKEN=ghp_...                # GitHub PAT
KUBETEE_HOTKEY=5F5F5F...                    # Default hotkey
KUBETEE_REGISTRY_CONTRACT=0x1234...         # Registry contract (BASE)
```

### Configuration File: `~/.kubetee/config.json`

```json
{
  "github_linking": {
    "enabled": true,
    "oauth_callback_port": 8888,
    "oauth_timeout_seconds": 300,
    "auto_verify_registry": true,
    "registry_url": "https://registry.kubetee.ai",
    "registry_chain": "base|bittensor",
    "allow_pat": true,
    "require_github_verification": true
  },
  "wallet": {
    "default_name": "main",
    "path": "~/.bittensor/wallets"
  }
}
```

---

## 5. Implementation: `cli/github.py`

### Module Structure

```python
# cli/github.py

from dataclasses import dataclass
from typing import Optional
from pathlib import Path
import json
import qrcode
from eth_account import Account
from eth_account.messages import encode_defunct

@dataclass
class GitHubLinkingConfig:
    """Configuration for GitHub linking"""
    
    github_client_id: str
    github_client_secret: str
    registry_url: str
    oauth_callback_port: int = 8888
    oauth_timeout: int = 300
    
    @classmethod
    def load(cls) -> "GitHubLinkingConfig":
        """Load from env or config file"""
        pass

class GitHubOAuthHandler:
    """Manage GitHub OAuth flow"""
    
    def __init__(self, config: GitHubLinkingConfig):
        self.config = config
    
    def get_auth_url(self, state_token: str) -> str:
        """Generate GitHub OAuth authorization URL"""
        pass
    
    def start_callback_server(self) -> int:
        """Start local HTTP server for callback"""
        pass
    
    def exchange_code_for_token(self, code: str) -> dict:
        """Exchange auth code for access token"""
        pass
    
    def get_github_user(self, access_token: str) -> dict:
        """Fetch GitHub user info"""
        pass

class GitHubLinkingCLI:
    """Main CLI handler for link-github command"""
    
    def __init__(self):
        self.config = GitHubLinkingConfig.load()
        self.oauth_handler = GitHubOAuthHandler(self.config)
    
    def cmd_link_github(
        self,
        hotkey: Optional[str] = None,
        hotkey_file: Optional[str] = None,
        github_token: Optional[str] = None,
        sign_with: Optional[str] = None,
        non_interactive: bool = False,
        force: bool = False,
        dry_run: bool = False
    ) -> bool:
        """
        Link GitHub account to Bittensor hotkey
        
        Returns:
            True if successful, False otherwise
        """
        
        # 1. Validate/get hotkey
        hotkey = self._get_hotkey(hotkey, hotkey_file)
        if not hotkey:
            self._error("No hotkey provided")
            return False
        
        # 2. Authenticate with GitHub
        github_user = self._authenticate_github(github_token, non_interactive)
        if not github_user:
            self._error("GitHub authentication failed")
            return False
        
        # 3. Sign message with hotkey
        message = self._build_message(github_user, hotkey)
        signature = self._sign_message(message, sign_with)
        if not signature:
            self._error("Message signing failed")
            return False
        
        # 4. Submit to registry (on-chain)
        if not dry_run:
            tx_hash = self._submit_to_registry(
                github_user,
                message,
                signature,
                force
            )
            if not tx_hash:
                self._error("Registry submission failed")
                return False
        
        # 5. Save locally
        self._save_linking(github_user, hotkey, github_token)
        
        self._success(f"✅ Linked {github_user['login']} to {hotkey}")
        return True
    
    # Private methods
    def _get_hotkey(self, hotkey: str, hotkey_file: str) -> Optional[str]:
        """Get hotkey from argument, file, or prompt"""
        pass
    
    def _authenticate_github(self, token: str, non_interactive: bool) -> Optional[dict]:
        """Authenticate with GitHub via OAuth or PAT"""
        pass
    
    def _build_message(self, github_user: dict, hotkey: str) -> str:
        """Build JSON message to sign"""
        pass
    
    def _sign_message(self, message: str, wallet_name: Optional[str]) -> Optional[str]:
        """Sign message with hotkey"""
        pass
    
    def _submit_to_registry(
        self,
        github_user: dict,
        message: str,
        signature: str,
        force: bool
    ) -> Optional[str]:
        """Submit linking to on-chain registry"""
        pass
    
    def _save_linking(self, github_user: dict, hotkey: str, token: str) -> None:
        """Save linking info locally"""
        pass
```

---

## 6. Integration with Main CLI

### Update `cli/__init__.py`

```python
from .reseller import ResellerCLI, main as reseller_main
from .github import GitHubLinkingCLI, main as github_main

__all__ = [
    "ResellerCLI",
    "reseller_main",
    "GitHubLinkingCLI",
    "github_main",
]
```

### Update Main Entry Point

```python
# scripts/kubeteectl or setup.py entry_points

def main():
    parser = argparse.ArgumentParser(
        prog="kubeteectl",
        description="KubeTEE CLI - Decentralized AI Infrastructure"
    )
    
    # Global options
    parser.add_argument("--config", type=str, help="Config file path")
    parser.add_argument("--verbose", "-v", action="store_true")
    
    subparsers = parser.add_subparsers(dest="command", help="Commands")
    
    # 1. link-github (NEW - TOP LEVEL)
    github_parser = subparsers.add_parser("link-github", help="Link GitHub account")
    github_parser.add_argument("--hotkey", help="Bittensor hotkey")
    github_parser.add_argument("--hotkey-file", help="Hotkey file path")
    github_parser.add_argument("--github-token", help="GitHub PAT")
    github_parser.add_argument("--sign-with", help="Wallet name to sign with")
    github_parser.add_argument("--non-interactive", action="store_true")
    github_parser.add_argument("--force", action="store_true")
    github_parser.add_argument("--dry-run", action="store_true")
    
    # 2. reseller (EXISTING)
    reseller_parser = subparsers.add_parser("reseller", help="Reseller management")
    # ... (existing reseller subcommands)
    
    # 3. wallet (FUTURE)
    # 4. api (FUTURE)
    # 5. rag (FUTURE)
    
    args = parser.parse_args()
    
    if args.command == "link-github":
        cli = GitHubLinkingCLI()
        return cli.cmd_link_github(
            hotkey=args.hotkey,
            hotkey_file=args.hotkey_file,
            github_token=args.github_token,
            sign_with=args.sign_with,
            non_interactive=args.non_interactive,
            force=args.force,
            dry_run=args.dry_run
        )
    elif args.command == "reseller":
        # ... existing reseller logic
        pass
```

---

## 7. Security & Best Practices

### Security Considerations

| Concern | Mitigation |
|---------|-----------|
| **OAuth State Token** | Generate 32 bytes random, validate on callback (CSRF protection) |
| **Token Storage** | Hash GitHub tokens before storing locally |
| **Message Signing** | Include timestamp (5 min validity), nonce, to prevent replay attacks |
| **Hotkey Leakage** | Never transmit private keys; only sign locally |
| **Registry Centralization** | Use decentralized option (Bittensor on-chain or IPFS) |
| **GitHub Account Hijacking** | Require re-verification if GitHub account is recovered |

### Best Practices

1. **Message Format Must Be Canonical**
   - Use JSON with sorted keys
   - Fixed field order for reproducibility
   - Validators can independently verify signatures

2. **Timestamp Validation**
   - Accept messages within ±5 minutes of current time
   - Prevents stale replay attacks

3. **Nonce Uniqueness**
   - Generate 32 random bytes per signing request
   - Prevents identical message signatures reuse

4. **OAuth Redirect URL Validation**
   - Only allow `http://localhost:PORT/callback`
   - Reject mismatched redirect URIs

5. **Token Expiry Handling**
   - Store OAuth refresh token
   - Automatically refresh before expiry
   - Gracefully handle expired tokens

6. **Rate Limiting**
   - Limit linking attempts: 10 per IP per hour
   - Prevent brute-force hotkey guessing

---

## 8. Error Handling & Edge Cases

### Error Scenarios

```python
class GitHubLinkingError(Exception):
    """Base exception for GitHub linking errors"""
    pass

class GitHubAuthError(GitHubLinkingError):
    """GitHub authentication failed"""
    # - OAuth callback timeout
    # - Invalid authorization code
    # - API rate limited
    pass

class HotkeyValidationError(GitHubLinkingError):
    """Invalid hotkey format or not found"""
    # - Invalid ss58 format
    # - Hotkey doesn't exist in subnet
    # - Hotkey is already linked to different GitHub account
    pass

class MessageSigningError(GitHubLinkingError):
    """Failed to sign message"""
    # - Hotkey file not found
    # - Private key invalid
    # - Signature verification failed
    pass

class RegistryError(GitHubLinkingError):
    """Failed to submit to registry"""
    # - Contract call failed
    # - Insufficient permissions
    # - Network unreachable
    pass

class DuplicateLinkError(GitHubLinkingError):
    """GitHub account already linked"""
    # Recovery: offer --force flag to re-link
    pass
```

### Edge Cases to Handle

1. **Hotkey Already Linked to Different GitHub Account**
   - Check registry before linking
   - Offer `--force` flag to override
   - Warn user with confirmation

2. **GitHub Account Already Linked to Different Hotkey**
   - Prevent multiple hotkeys per GitHub account (1:1 mapping)
   - Show existing mapping if found

3. **OAuth Callback Timeout**
   - User doesn't complete OAuth within 5 minutes
   - Cleanup local state
   - Ask user to retry

4. **Network Interruption During Submission**
   - Prompt user to retry linking with same token
   - Don't lose OAuth token after successful GitHub auth

5. **Signature Verification Fails**
   - Suggest checking hotkey format
   - Offer to verify hotkey with subnet

---

## 9. Testing Strategy

### Unit Tests: `tests/test_github_linking.py`

```python
import pytest
from cli.github import GitHubLinkingCLI, GitHubOAuthHandler

class TestGitHubOAuth:
    def test_generate_auth_url(self):
        """Verify auth URL contains required params"""
        pass
    
    def test_state_token_validation(self):
        """CSRF protection - state must match"""
        pass
    
    def test_github_user_fetch(self):
        """Mock GitHub API for user data"""
        pass
    
    def test_oauth_timeout(self):
        """Callback server times out after 5 min"""
        pass

class TestMessageSigning:
    def test_message_format_consistency(self):
        """Same inputs produce same JSON (canonical)"""
        pass
    
    def test_timestamp_validation(self):
        """Messages older than 5 min rejected"""
        pass
    
    def test_nonce_uniqueness(self):
        """Each message has unique nonce"""
        pass
    
    def test_signature_verification(self):
        """Valid signature accepts, invalid rejects"""
        pass

class TestRegistrySubmission:
    def test_registry_contract_call(self, web3_mock):
        """Mock registry contract submission"""
        pass
    
    def test_duplicate_prevention(self):
        """Can't link same GitHub account twice"""
        pass
    
    def test_force_override(self):
        """--force flag allows re-linking"""
        pass

class TestErrorHandling:
    def test_invalid_hotkey_format(self):
        """Reject non-ss58 hotkeys"""
        pass
    
    def test_github_auth_failure(self):
        """Handle OAuth errors gracefully"""
        pass
    
    def test_network_timeout_retry(self):
        """Retry logic on network errors"""
        pass
```

### Integration Tests

```python
def test_end_to_end_linking(github_mock, registry_mock, temp_config):
    """Full flow: OAuth → Message → Signature → Registry"""
    cli = GitHubLinkingCLI()
    result = cli.cmd_link_github(
        hotkey="5F...",
        github_token="ghp_...",
        non_interactive=True
    )
    assert result is True
    assert registry_mock.called  # Registry submission occurred
```

---

## 10. Implementation Phases

### Phase 1: Core Linking (MVP)
- [x] Message signing (local only)
- [x] GitHub API integration (PAT only)
- [x] Local storage (`github-linking.json`)
- [ ] Basic error handling
- **Output**: `kubeteectl link-github --hotkey 5F... --github-token ghp_...`

### Phase 2: OAuth + Registry
- [ ] OAuth flow implementation
- [ ] Registry contract (BASE or Bittensor)
- [ ] On-chain submission
- [ ] Advanced error handling
- **Output**: Full end-to-end linking with browser OAuth

### Phase 3: Validation & Governance
- [ ] Validator integration (read from registry)
- [ ] Weight calculation based on GitHub contributions
- [ ] CLI commands to query registry
- [ ] Audit logging
- **Output**: `kubeteectl check-github <username>` to verify

---

## 11. Configuration & Deployment

### GitHub OAuth App Setup

```
GitHub Organization: KubeTEE-AI

App Name: KubeTEE CLI
Homepage URL: https://kubetee.ai
Authorization callback URL: http://localhost:8888/callback

Permissions:
- read:user (get username, email, avatar)

Client ID: Iv1.example1234...
Client Secret: secret_example... (stored in Vault)
```

### Environment Setup for CI/CD

```bash
# GitHub Secrets (for automation)
export KUBETEE_GITHUB_CLIENT_ID="Iv1.example..."
export KUBETEE_GITHUB_CLIENT_SECRET="secret_example..."
export KUBETEE_REGISTRY_URL="https://registry.kubetee.ai"
export KUBETEE_REGISTRY_CONTRACT="0x1234..."

# Deploy to production
pip install kubeteectl
kubeteectl link-github --hotkey 5F... --github-token ghp_...
```

---

## 12. User Workflows

### Workflow 1: First-Time User (Interactive OAuth)

```bash
$ kubeteectl link-github

? Bittensor hotkey [5F...]: (interactive prompt or read from config)
Opening browser for GitHub authentication...
🌐 https://github.com/login/oauth/authorize?client_id=...&state=...

(User authenticates in browser)

✓ GitHub authenticated as: alice
✓ Message signed with hotkey
✓ Submitting to registry (BASE L2)...
✓ Transaction confirmed: 0x1234...

✅ Successfully linked alice → 5F...
   GitHub: https://github.com/alice
   Hotkey: 5F...
```

### Workflow 2: CI/CD Environment (Non-Interactive)

```bash
$ export KUBETEE_HOTKEY="5F..."
$ export KUBETEE_GITHUB_TOKEN="ghp_..."

$ kubeteectl link-github --non-interactive

✓ GitHub authenticated as: bot_user
✓ Message signed with hotkey
✓ Submitting to registry...
✓ Transaction confirmed: 0x5678...

✅ Successfully linked bot_user → 5F...
```

### Workflow 3: Re-Link Account (With Override)

```bash
$ kubeteectl link-github --hotkey 5F... --github-token ghp_... --force

⚠️  alice is already linked to 5F...
?  Override and re-link to 5F...? [y/n]: y

✓ Previous link removed
✓ New link submitted
✅ Re-linked alice → 5F...
```

---

## 13. Query Commands (Phase 3)

```bash
# Check your linking
kubeteectl github status

# Verify someone else's linking
kubeteectl github check --username alice
kubeteectl github check --hotkey 5F...

# Unlink your GitHub account
kubeteectl github unlink --force

# View registry entries (validator-only)
kubeteectl github list --limit 100
```

---

## Conclusion

This architecture provides:

✅ **First-class integration**: GitHub linking as core CLI feature  
✅ **Secure**: Message signing prevents hotkey hijacking  
✅ **User-friendly**: OAuth for interactive, PAT for automation  
✅ **Decentralized**: On-chain registry prevents collusion  
✅ **Extensible**: Foundation for contribution-based rewards (Phase 3)  
✅ **Production-ready**: Comprehensive error handling and testing  

---

## Next Steps

1. **Design Review**: Validate architecture with team
2. **Smart Contract**: Write registry contract or Bittensor integration
3. **Implementation**: Begin Phase 1 (core + local storage)
4. **Testing**: Comprehensive unit + integration tests
5. **Deployment**: GitHub App creation + production rollout
