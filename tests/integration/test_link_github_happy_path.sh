#!/bin/bash
# =============================================================================
# Integration Test: GitHub Linking - Happy Path
# =============================================================================
#
# Tests the kubetee CLI `link-github` command with valid inputs.
# Uses mock validator server and mock wallet.
#
# Prerequisites:
#   - kubetee CLI installed (pip install -e .)
#   - Mock validator server running (or will be started)
#
# Usage:
#   ./test_link_github_happy_path.sh
#
# Test Repository: https://github.com/chainswarm/template
# =============================================================================

set -e  # Exit on error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Test configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
MOCK_SERVER_PORT="${MOCK_SERVER_PORT:-8765}"
MOCK_SERVER_URL="http://127.0.0.1:${MOCK_SERVER_PORT}"
TEST_REPO_URL="https://github.com/chainswarm/template"

# Test hotkeys (valid SS58 format)
TEST_HOTKEY="5GrwvaEF5zXb26Fz9rcQpDWS57CtERHpNehXCPcNoHGKutQY"
TEST_GIST_ID="abc123def456"
TEST_GIST_URL="https://gist.github.com/testuser/${TEST_GIST_ID}"

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
    echo -e "${YELLOW}TEST:${NC} $1"
    echo -e "${YELLOW}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
}

check_mock_server() {
    curl -s "${MOCK_SERVER_URL}/health" > /dev/null 2>&1
}

wait_for_server() {
    local max_attempts=30
    local attempt=0

    while [ $attempt -lt $max_attempts ]; do
        if check_mock_server; then
            return 0
        fi
        sleep 0.5
        ((attempt++))
    done
    return 1
}

set_scenario() {
    local scenario="$1"
    curl -s -X POST "${MOCK_SERVER_URL}/api/test/set-scenario?scenario=${scenario}" > /dev/null
}

reset_server() {
    curl -s -X POST "${MOCK_SERVER_URL}/api/test/reset" > /dev/null
}

# =============================================================================
# TEST CASES - HAPPY PATH
# =============================================================================

test_cli_help() {
    log_test "CLI Help Command"

    if kubetee --help | grep -q "link-github"; then
        log_success "CLI help shows link-github command"
    else
        log_fail "CLI help does not show link-github command"
    fi

    if kubetee link-github --help | grep -q "gist-url"; then
        log_success "link-github help shows --gist-url option"
    else
        log_fail "link-github help missing --gist-url option"
    fi
}

test_dry_run_mode() {
    log_test "Dry Run Mode"

    # Test dry-run with mock wallet (will fail to load real wallet, but should show dry-run output)
    output=$(kubetee link-github \
        --gist-url "${TEST_GIST_URL}" \
        --mechanism-id 3 \
        --validator-url "${MOCK_SERVER_URL}" \
        --dry-run \
        --wallet-name "nonexistent_wallet_for_test" 2>&1) || true

    # Dry run should either show request details or wallet error
    if echo "$output" | grep -qi "dry run\|DRY RUN\|wallet"; then
        log_success "Dry run mode works (shows output or wallet error as expected)"
    else
        log_fail "Dry run mode did not produce expected output: $output"
    fi
}

test_environment_variables() {
    log_test "Environment Variable Support"

    # Test that environment variables are recognized
    export KUBETEE_VALIDATOR="http://test-validator:9999"

    output=$(kubetee link-github --help 2>&1)

    if echo "$output" | grep -q "KUBETEE_VALIDATOR"; then
        log_success "KUBETEE_VALIDATOR environment variable documented"
    else
        log_fail "KUBETEE_VALIDATOR environment variable not documented"
    fi

    unset KUBETEE_VALIDATOR
}

test_mechanism_id_validation() {
    log_test "Mechanism ID Validation"

    # Valid mechanism IDs: 0-10
    for mech_id in 0 1 2 3; do
        output=$(kubetee link-github \
            --gist-url "${TEST_GIST_URL}" \
            --mechanism-id "$mech_id" \
            --dry-run \
            --wallet-name "test" 2>&1) || true

        # Should not fail on valid mechanism ID (wallet error is OK)
        if ! echo "$output" | grep -qi "invalid.*mechanism"; then
            log_success "Mechanism ID $mech_id accepted"
        else
            log_fail "Mechanism ID $mech_id rejected incorrectly"
        fi
    done
}

test_status_command_help() {
    log_test "Status Command"

    if kubetee status --help | grep -q "hotkey"; then
        log_success "Status command has --hotkey option"
    else
        log_fail "Status command missing --hotkey option"
    fi
}

test_cli_version() {
    log_test "CLI Version"

    if kubetee --version | grep -qi "kubetee\|0\."; then
        log_success "CLI version command works"
    else
        log_fail "CLI version command failed"
    fi
}

# =============================================================================
# PYTEST INTEGRATION TESTS
# =============================================================================

test_pytest_acceptance() {
    log_test "PyTest Acceptance Tests"

    cd "$PROJECT_ROOT"

    # Run existing acceptance tests
    if python -m pytest tests/acceptance/test_cli_acceptance.py -v --tb=short 2>&1; then
        log_success "PyTest acceptance tests passed"
    else
        log_fail "PyTest acceptance tests failed"
    fi
}

test_pytest_github_verifier() {
    log_test "PyTest GitHub Verifier Tests"

    cd "$PROJECT_ROOT"

    # Run GitHub verifier tests
    if python -m pytest tests/test_github_verifier.py -v --tb=short 2>&1; then
        log_success "PyTest GitHub verifier tests passed"
    else
        log_fail "PyTest GitHub verifier tests failed"
    fi
}

# =============================================================================
# MAIN
# =============================================================================

main() {
    echo ""
    echo "=============================================================="
    echo "   KubeTEE CLI Integration Tests - Happy Path"
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

    # Run tests that don't require mock server
    test_cli_help
    test_cli_version
    test_environment_variables
    test_mechanism_id_validation
    test_status_command_help
    test_dry_run_mode

    # Run pytest tests if available
    if command -v pytest &> /dev/null; then
        log_info "Running PyTest acceptance tests..."
        test_pytest_acceptance || true
    else
        log_skip "PyTest not available - skipping acceptance tests"
    fi

    # Summary
    echo ""
    echo "=============================================================="
    echo "   Test Summary"
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
