#!/usr/bin/env python3
"""
Mock Validator Server for Integration Testing

Provides a simple FastAPI server that mimics the validator's GitHub linking API.
Can be configured to return success/failure responses for testing.

Usage:
    python mock_validator_server.py [--port 8765] [--scenario success]

Scenarios:
    - success: All requests succeed
    - gist_not_found: Returns gist not found error
    - hotkey_not_registered: Returns hotkey not registered error
    - signature_invalid: Returns signature validation error
    - rate_limited: Returns GitHub rate limit error
    - network_error: Server returns 500 errors
"""

import os
import sys
import json
import time
import argparse
from typing import Optional, Dict, Any
from dataclasses import dataclass

try:
    from fastapi import FastAPI, HTTPException
    from fastapi.responses import JSONResponse
    from pydantic import BaseModel
    import uvicorn
except ImportError:
    print("Required packages not installed. Install with:")
    print("  pip install fastapi uvicorn pydantic")
    sys.exit(1)


# =============================================================================
# REQUEST/RESPONSE MODELS
# =============================================================================

class LinkGitHubRequest(BaseModel):
    """Request model for link-github endpoint."""
    hotkey: str
    mechanism_id: int
    gist_url: str
    message: str
    signature: str


class LinkGitHubResponse(BaseModel):
    """Response model for link-github endpoint."""
    success: bool
    github_username: Optional[str] = None
    tx_hash: Optional[str] = None
    status: Optional[str] = None  # "created", "updated", "unchanged"
    error_code: Optional[str] = None
    error_message: Optional[str] = None


class StatusResponse(BaseModel):
    """Response model for status endpoint."""
    hotkey: str
    is_linked: bool
    github_username: Optional[str] = None
    mechanism_id: int
    links: list = []


# =============================================================================
# ERROR SCENARIOS
# =============================================================================

ERROR_SCENARIOS = {
    "gist_not_found": {
        "success": False,
        "error_code": "gist_not_found",
        "error_message": "Gist not found or not public. Ensure gist exists and is public."
    },
    "hotkey_not_registered": {
        "success": False,
        "error_code": "hotkey_not_registered",
        "error_message": "Hotkey is not registered on subnet 62. Register first with btcli."
    },
    "signature_invalid": {
        "success": False,
        "error_code": "signature_invalid",
        "error_message": "Message signature verification failed. Ensure signing with correct hotkey."
    },
    "timestamp_expired": {
        "success": False,
        "error_code": "timestamp_expired",
        "error_message": "Message timestamp is too old. Message must be signed within 5 minutes."
    },
    "hotkey_mismatch": {
        "success": False,
        "error_code": "hotkey_mismatch",
        "error_message": "Hotkey in gist does not match request hotkey."
    },
    "rate_limited": {
        "success": False,
        "error_code": "github_rate_limited",
        "error_message": "GitHub API rate limit exceeded. Try again in 60 seconds."
    },
    "github_user_not_found": {
        "success": False,
        "error_code": "github_user_not_found",
        "error_message": "GitHub user not found. Ensure gist owner account exists."
    },
    "contract_error": {
        "success": False,
        "error_code": "contract_error",
        "error_message": "Failed to write link to smart contract. Try again later."
    },
}


# =============================================================================
# MOCK SERVER
# =============================================================================

app = FastAPI(title="Mock KubeTEE Validator", version="1.0.0")

# Global state
_scenario: str = "success"
_linked_hotkeys: Dict[str, Dict[int, str]] = {}  # hotkey -> {mechanism_id: github_username}
_request_count: int = 0


def set_scenario(scenario: str):
    """Set the current error scenario."""
    global _scenario
    _scenario = scenario


def get_scenario() -> str:
    """Get the current error scenario."""
    return _scenario


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "scenario": _scenario}


@app.post("/api/github/link", response_model=LinkGitHubResponse)
async def link_github(request: LinkGitHubRequest):
    """
    Link GitHub account to hotkey.

    In test mode, behavior is controlled by the current scenario.
    """
    global _request_count, _linked_hotkeys
    _request_count += 1

    # Network error scenario - return 500
    if _scenario == "network_error":
        raise HTTPException(status_code=500, detail="Internal server error")

    # Timeout scenario - sleep forever (will timeout)
    if _scenario == "timeout":
        time.sleep(120)

    # Check for error scenarios
    if _scenario in ERROR_SCENARIOS:
        return LinkGitHubResponse(**ERROR_SCENARIOS[_scenario])

    # Success scenario
    # Extract gist username from URL (e.g., https://gist.github.com/octocat/abc123)
    try:
        parts = request.gist_url.split("/")
        github_username = parts[3] if len(parts) > 3 else "testuser"
    except Exception:
        github_username = "testuser"

    # Track the link
    if request.hotkey not in _linked_hotkeys:
        _linked_hotkeys[request.hotkey] = {}

    existing = _linked_hotkeys[request.hotkey].get(request.mechanism_id)
    if existing == github_username:
        status = "unchanged"
        tx_hash = None
    elif existing:
        status = "updated"
        tx_hash = f"0x{'ab' * 32}"
    else:
        status = "created"
        tx_hash = f"0x{'cd' * 32}"

    _linked_hotkeys[request.hotkey][request.mechanism_id] = github_username

    return LinkGitHubResponse(
        success=True,
        github_username=github_username,
        tx_hash=tx_hash,
        status=status
    )


@app.get("/api/github/status/{hotkey}")
async def get_status(hotkey: str, mechanism_id: int = 3):
    """Get GitHub link status for a hotkey."""
    global _linked_hotkeys

    if _scenario == "network_error":
        raise HTTPException(status_code=500, detail="Internal server error")

    links = []
    is_linked = False
    github_username = None

    if hotkey in _linked_hotkeys:
        for mech_id, username in _linked_hotkeys[hotkey].items():
            links.append({"mechanism_id": mech_id, "github_username": username})
            if mech_id == mechanism_id:
                is_linked = True
                github_username = username

    return StatusResponse(
        hotkey=hotkey,
        is_linked=is_linked,
        github_username=github_username,
        mechanism_id=mechanism_id,
        links=links
    )


@app.post("/api/test/set-scenario")
async def set_test_scenario(scenario: str):
    """Test-only endpoint to change scenario."""
    global _scenario
    if scenario not in ERROR_SCENARIOS and scenario not in ["success", "network_error", "timeout"]:
        return {"error": f"Unknown scenario: {scenario}"}
    _scenario = scenario
    return {"scenario": _scenario}


@app.post("/api/test/reset")
async def reset_test_state():
    """Test-only endpoint to reset state."""
    global _scenario, _linked_hotkeys, _request_count
    _scenario = "success"
    _linked_hotkeys = {}
    _request_count = 0
    return {"status": "reset"}


@app.get("/api/test/stats")
async def get_test_stats():
    """Test-only endpoint to get stats."""
    return {
        "scenario": _scenario,
        "request_count": _request_count,
        "linked_hotkeys": len(_linked_hotkeys)
    }


# =============================================================================
# MAIN
# =============================================================================

def main():
    parser = argparse.ArgumentParser(description="Mock Validator Server for Testing")
    parser.add_argument("--port", type=int, default=8765, help="Port to run on")
    parser.add_argument("--host", default="127.0.0.1", help="Host to bind to")
    parser.add_argument(
        "--scenario",
        default="success",
        choices=list(ERROR_SCENARIOS.keys()) + ["success", "network_error", "timeout"],
        help="Initial scenario"
    )
    args = parser.parse_args()

    set_scenario(args.scenario)

    print(f"Starting Mock Validator Server on {args.host}:{args.port}")
    print(f"Initial scenario: {args.scenario}")
    print(f"Endpoints:")
    print(f"  POST /api/github/link - Link GitHub account")
    print(f"  GET  /api/github/status/{{hotkey}} - Check link status")
    print(f"  POST /api/test/set-scenario - Change test scenario")
    print(f"  POST /api/test/reset - Reset test state")
    print(f"  GET  /api/test/stats - Get test statistics")

    uvicorn.run(app, host=args.host, port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
