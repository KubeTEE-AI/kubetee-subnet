# Changelog

All notable changes to this project are documented here. The project follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) conventions; release
and versioning policy lives in
[RELEASE-AND-VERSIONING.md](./RELEASE-AND-VERSIONING.md).

## [Unreleased]

### Added

- CI: ruff correctness gate (undefined names / syntax class) alongside the
  existing black format check.
- CI: pytest coverage gate (`--cov-fail-under=80`; baseline ~84% at adoption).
- CI: `zizmor` workflow-security job (scoped to this repo's workflows).
- CI/release: all GitHub Actions pinned to full commit SHAs.
- Release image: SLSA build provenance + SBOM attestation
  (`actions/attest-build-provenance`), verify with
  `gh attestation verify oci://ghcr.io/kubetee-ai/kubetee-validator:<tag>`.
- Dependabot root entry moved to the `uv` ecosystem so `uv.lock` regenerates
  with manifest bumps (2026-11-27).
- Dependabot security updates + secret scanning + push protection enabled
  (2026-11-27).
- Branch protection on `main` (required checks, linear history, no force
  push).
- Stale issue/PR bot and `dependencies` / `submodule` labels.

### Fixed

- `validator.py`: import `resolve_card` from `price_card` — the non-hippius
  card-resolution path raised `NameError` at runtime (latent bug found by the
  new ruff gate).

### Documentation

- Attestation docs: Phase 6 trust-bootstrap note, spec + client-facing
  contract reconciliation (pending review).

## [1.3.3] and earlier

See git history and [RELEASE-AND-VERSIONING.md](./RELEASE-AND-VERSIONING.md).
