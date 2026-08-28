# Contributing to KubeTEE AI (SN90)

Thank you for your interest in contributing to the KubeTEE subnet validator.
This is a Bittensor subnet-owner validator — it scores miners on infrastructure
readiness and sets Bittensor weights on-chain. Contributions that affect
scoring or weight-setting are held to a high bar because they influence
on-chain emissions.

## Development setup

```bash
# Clone with submodules (the vendored bittensor SDK lives in subtensor/)
git clone --recurse-submodules https://github.com/KubeTEE-AI/kubetee-subnet.git
cd kubetee-subnet

# Install in development mode
pip install -e ".[dev]"

# Copy the env template and fill in your values (DO NOT commit .env)
cp validator/.env.example validator/.env
# edit validator/.env with your RANCHER_URL, RANCHER_BEARER_TOKEN, etc.
```

**Python 3.13+** is required (`requires-python = ">=3.13"`).

## Code quality checks

All PRs must pass:

```bash
# Format check (line-length 79)
black --line-length 79 --exclude '(env|venv|.eggs|.git|subtensor)' --check .

# Tests
pytest validator/tests -q

# Build (verify the Docker image builds)
docker build -f validator/Dockerfile -t kubetee-validator:dev .
```

CI runs these on every push and pull request to `main`.

## Commit message convention

Follow `<type>(subnet): <description>`:

- `feat(subnet): ...` — new feature
- `fix(subnet): ...` — bug fix
- `docs(subnet): ...` — documentation only
- `refactor(subnet): ...` — no behavior change
- `chore(subnet): ...` — tooling, deps, CI

Keep the subject line to ~72 characters. Reference issues in the body
(`Closes #123`, `Refs #456`).

## Branch model

- `main` — production branch (protected). Releases are tagged from here.
- Feature branches: `feature/<topic>/<description>`.
- Hotfix branches: `hotfix/<version>/<description>`.

Open pull requests against `main`.

## Scoring invariants — do not break these

The validator holds several invariants that keep the subnet's incentive
mechanism sound. A PR that changes scoring or weight-setting must preserve:

1. **Fail-closed readiness**: a miner with missing, ambiguous, or malformed
   evidence scores `0`. A Rancher evidence *outage* skips the whole cycle
   rather than failing miners.
2. **Miner/owner weight split**: weights sum to `1.0`; the owner remainder
   is set on the owner UID — the protocol's recycle/burn sink. Under
   `recycle_or_burn=recycle` that alpha returns to unissued supply and never
   credits the owner key; it is not an owner payout
   ([Bittensor subnet guide](https://www.bittensor.com/docs/guides/subnets)).
3. **Single weight matrix**: one `set_weights` per epoch (no `mechanism_id`
   split), boundary-aligned, with `weights_rate_limit` cooldown.
4. **No secrets in code**: all credentials come from environment variables
   via `config.py`; never hardcode a token, seed, or key.
5. **No utilization term**: miners are scored on **provable available
   capacity**, not on consumption. Do not (re)introduce a utilization term,
   a "75% target", or a `util_gap` factor.

If your change touches any of these, explain why in the PR description and
add a test.

## Tests

The test suite lives in `validator/tests/` and is a flat `pytest` collection
(no `__init__.py`; `tests/conftest.py` puts `validator/` on `sys.path`).
Tests are hermetic — no test hits a live external service. When adding a
scoring input or a new client, add a test that monkeypatches the HTTP layer.

## Reporting security issues

See [SECURITY.md](SECURITY.md) — do NOT open a public issue for a security
vulnerability.
