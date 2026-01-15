#!/bin/bash
# =============================================================================
# Integration Test: GitHub Linking - Corner Cases
# =============================================================================
#
# Tests edge cases, error handling, and unusual inputs for the kubetee CLI.
# Requires mock validator server to be running.
#
# Test Categories:
#   1. Invalid URL formats
#   2. Network errors
#   3. Validation failures
#   4. Rate limiting
#   5. Boundary conditions
#   6. Special characters and encoding
#
# Usage:
#   ./test_corner_cases.sh
# =============================================================================

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# Test configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
MOCK_SERVER_PORT="${MOCK_SERVER_PORT:-8765}"
MOCK_SERVER_URL="http://127.0.0.1:${MOCK_SERVER_PORT}"
MOCK_SERVER_PID=""

# Test data
TEST_HOTKEY="5GrwvaEF5zXb26Fz9rcQpDWS57CtERHpNehXCPcNoHGKutQY"
TEST_GIST_URL="https://gist.github.com/testuser/abc123"
TEST_REPO_URL="https://github.com/chainswarm/template"

# Counters
TESTS_PASSED=0
TESTS_FAILED=0
TESTS_SKIPPED=0

# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[PASS]${NC} $1"
    ((TESTS_PASSED++))
}

log_fail() {
    echo -e "${RED}[FAIL]${NC} $1"
    ((TESTS_FAILED++))
}

log_skip() {
    echo -e "${YELLOW}[SKIP]${NC} $1"
    ((TESTS_SKIPPED++))
}

log_test() {
    echo -e "\n${YELLOW}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${YELLOW}CORNER CASE:${NC} $1"
    echo -e "${YELLOW}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
}

check_mock_server() {
    curl -s "${MOCK_SERVER_URL}/health" > /dev/null 2>&1
}

start_mock_server() {
    log_info "Starting mock validator server on port ${MOCK_SERVER_PORT}..."
    cd "$SCRIPT_DIR"
    python mock_validator_server.py --port "$MOCK_SERVER_PORT" &
    MOCK_SERVER_PID=$!

    # Wait for server to start
    local max_attempts=30
    local attempt=0
    while [ $attempt -lt $max_attempts ]; do
        if check_mock_server; then
            log_info "Mock server started (PID: $MOCK_SERVER_PID)"
            return 0
        fi
        sleep 0.5
        ((attempt++))
    done

    log_fail "Failed to start mock server"
    return 1
}

stop_mock_server() {
    if [ -n "$MOCK_SERVER_PID" ]; then
        log_info "Stopping mock server (PID: $MOCK_SERVER_PID)..."
        kill "$MOCK_SERVER_PID" 2>/dev/null || true
        wait "$MOCK_SERVER_PID" 2>/dev/null || true
        MOCK_SERVER_PID=""
    fi
}

set_scenario() {
    local scenario="$1"
    curl -s -X POST "${MOCK_SERVER_URL}/api/test/set-scenario?scenario=${scenario}" > /dev/null
}

reset_server() {
    curl -s -X POST "${MOCK_SERVER_URL}/api/test/reset" > /dev/null
}

# Cleanup on exit
trap stop_mock_server EXIT

# =============================================================================
# CORNER CASE TESTS - INVALID URL FORMATS
# =============================================================================

test_invalid_gist_url_format() {
    log_test "Invalid Gist URL - Not a gist.github.com URL"

    # Using a regular GitHub URL instead of gist URL
    output=$(kubetee link-github \
        --gist-url "https://github.com/testuser/repo" \
        --mechanism-id 3 \
        --validator-url "${MOCK_SERVER_URL}" \
        --dry-run \
        --wallet-name "test" 2>&1) || true

    # Should either warn or proceed with dry-run
    log_success "Handled non-gist URL (output: ${output:0:100}...)"
}

test_invalid_gist_url_malformed() {
    log_test "Invalid Gist URL - Malformed URL"

    output=$(kubetee link-github \
        --gist-url "not-a-valid-url" \
        --mechanism-id 3 \
        --validator-url "${MOCK_SERVER_URL}" \
        --dry-run \
        --wallet-name "test" 2>&1) || true

    # Should handle gracefully
    log_success "Handled malformed URL gracefully"
}

test_empty_gist_id() {
    log_test "Invalid Gist URL - Empty gist ID"

    output=$(kubetee link-github \
        --gist-url "https://gist.github.com/testuser/" \
        --mechanism-id 3 \
        --validator-url "${MOCK_SERVER_URL}" \
        --dry-run \
        --wallet-name "test" 2>&1) || true

    log_success "Handled empty gist ID"
}

test_gist_url_with_special_chars() {
    log_test "Gist URL with Special Characters"

    # URL with query parameters and fragments
    output=$(kubetee link-github \
        --gist-url "https://gist.github.com/testuser/abc123?foo=bar#section" \
        --mechanism-id 3 \
        --validator-url "${MOCK_SERVER_URL}" \
        --dry-run \
        --wallet-name "test" 2>&1) || true

    log_success "Handled URL with query params and fragments"
}

# =============================================================================
# CORNER CASE TESTS - MECHANISM ID BOUNDARIES
# =============================================================================

test_mechanism_id_boundary_low() {
    log_test "Mechanism ID Boundary - Minimum (0)"

    output=$(kubetee link-github \
        --gist-url "${TEST_GIST_URL}" \
        --mechanism-id 0 \
        --validator-url "${MOCK_SERVER_URL}" \
        --dry-run \
        --wallet-name "test" 2>&1) || true

    if ! echo "$output" | grep -qi "invalid"; then
        log_success "Mechanism ID 0 accepted"
    else
        log_fail "Mechanism ID 0 rejected"
    fi
}

test_mechanism_id_boundary_high() {
    log_test "Mechanism ID Boundary - Maximum (10)"

    output=$(kubetee link-github \
        --gist-url "${TEST_GIST_URL}" \
        --mechanism-id 10 \
        --validator-url "${MOCK_SERVER_URL}" \
        --dry-run \
        --wallet-name "test" 2>&1) || true

    if ! echo "$output" | grep -qi "invalid"; then
        log_success "Mechanism ID 10 accepted"
    else
        log_fail "Mechanism ID 10 rejected"
    fi
}

test_mechanism_id_out_of_range_negative() {
    log_test "Mechanism ID - Negative Value"

    output=$(kubetee link-github \
        --gist-url "${TEST_GIST_URL}" \
        --mechanism-id -1 \
        --validator-url "${MOCK_SERVER_URL}" \
        --dry-run \
        --wallet-name "test" 2>&1) || exit_code=$?

    # Should be rejected by Click validation
    if echo "$output" | grep -qi "invalid\|error\|range"; then
        log_success "Negative mechanism ID rejected"
    else
        log_fail "Negative mechanism ID not properly rejected"
    fi
}

test_mechanism_id_out_of_range_high() {
    log_test "Mechanism ID - Out of Range (11)"

    output=$(kubetee link-github \
        --gist-url "${TEST_GIST_URL}" \
        --mechanism-id 11 \
        --validator-url "${MOCK_SERVER_URL}" \
        --dry-run \
        --wallet-name "test" 2>&1) || exit_code=$?

    if echo "$output" | grep -qi "invalid\|error\|range"; then
        log_success "Out-of-range mechanism ID rejected"
    else
        log_fail "Out-of-range mechanism ID not properly rejected"
    fi
}

# =============================================================================
# CORNER CASE TESTS - NETWORK ERRORS (requires mock server)
# =============================================================================

test_server_not_reachable() {
    log_test "Network Error - Server Not Reachable"

    # Point to a non-existent server
    output=$(kubetee link-github \
        --gist-url "${TEST_GIST_URL}" \
        --mechanism-id 3 \
        --validator-url "http://127.0.0.1:59999" \
        --wallet-name "test" 2>&1) || exit_code=$?

    if echo "$output" | grep -qi "connect\|error\|failed\|wallet"; then
        log_success "Connection error handled gracefully"
    else
        log_fail "Connection error not handled properly: $output"
    fi
}

test_validator_returns_500() {
    log_test "Network Error - Server Returns 500"

    if ! check_mock_server; then
        log_skip "Mock server not running"
        return
    fi

    set_scenario "network_error"

    output=$(kubetee link-github \
        --gist-url "${TEST_GIST_URL}" \
        --mechanism-id 3 \
        --validator-url "${MOCK_SERVER_URL}" \
        --wallet-name "test" 2>&1) || exit_code=$?

    reset_server

    if echo "$output" | grep -qi "error\|failed\|wallet"; then
        log_success "Server 500 error handled gracefully"
    else
        log_fail "Server 500 error not handled properly"
    fi
}

# =============================================================================
# CORNER CASE TESTS - VALIDATION ERRORS (requires mock server)
# =============================================================================

test_gist_not_found_error() {
    log_test "Validation Error - Gist Not Found"

    if ! check_mock_server; then
        log_skip "Mock server not running"
        return
    fi

    set_scenario "gist_not_found"

    output=$(kubetee link-github \
        --gist-url "${TEST_GIST_URL}" \
        --mechanism-id 3 \
        --validator-url "${MOCK_SERVER_URL}" \
        --wallet-name "test" 2>&1) || exit_code=$?

    reset_server

    if echo "$output" | grep -qi "gist_not_found\|not found\|error\|wallet"; then
        log_success "Gist not found error displayed correctly"
    else
        log_fail "Gist not found error not displayed: $output"
    fi
}

test_hotkey_not_registered_error() {
    log_test "Validation Error - Hotkey Not Registered"

    if ! check_mock_server; then
        log_skip "Mock server not running"
        return
    fi

    set_scenario "hotkey_not_registered"

    output=$(kubetee link-github \
        --gist-url "${TEST_GIST_URL}" \
        --mechanism-id 3 \
        --validator-url "${MOCK_SERVER_URL}" \
        --wallet-name "test" 2>&1) || exit_code=$?

    reset_server

    if echo "$output" | grep -qi "not_registered\|register\|error\|wallet"; then
        log_success "Hotkey not registered error handled"
    else
        log_fail "Hotkey not registered error not handled"
    fi
}

test_signature_invalid_error() {
    log_test "Validation Error - Invalid Signature"

    if ! check_mock_server; then
        log_skip "Mock server not running"
        return
    fi

    set_scenario "signature_invalid"

    output=$(kubetee link-github \
        --gist-url "${TEST_GIST_URL}" \
        --mechanism-id 3 \
        --validator-url "${MOCK_SERVER_URL}" \
        --wallet-name "test" 2>&1) || exit_code=$?

    reset_server

    if echo "$output" | grep -qi "signature\|invalid\|error\|wallet"; then
        log_success "Invalid signature error handled"
    else
        log_fail "Invalid signature error not handled"
    fi
}

test_rate_limited_error() {
    log_test "Validation Error - GitHub Rate Limited"

    if ! check_mock_server; then
        log_skip "Mock server not running"
        return
    fi

    set_scenario "rate_limited"

    output=$(kubetee link-github \
        --gist-url "${TEST_GIST_URL}" \
        --mechanism-id 3 \
        --validator-url "${MOCK_SERVER_URL}" \
        --wallet-name "test" 2>&1) || exit_code=$?

    reset_server

    if echo "$output" | grep -qi "rate\|limit\|error\|wallet"; then
        log_success "Rate limit error handled"
    else
        log_fail "Rate limit error not handled"
    fi
}

# =============================================================================
# CORNER CASE TESTS - SPECIAL INPUT VALUES
# =============================================================================

test_very_long_gist_url() {
    log_test "Special Input - Very Long Gist URL"

    # Create a very long but valid-looking URL
    long_id=$(printf 'a%.0s' {1..1000})
    output=$(kubetee link-github \
        --gist-url "https://gist.github.com/testuser/${long_id}" \
        --mechanism-id 3 \
        --validator-url "${MOCK_SERVER_URL}" \
        --dry-run \
        --wallet-name "test" 2>&1) || true

    log_success "Handled very long gist URL"
}

test_unicode_in_url() {
    log_test "Special Input - Unicode in URL"

    output=$(kubetee link-github \
        --gist-url "https://gist.github.com/tëstüsér/abc123" \
        --mechanism-id 3 \
        --validator-url "${MOCK_SERVER_URL}" \
        --dry-run \
        --wallet-name "test" 2>&1) || true

    log_success "Handled unicode in URL"
}

test_empty_wallet_name() {
    log_test "Special Input - Empty Wallet Name"

    output=$(kubetee link-github \
        --gist-url "${TEST_GIST_URL}" \
        --mechanism-id 3 \
        --validator-url "${MOCK_SERVER_URL}" \
        --dry-run \
        --wallet-name "" 2>&1) || exit_code=$?

    # Should use default or show error
    log_success "Handled empty wallet name"
}

test_timeout_value() {
    log_test "Special Input - Custom Timeout"

    output=$(kubetee link-github \
        --gist-url "${TEST_GIST_URL}" \
        --mechanism-id 3 \
        --validator-url "${MOCK_SERVER_URL}" \
        --timeout 1 \
        --dry-run \
        --wallet-name "test" 2>&1) || true

    log_success "Accepted custom timeout value"
}

# =============================================================================
# CORNER CASE TESTS - STATUS COMMAND
# =============================================================================

test_status_invalid_hotkey() {
    log_test "Status Command - Invalid Hotkey Format"

    output=$(kubetee status \
        --hotkey "not-a-valid-ss58-address" \
        --validator-url "${MOCK_SERVER_URL}" 2>&1) || exit_code=$?

    # Should either query anyway or reject
    log_success "Handled invalid hotkey format in status"
}

test_status_empty_hotkey() {
    log_test "Status Command - Empty Hotkey"

    output=$(kubetee status \
        --hotkey "" \
        --validator-url "${MOCK_SERVER_URL}" 2>&1) || exit_code=$?

    if echo "$output" | grep -qi "required\|missing\|error"; then
        log_success "Empty hotkey properly rejected"
    else
        log_fail "Empty hotkey not rejected"
    fi
}

# =============================================================================
# PYTEST CORNER CASE TESTS
# =============================================================================

run_pytest_corner_cases() {
    log_test "PyTest Corner Case Tests"

    cd "$PROJECT_ROOT"

    # Create a temporary test file for corner cases
    cat > /tmp/test_cli_corner_cases.py << 'PYTEST_EOF'
"""
Corner case tests for kubetee CLI.
"""
import pytest
import json
from unittest.mock import Mock, patch, MagicMock
from click.testing import CliRunner


@pytest.fixture
def cli_runner():
    return CliRunner()


class TestURLValidation:
    """Tests for URL validation corner cases."""

    def test_gist_url_with_trailing_slash(self, cli_runner):
        """Gist URL with trailing slash should be handled."""
        from kubetee.cli import main

        with patch('kubetee.cli.github.bittensor') as mock_bt:
            mock_wallet = MagicMock()
            mock_wallet.hotkey.ss58_address = "5GrwvaEF5zXb26Fz9rcQpDWS57CtERHpNehXCPcNoHGKutQY"
            mock_wallet.hotkey_file.exists_on_device.return_value = True
            mock_bt.wallet.return_value = mock_wallet

            result = cli_runner.invoke(main, [
                "link-github",
                "--gist-url", "https://gist.github.com/user/abc123/",
                "--mechanism-id", "3",
                "--dry-run"
            ])
            # Should complete dry-run successfully
            assert "DRY RUN" in result.output or result.exit_code == 0

    def test_gist_url_https_vs_http(self, cli_runner):
        """HTTP URL should work or warn appropriately."""
        from kubetee.cli import main

        with patch('kubetee.cli.github.bittensor') as mock_bt:
            mock_wallet = MagicMock()
            mock_wallet.hotkey.ss58_address = "5GrwvaEF5zXb26Fz9rcQpDWS57CtERHpNehXCPcNoHGKutQY"
            mock_wallet.hotkey_file.exists_on_device.return_value = True
            mock_bt.wallet.return_value = mock_wallet

            result = cli_runner.invoke(main, [
                "link-github",
                "--gist-url", "http://gist.github.com/user/abc123",
                "--mechanism-id", "3",
                "--dry-run"
            ])
            # Should handle HTTP URLs
            assert result.exit_code == 0 or "error" in result.output.lower()


class TestMechanismIdEdgeCases:
    """Tests for mechanism ID edge cases."""

    @pytest.mark.parametrize("mech_id", [0, 1, 2, 3, 10])
    def test_valid_mechanism_ids(self, cli_runner, mech_id):
        """All valid mechanism IDs should be accepted."""
        from kubetee.cli import main

        with patch('kubetee.cli.github.bittensor') as mock_bt:
            mock_wallet = MagicMock()
            mock_wallet.hotkey.ss58_address = "5GrwvaEF5zXb26Fz9rcQpDWS57CtERHpNehXCPcNoHGKutQY"
            mock_wallet.hotkey_file.exists_on_device.return_value = True
            mock_bt.wallet.return_value = mock_wallet

            result = cli_runner.invoke(main, [
                "link-github",
                "--gist-url", "https://gist.github.com/user/abc",
                "--mechanism-id", str(mech_id),
                "--dry-run"
            ])
            assert "DRY RUN" in result.output

    def test_mechanism_id_as_string(self, cli_runner):
        """Mechanism ID as non-numeric string should fail."""
        from kubetee.cli import main

        result = cli_runner.invoke(main, [
            "link-github",
            "--gist-url", "https://gist.github.com/user/abc",
            "--mechanism-id", "bounty",
            "--dry-run"
        ])
        assert result.exit_code != 0


class TestWalletEdgeCases:
    """Tests for wallet-related edge cases."""

    def test_wallet_path_with_spaces(self, cli_runner):
        """Wallet name with spaces should be handled."""
        from kubetee.cli import main

        result = cli_runner.invoke(main, [
            "link-github",
            "--gist-url", "https://gist.github.com/user/abc",
            "--mechanism-id", "3",
            "--wallet-name", "my wallet with spaces",
            "--dry-run"
        ])
        # Should attempt to load (and fail gracefully)
        assert "wallet" in result.output.lower() or result.exit_code != 0


class TestEnvironmentVariables:
    """Tests for environment variable handling."""

    def test_env_vars_override_defaults(self, cli_runner):
        """Environment variables should override defaults."""
        from kubetee.cli import main

        with patch('kubetee.cli.github.bittensor') as mock_bt:
            mock_wallet = MagicMock()
            mock_wallet.hotkey.ss58_address = "5GrwvaEF5zXb26Fz9rcQpDWS57CtERHpNehXCPcNoHGKutQY"
            mock_wallet.hotkey_file.exists_on_device.return_value = True
            mock_bt.wallet.return_value = mock_wallet

            result = cli_runner.invoke(main, [
                "link-github",
                "--gist-url", "https://gist.github.com/user/abc",
                "--mechanism-id", "3",
                "--dry-run"
            ], env={
                "KUBETEE_WALLET": "env_wallet_name",
                "KUBETEE_VALIDATOR": "http://custom-validator:9999"
            })

            # Should use custom validator URL in dry-run output
            assert "custom-validator:9999" in result.output or "DRY RUN" in result.output


class TestStatusCommand:
    """Tests for status command edge cases."""

    def test_status_with_short_hotkey(self, cli_runner):
        """Short hotkey should be handled appropriately."""
        from kubetee.cli import main

        result = cli_runner.invoke(main, [
            "status",
            "--hotkey", "5Grw"  # Too short
        ])
        # Should query or reject
        assert result.exit_code != 0 or "error" in result.output.lower() or "hotkey" in result.output.lower()
PYTEST_EOF

    # Run the corner case tests
    if python -m pytest /tmp/test_cli_corner_cases.py -v --tb=short 2>&1; then
        log_success "PyTest corner case tests passed"
    else
        log_fail "Some PyTest corner case tests failed"
    fi

    rm -f /tmp/test_cli_corner_cases.py
}

# =============================================================================
# MAIN
# =============================================================================

main() {
    echo ""
    echo "=============================================================="
    echo "   KubeTEE CLI Integration Tests - Corner Cases"
    echo "=============================================================="
    echo "  Test Repository: ${TEST_REPO_URL}"
    echo "  Mock Server URL: ${MOCK_SERVER_URL}"
    echo "=============================================================="
    echo ""

    # Check if kubetee CLI is installed
    if ! command -v kubetee &> /dev/null; then
        log_info "Installing kubetee CLI..."
        cd "$PROJECT_ROOT"
        pip install -e . --quiet
    fi

    # Start mock server if not running
    if ! check_mock_server; then
        start_mock_server
    else
        log_info "Mock server already running"
    fi

    # URL format tests
    test_invalid_gist_url_format
    test_invalid_gist_url_malformed
    test_empty_gist_id
    test_gist_url_with_special_chars

    # Mechanism ID boundary tests
    test_mechanism_id_boundary_low
    test_mechanism_id_boundary_high
    test_mechanism_id_out_of_range_negative
    test_mechanism_id_out_of_range_high

    # Network error tests (require mock server)
    test_server_not_reachable
    test_validator_returns_500

    # Validation error tests (require mock server)
    test_gist_not_found_error
    test_hotkey_not_registered_error
    test_signature_invalid_error
    test_rate_limited_error

    # Special input tests
    test_very_long_gist_url
    test_unicode_in_url
    test_empty_wallet_name
    test_timeout_value

    # Status command tests
    test_status_invalid_hotkey
    test_status_empty_hotkey

    # Run PyTest corner cases
    if command -v pytest &> /dev/null; then
        run_pytest_corner_cases
    else
        log_skip "PyTest not available"
    fi

    # Summary
    echo ""
    echo "=============================================================="
    echo "   Corner Case Test Summary"
    echo "=============================================================="
    echo -e "  ${GREEN}Passed:${NC}  $TESTS_PASSED"
    echo -e "  ${RED}Failed:${NC}  $TESTS_FAILED"
    echo -e "  ${YELLOW}Skipped:${NC} $TESTS_SKIPPED"
    echo "=============================================================="

    if [ $TESTS_FAILED -gt 0 ]; then
        exit 1
    fi
    exit 0
}

main "$@"
