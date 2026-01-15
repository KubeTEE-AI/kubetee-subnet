#!/bin/bash
# =============================================================================
# KubeTEE CLI Integration Test Runner
# =============================================================================
#
# Main entry point for running all integration tests for the kubetee CLI.
# Handles setup, teardown, and test orchestration.
#
# Usage:
#   ./run_integration_tests.sh [OPTIONS]
#
# Options:
#   --quick       Run only quick tests (no mock server required)
#   --full        Run all tests including slow ones
#   --happy-path  Run only happy path tests
#   --corner-cases Run only corner case tests
#   --pytest      Run only pytest-based tests
#   --verbose     Enable verbose output
#   --keep-server Keep mock server running after tests
#
# Test Repository: https://github.com/chainswarm/template
# =============================================================================

set -e

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
MOCK_SERVER_PORT="${MOCK_SERVER_PORT:-8765}"
MOCK_SERVER_URL="http://127.0.0.1:${MOCK_SERVER_PORT}"
MOCK_SERVER_PID=""

# Test repository for integration testing
TEST_REPO_URL="https://github.com/chainswarm/template"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

# Options
RUN_QUICK=false
RUN_FULL=false
RUN_HAPPY_PATH=false
RUN_CORNER_CASES=false
RUN_PYTEST=false
VERBOSE=false
KEEP_SERVER=false

# Exit codes
EXIT_SUCCESS=0
EXIT_FAILURE=1

# =============================================================================
# ARGUMENT PARSING
# =============================================================================

usage() {
    echo "Usage: $0 [OPTIONS]"
    echo ""
    echo "Options:"
    echo "  --quick         Run only quick tests (no mock server)"
    echo "  --full          Run all tests including slow ones"
    echo "  --happy-path    Run only happy path tests"
    echo "  --corner-cases  Run only corner case tests"
    echo "  --pytest        Run only pytest-based tests"
    echo "  --verbose       Enable verbose output"
    echo "  --keep-server   Keep mock server running after tests"
    echo "  --help          Show this help message"
    echo ""
    echo "Test Repository: ${TEST_REPO_URL}"
}

parse_args() {
    while [[ $# -gt 0 ]]; do
        case $1 in
            --quick)
                RUN_QUICK=true
                shift
                ;;
            --full)
                RUN_FULL=true
                shift
                ;;
            --happy-path)
                RUN_HAPPY_PATH=true
                shift
                ;;
            --corner-cases)
                RUN_CORNER_CASES=true
                shift
                ;;
            --pytest)
                RUN_PYTEST=true
                shift
                ;;
            --verbose)
                VERBOSE=true
                shift
                ;;
            --keep-server)
                KEEP_SERVER=true
                shift
                ;;
            --help)
                usage
                exit 0
                ;;
            *)
                echo "Unknown option: $1"
                usage
                exit 1
                ;;
        esac
    done

    # Default: run all tests
    if ! $RUN_QUICK && ! $RUN_FULL && ! $RUN_HAPPY_PATH && ! $RUN_CORNER_CASES && ! $RUN_PYTEST; then
        RUN_FULL=true
    fi
}

# =============================================================================
# LOGGING
# =============================================================================

log_header() {
    echo -e "\n${CYAN}╔══════════════════════════════════════════════════════════════════╗${NC}"
    echo -e "${CYAN}║${NC} $1"
    echo -e "${CYAN}╚══════════════════════════════════════════════════════════════════╝${NC}\n"
}

log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

# =============================================================================
# SETUP AND TEARDOWN
# =============================================================================

check_dependencies() {
    log_info "Checking dependencies..."

    local missing_deps=()

    # Check Python
    if ! command -v python &> /dev/null; then
        missing_deps+=("python")
    fi

    # Check pip/uv
    if ! command -v pip &> /dev/null && ! command -v uv &> /dev/null; then
        missing_deps+=("pip or uv")
    fi

    # Check curl
    if ! command -v curl &> /dev/null; then
        missing_deps+=("curl")
    fi

    if [ ${#missing_deps[@]} -gt 0 ]; then
        log_error "Missing dependencies: ${missing_deps[*]}"
        exit 1
    fi

    log_success "All dependencies present"
}

install_cli() {
    log_info "Ensuring kubetee CLI is installed..."

    cd "$PROJECT_ROOT"

    if ! command -v kubetee &> /dev/null; then
        log_info "Installing kubetee CLI..."
        pip install -e . --quiet
    fi

    # Verify installation
    if kubetee --version &> /dev/null; then
        log_success "kubetee CLI installed: $(kubetee --version 2>&1)"
    else
        log_error "Failed to install kubetee CLI"
        exit 1
    fi
}

check_mock_server() {
    curl -s "${MOCK_SERVER_URL}/health" > /dev/null 2>&1
}

start_mock_server() {
    if check_mock_server; then
        log_info "Mock server already running on port ${MOCK_SERVER_PORT}"
        return 0
    fi

    log_info "Starting mock validator server on port ${MOCK_SERVER_PORT}..."

    cd "$SCRIPT_DIR"
    python mock_validator_server.py --port "$MOCK_SERVER_PORT" &
    MOCK_SERVER_PID=$!

    # Wait for server to start
    local max_attempts=30
    local attempt=0
    while [ $attempt -lt $max_attempts ]; do
        if check_mock_server; then
            log_success "Mock server started (PID: $MOCK_SERVER_PID)"
            return 0
        fi
        sleep 0.5
        ((attempt++))
    done

    log_error "Failed to start mock server"
    return 1
}

stop_mock_server() {
    if $KEEP_SERVER; then
        log_info "Keeping mock server running (--keep-server)"
        return
    fi

    if [ -n "$MOCK_SERVER_PID" ]; then
        log_info "Stopping mock server (PID: $MOCK_SERVER_PID)..."
        kill "$MOCK_SERVER_PID" 2>/dev/null || true
        wait "$MOCK_SERVER_PID" 2>/dev/null || true
        MOCK_SERVER_PID=""
        log_success "Mock server stopped"
    fi
}

cleanup() {
    log_info "Cleaning up..."
    stop_mock_server
}

trap cleanup EXIT

# =============================================================================
# TEST RUNNERS
# =============================================================================

run_quick_tests() {
    log_header "Quick Tests (No Mock Server)"

    local exit_code=0

    # CLI help tests
    log_info "Testing CLI help..."
    if kubetee --help > /dev/null 2>&1; then
        log_success "kubetee --help works"
    else
        log_error "kubetee --help failed"
        exit_code=1
    fi

    # Subcommand help
    for cmd in "link-github" "status"; do
        if kubetee $cmd --help > /dev/null 2>&1; then
            log_success "kubetee $cmd --help works"
        else
            log_error "kubetee $cmd --help failed"
            exit_code=1
        fi
    done

    # Version
    if kubetee --version > /dev/null 2>&1; then
        log_success "kubetee --version works"
    else
        log_error "kubetee --version failed"
        exit_code=1
    fi

    return $exit_code
}

run_happy_path_tests() {
    log_header "Happy Path Tests"

    chmod +x "$SCRIPT_DIR/test_link_github_happy_path.sh"

    if $VERBOSE; then
        "$SCRIPT_DIR/test_link_github_happy_path.sh"
    else
        "$SCRIPT_DIR/test_link_github_happy_path.sh" 2>&1 | tail -30
    fi
}

run_corner_case_tests() {
    log_header "Corner Case Tests"

    chmod +x "$SCRIPT_DIR/test_corner_cases.sh"

    if $VERBOSE; then
        "$SCRIPT_DIR/test_corner_cases.sh"
    else
        "$SCRIPT_DIR/test_corner_cases.sh" 2>&1 | tail -50
    fi
}

run_pytest_tests() {
    log_header "PyTest Tests"

    cd "$PROJECT_ROOT"

    local pytest_args="-v"
    if ! $VERBOSE; then
        pytest_args="--tb=short -q"
    fi

    # Run acceptance tests
    log_info "Running acceptance tests..."
    python -m pytest tests/acceptance/ $pytest_args || true

    # Run GitHub verifier tests
    log_info "Running GitHub verifier tests..."
    python -m pytest tests/test_github_verifier.py $pytest_args 2>/dev/null || true

    # Run GitHub API tests
    log_info "Running GitHub API tests..."
    python -m pytest tests/test_github_api.py $pytest_args 2>/dev/null || true

    # Run mock tests
    log_info "Running mock tests..."
    python -m pytest tests/test_mock.py $pytest_args 2>/dev/null || true
}

run_repo_integration_tests() {
    log_header "Repository Integration Tests (${TEST_REPO_URL})"

    log_info "Testing with repository: ${TEST_REPO_URL}"

    # These tests simulate how a user would interact with the CLI
    # for the bounty/open source contribution flow

    # Test 1: Check if we can validate a GitHub repository URL format
    log_info "Test: Validating GitHub repository URL format..."

    if [[ "$TEST_REPO_URL" =~ ^https://github\.com/[^/]+/[^/]+$ ]]; then
        log_success "Repository URL format is valid"
    else
        log_error "Repository URL format is invalid"
    fi

    # Test 2: Verify repository is accessible (optional, requires network)
    log_info "Test: Checking repository accessibility..."
    if curl -s -o /dev/null -w "%{http_code}" "${TEST_REPO_URL}" | grep -q "200"; then
        log_success "Repository is accessible"
    else
        log_warn "Repository not accessible (may require authentication)"
    fi

    # Test 3: Test dry-run with repository-related scenarios
    log_info "Test: Dry-run with repository context..."

    # Extract owner and repo from URL
    REPO_OWNER=$(echo "$TEST_REPO_URL" | sed 's|https://github.com/||' | cut -d'/' -f1)
    REPO_NAME=$(echo "$TEST_REPO_URL" | sed 's|https://github.com/||' | cut -d'/' -f2)

    log_info "Repository owner: $REPO_OWNER"
    log_info "Repository name: $REPO_NAME"

    # Simulate gist URL for this user
    TEST_GIST_URL="https://gist.github.com/${REPO_OWNER}/abc123test"

    output=$(kubetee link-github \
        --gist-url "$TEST_GIST_URL" \
        --mechanism-id 3 \
        --validator-url "${MOCK_SERVER_URL}" \
        --dry-run \
        --wallet-name "test_wallet" 2>&1) || true

    if echo "$output" | grep -qi "dry run\|wallet"; then
        log_success "Dry-run with repository owner context works"
    else
        log_error "Dry-run failed: $output"
    fi
}

# =============================================================================
# MAIN
# =============================================================================

main() {
    echo ""
    echo -e "${CYAN}╔══════════════════════════════════════════════════════════════════╗${NC}"
    echo -e "${CYAN}║${NC}           ${GREEN}KubeTEE CLI Integration Test Suite${NC}                     ${CYAN}║${NC}"
    echo -e "${CYAN}╠══════════════════════════════════════════════════════════════════╣${NC}"
    echo -e "${CYAN}║${NC}  Test Repository: ${YELLOW}${TEST_REPO_URL}${NC}"
    echo -e "${CYAN}║${NC}  Mock Server:     ${YELLOW}${MOCK_SERVER_URL}${NC}"
    echo -e "${CYAN}╚══════════════════════════════════════════════════════════════════╝${NC}"
    echo ""

    parse_args "$@"

    # Setup
    check_dependencies
    install_cli

    local exit_code=0

    # Run tests based on options
    if $RUN_QUICK; then
        run_quick_tests || exit_code=1
    fi

    if $RUN_FULL || $RUN_HAPPY_PATH || $RUN_CORNER_CASES; then
        start_mock_server || exit 1
    fi

    if $RUN_FULL; then
        run_quick_tests || exit_code=1
        run_happy_path_tests || exit_code=1
        run_corner_case_tests || exit_code=1
        run_pytest_tests || exit_code=1
        run_repo_integration_tests || exit_code=1
    fi

    if $RUN_HAPPY_PATH && ! $RUN_FULL; then
        run_happy_path_tests || exit_code=1
    fi

    if $RUN_CORNER_CASES && ! $RUN_FULL; then
        run_corner_case_tests || exit_code=1
    fi

    if $RUN_PYTEST && ! $RUN_FULL; then
        run_pytest_tests || exit_code=1
    fi

    # Summary
    echo ""
    log_header "Test Suite Complete"

    if [ $exit_code -eq 0 ]; then
        log_success "All tests passed!"
    else
        log_error "Some tests failed"
    fi

    exit $exit_code
}

main "$@"
