# KubeTEE CLI Integration Tests

Integration tests for the `kubetee` CLI GitHub repository submission functionality.

## Test Repository

These tests use `https://github.com/chainswarm/template` as the reference repository for integration testing.

## Test Structure

```
tests/integration/
├── README.md                           # This file
├── __init__.py                         # Python package init
├── mock_validator_server.py            # Mock validator API server
├── run_integration_tests.sh            # Main test runner
├── test_link_github_happy_path.sh      # Happy path bash tests
├── test_corner_cases.sh                # Corner case bash tests
└── test_github_repo_submission.py      # PyTest integration tests
```

## Quick Start

### Run All Tests

```bash
cd kubetee-subnet/tests/integration
./run_integration_tests.sh
```

### Run Specific Test Suites

```bash
# Quick tests only (no mock server required)
./run_integration_tests.sh --quick

# Happy path tests
./run_integration_tests.sh --happy-path

# Corner case tests
./run_integration_tests.sh --corner-cases

# PyTest tests only
./run_integration_tests.sh --pytest
```

### Run PyTest Directly

```bash
# All integration tests
pytest tests/integration/ -v

# Specific test file
pytest tests/integration/test_github_repo_submission.py -v

# With coverage
pytest tests/integration/ -v --cov=kubetee
```

## Mock Validator Server

The mock server simulates the validator's GitHub linking API for testing.

### Start Manually

```bash
python tests/integration/mock_validator_server.py --port 8765
```

### Available Scenarios

Set scenario via API:
```bash
curl -X POST "http://localhost:8765/api/test/set-scenario?scenario=gist_not_found"
```

Available scenarios:
- `success` - All requests succeed
- `gist_not_found` - Gist not found error
- `hotkey_not_registered` - Hotkey not registered error
- `signature_invalid` - Invalid signature error
- `timestamp_expired` - Expired timestamp error
- `rate_limited` - GitHub rate limit error
- `network_error` - Server 500 errors

### API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Health check |
| `/api/github/link` | POST | Link GitHub account |
| `/api/github/status/{hotkey}` | GET | Check link status |
| `/api/test/set-scenario` | POST | Set test scenario |
| `/api/test/reset` | POST | Reset server state |
| `/api/test/stats` | GET | Get test statistics |

## Mocking Bittensor

These tests mock the bittensor/subtensor layer to avoid requiring on-chain registration.

### Mock Classes

```python
from tests.integration.test_github_repo_submission import (
    MockSubtensor,
    MockWallet,
    MockGitHubRegistry,
)

# Create mock subtensor with registered hotkeys
subtensor = MockSubtensor()
subtensor.register_hotkey("5Grwva...", netuid=62)

# Create mock wallet
wallet = MockWallet(name="test_wallet")
wallet.set_hotkey("5Grwva...")

# Create mock registry
registry = MockGitHubRegistry()
```

### Usage in Tests

```python
import pytest
from unittest.mock import patch

def test_cli_with_mock(cli_runner):
    with patch('kubetee.cli.github.bittensor') as mock_bt:
        mock_bt.wallet.return_value = MockWallet()

        result = cli_runner.invoke(main, [
            "link-github",
            "--gist-url", "https://gist.github.com/user/abc",
            "--mechanism-id", "3",
            "--dry-run"
        ])

        assert "DRY RUN" in result.output
```

## Test Categories

### Happy Path Tests

Tests normal operation with valid inputs:
- CLI help commands
- Dry-run mode
- Environment variable support
- All valid mechanism IDs
- Successful link flow

### Corner Case Tests

Tests edge conditions and error handling:
- Invalid URL formats (malformed, non-gist URLs, special characters)
- Mechanism ID boundaries (0-10, negative, out of range)
- Network errors (connection refused, timeouts, 500 errors)
- Validation errors (gist not found, hotkey not registered, etc.)
- Special input values (unicode, long URLs, empty values)

### Integration Tests

End-to-end tests with the test repository:
- Repository URL parsing
- Gist URL generation for repo owner
- Full submission flow simulation
- Status checking

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `MOCK_SERVER_PORT` | Mock server port | `8765` |
| `KUBETEE_WALLET` | Wallet name | `default` |
| `KUBETEE_WALLET_HOTKEY` | Hotkey name | `default` |
| `KUBETEE_VALIDATOR` | Validator URL | `https://validator.kubetee.io` |

## CI Integration

Add to your CI pipeline:

```yaml
# GitHub Actions example
- name: Run Integration Tests
  run: |
    cd kubetee-subnet
    pip install -e ".[dev]"
    ./tests/integration/run_integration_tests.sh --full
```

## Troubleshooting

### Mock Server Won't Start

```bash
# Check if port is in use
lsof -i :8765

# Kill existing process
pkill -f "mock_validator_server.py"
```

### Tests Fail with Import Errors

```bash
# Ensure kubetee is installed
cd kubetee-subnet
pip install -e .
```

### PyTest Not Found

```bash
pip install pytest pytest-asyncio
```
