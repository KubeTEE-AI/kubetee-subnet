#!/bin/bash
# =============================================================================
# KubeTEE GitHub Linking - Complete Test Suite Runner
# =============================================================================
# This script runs all tests including:
# - Python unit tests with coverage
# - Hardhat smart contract tests
# - Integration tests (Python ↔ Contract)
# - Acceptance tests
#
# Usage: ./scripts/run_all_tests.sh [--quick] [--coverage-only]
# =============================================================================

set -e  # Exit on first error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

# Parse arguments
QUICK_MODE=false
COVERAGE_ONLY=false

while [[ "$#" -gt 0 ]]; do
    case $1 in
        --quick) QUICK_MODE=true ;;
        --coverage-only) COVERAGE_ONLY=true ;;
        -h|--help)
            echo "Usage: $0 [--quick] [--coverage-only]"
            echo ""
            echo "Options:"
            echo "  --quick         Skip slow tests and integration tests"
            echo "  --coverage-only Run only Python tests with coverage report"
            echo "  -h, --help      Show this help message"
            exit 0
            ;;
        *) echo "Unknown parameter: $1"; exit 1 ;;
    esac
    shift
done

echo -e "${BLUE}==============================================================${NC}"
echo -e "${BLUE}       KubeTEE GitHub Linking - Complete Test Suite           ${NC}"
echo -e "${BLUE}==============================================================${NC}"
echo ""

# Track results
PYTHON_TESTS_PASSED=false
CONTRACT_TESTS_PASSED=false
INTEGRATION_TESTS_PASSED=false
ACCEPTANCE_TESTS_PASSED=false

# Cleanup function
cleanup() {
    echo -e "\n${YELLOW}Cleaning up...${NC}"
    if [ ! -z "$HARDHAT_PID" ] && kill -0 $HARDHAT_PID 2>/dev/null; then
        echo "Stopping Hardhat node (PID: $HARDHAT_PID)..."
        kill $HARDHAT_PID 2>/dev/null || true
        wait $HARDHAT_PID 2>/dev/null || true
    fi
}

trap cleanup EXIT

# =============================================================================
# Step 1: Python Unit Tests
# =============================================================================
echo -e "${BLUE}[1/4] Running Python Unit Tests${NC}"
echo "-----------------------------------------------------------"

cd "$ROOT_DIR"

if [ "$COVERAGE_ONLY" = true ]; then
    echo "Running with coverage..."
    python -m pytest tests/test_github_verifier.py tests/test_github_api.py \
        --cov=kubetee \
        --cov-report=html \
        --cov-report=term-missing \
        --cov-fail-under=80 \
        -v
    PYTHON_TESTS_PASSED=true
    echo -e "${GREEN}✓ Python tests with coverage complete${NC}"
    echo -e "\nCoverage report: ${ROOT_DIR}/htmlcov/index.html"
    exit 0
fi

if python -m pytest tests/test_github_verifier.py tests/test_github_api.py \
    --cov=kubetee \
    --cov-report=term \
    -v; then
    PYTHON_TESTS_PASSED=true
    echo -e "${GREEN}✓ Python unit tests PASSED${NC}"
else
    echo -e "${RED}✗ Python unit tests FAILED${NC}"
fi

echo ""

# =============================================================================
# Step 2: Smart Contract Tests
# =============================================================================
echo -e "${BLUE}[2/4] Running Smart Contract Tests${NC}"
echo "-----------------------------------------------------------"

cd "$ROOT_DIR/kubetee/contracts"

# Check if node_modules exists
if [ ! -d "node_modules" ]; then
    echo "Installing npm dependencies..."
    npm install
fi

if npx hardhat test; then
    CONTRACT_TESTS_PASSED=true
    echo -e "${GREEN}✓ Smart contract tests PASSED${NC}"
else
    echo -e "${RED}✗ Smart contract tests FAILED${NC}"
fi

echo ""

# =============================================================================
# Step 3: Integration Tests (skip in quick mode)
# =============================================================================
if [ "$QUICK_MODE" = false ]; then
    echo -e "${BLUE}[3/4] Running Integration Tests${NC}"
    echo "-----------------------------------------------------------"

    cd "$ROOT_DIR/kubetee/contracts"

    # Start Hardhat node in background
    echo "Starting Hardhat node..."
    npx hardhat node > /tmp/hardhat.log 2>&1 &
    HARDHAT_PID=$!
    
    # Wait for Hardhat to start
    echo "Waiting for Hardhat node to start..."
    sleep 5
    
    # Check if Hardhat is running
    if ! kill -0 $HARDHAT_PID 2>/dev/null; then
        echo -e "${RED}Failed to start Hardhat node${NC}"
        cat /tmp/hardhat.log
        exit 1
    fi
    
    echo "Hardhat node running (PID: $HARDHAT_PID)"
    
    cd "$ROOT_DIR"
    
    if python -m pytest tests/acceptance/test_contract_integration.py -v; then
        INTEGRATION_TESTS_PASSED=true
        echo -e "${GREEN}✓ Integration tests PASSED${NC}"
    else
        echo -e "${RED}✗ Integration tests FAILED${NC}"
    fi
    
    # Stop Hardhat node
    echo "Stopping Hardhat node..."
    kill $HARDHAT_PID 2>/dev/null || true
    wait $HARDHAT_PID 2>/dev/null || true
    unset HARDHAT_PID
else
    echo -e "${YELLOW}[3/4] Skipping Integration Tests (quick mode)${NC}"
    INTEGRATION_TESTS_PASSED=true
fi

echo ""

# =============================================================================
# Step 4: Acceptance Tests (skip in quick mode)
# =============================================================================
if [ "$QUICK_MODE" = false ]; then
    echo -e "${BLUE}[4/4] Running Acceptance Tests${NC}"
    echo "-----------------------------------------------------------"

    cd "$ROOT_DIR"

    if python -m pytest tests/acceptance/test_e2e_github_linking.py \
                        tests/acceptance/test_cli_acceptance.py -v; then
        ACCEPTANCE_TESTS_PASSED=true
        echo -e "${GREEN}✓ Acceptance tests PASSED${NC}"
    else
        echo -e "${RED}✗ Acceptance tests FAILED${NC}"
    fi
else
    echo -e "${YELLOW}[4/4] Skipping Acceptance Tests (quick mode)${NC}"
    ACCEPTANCE_TESTS_PASSED=true
fi

echo ""

# =============================================================================
# Summary
# =============================================================================
echo -e "${BLUE}==============================================================${NC}"
echo -e "${BLUE}                      TEST SUMMARY                            ${NC}"
echo -e "${BLUE}==============================================================${NC}"
echo ""

print_status() {
    if [ "$2" = true ]; then
        echo -e "  $1: ${GREEN}PASSED${NC}"
    else
        echo -e "  $1: ${RED}FAILED${NC}"
    fi
}

print_status "Python Unit Tests    " $PYTHON_TESTS_PASSED
print_status "Smart Contract Tests " $CONTRACT_TESTS_PASSED
print_status "Integration Tests    " $INTEGRATION_TESTS_PASSED
print_status "Acceptance Tests     " $ACCEPTANCE_TESTS_PASSED

echo ""

# Final result
ALL_PASSED=true
if [ "$PYTHON_TESTS_PASSED" = false ] || \
   [ "$CONTRACT_TESTS_PASSED" = false ] || \
   [ "$INTEGRATION_TESTS_PASSED" = false ] || \
   [ "$ACCEPTANCE_TESTS_PASSED" = false ]; then
    ALL_PASSED=false
fi

if [ "$ALL_PASSED" = true ]; then
    echo -e "${GREEN}==============================================================${NC}"
    echo -e "${GREEN}              ✓ ALL TESTS PASSED SUCCESSFULLY!               ${NC}"
    echo -e "${GREEN}==============================================================${NC}"
    exit 0
else
    echo -e "${RED}==============================================================${NC}"
    echo -e "${RED}                  ✗ SOME TESTS FAILED                        ${NC}"
    echo -e "${RED}==============================================================${NC}"
    exit 1
fi
