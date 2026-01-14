# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.1.0] - 2026-01-13

### Added

- **Smart Contracts:** KubeTEEGitHubRegistry contract for GitHub-hotkey linking
  - Upgradeable UUPS pattern for future improvements
  - Event-based storage for gas efficiency (~2,000 gas vs ~20,000 per write)
  - Admin/Operator access control model
  - Full test coverage (23 tests passing)

- **GitHub Linking API:** REST API for miner GitHub account linking
  - POST `/api/github/link` - Link hotkey to GitHub account
  - GET `/api/github/status/{hotkey}` - Check link status
  - GET `/api/github/health` - Health check endpoint
  - 6-step verification process (registration, signature, gist, HOTKEY.md, match, user)
  - Mock mode for local development (`--mock` flag)

- **CLI Tool:** `kubetee` command-line interface
  - `kubetee link-github` - Link GitHub account to hotkey
  - `kubetee status` - Check link status
  - ASCII banner and rich formatting
  - Environment variable support

- **Acceptance Tests:** Comprehensive test suite
  - 32 API validation tests covering all acceptance criteria
  - Request validation (AC1), verification checks (AC2), response handling (AC3)
  - Edge cases (AC4) and security tests (AC5)
  - Mock fixtures for isolated testing

- **Docker Support:** Containerized deployment
  - `Dockerfile.base` - Base image with Python dependencies
  - `Dockerfile` - Application image with code
  - `docker-compose.yml` - Full development stack
  - Hardhat node, Redis, API services
  - Observability with Dozzle

- **GitHub Actions:** CI/CD workflows
  - `release.yml` - Automated release and Docker publishing
  - Smart conditional base image rebuilds
  - OCI-compliant image labels

### Technical Details

- **Access Control Model:**
  - Admin (owner): Full rights - add/remove operators, upgrade contract
  - Operator: Can emit events and perform logic operations

- **Verification Flow:**
  1. [A] Hotkey registered on subnet 62
  2. [B] Signature valid (sr25519)
  3. [C] Gist exists and is public
  4. [D] HOTKEY.md contains valid hotkey
  5. [E] All hotkeys match (claimed, signed, gist)
  6. [F] GitHub user exists

- **Multi-Mechanism Support:**
  - Mechanism 0: Infrastructure (60% emissions)
  - Mechanism 1: Open Source (40% emissions)
  - Mechanism 2: Referral (0% emissions, revenue share)
  - Mechanism 3: Bounty

## [0.0.0] - Initial Template

### Added

- Initial project structure from Bittensor subnet template
- Multi-mechanism architecture design
- Base neuron classes (validator, miner)
- Protocol definitions (ServiceRequest, InfrastructureStatus, Dummy)
