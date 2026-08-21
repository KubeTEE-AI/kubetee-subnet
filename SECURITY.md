# Security Policy

## Scope

KubeTEE AI (SN90) is a Bittensor subnet that runs SOTA AI services for enterprises in
hardware-secured Trusted Execution Environments (TEE) using Kata Containers and
Confidential Containers (CoCo) on decentralized RKE2 Kubernetes infrastructure.

This policy covers security vulnerabilities in the **KubeTEE subnet validator**
code (`validator/`), its Dockerfile, the configuration templates
(`validator/.env.example`), and the repository's documentation. It does not
cover the upstream `subtensor` submodule (report those to
[RaoFoundation/subtensor](https://github.com/RaoFoundation/subtensor)) or
third-party dependencies (report those upstream).

## Reporting a vulnerability

**Do NOT open a public GitHub issue for a security vulnerability.**

Instead, report vulnerabilities privately:

- Open a **private security advisory** via GitHub: Security tab → "Report a
  vulnerability" (the preferred path).
- Or email `pierre@kubetee.ai` with `[security]` in the subject line.

Please include:
- A description of the vulnerability and its impact.
- The affected file(s) / commit / version.
- Steps to reproduce, or a proof of concept.
- Any suggested remediation.

## Response timeline (target)

| Step | Target |
|------|--------|
| Acknowledge receipt | within 72 hours |
| Initial assessment + severity rating | within 7 days |
| Fix or mitigation for high/critical issues | within 30 days |
| Coordinated public disclosure | after a fix is released, or after 90 days if the issue is unpatched (whichever comes first) |

These are targets, not guarantees. We will keep you informed of progress.

## In scope

- Validator code vulnerabilities (the `validator/` flat package).
- Secrets exposure in committed files, the Docker image, or CI.
- The Dockerfile / build context leaking secrets or running as an
  over-privileged user.
- Authentication / authorization bypass in the Rancher v3 client, the
  hotkey-seed wallet, or the `set_weights` path.
- Failure modes that silently skip scoring or weight-setting without a
  metric/log (a fail-closed or fail-soft regression).
- Documentation that misleads a miner or validator operator into an insecure
  configuration.

## Out of scope

- The upstream `subtensor` blockchain and SDK (report to RaoFoundation/subtensor).
- Third-party libraries (httpx, prometheus-client, bittensor) — report upstream.
- Social engineering, physical attacks, or DoS against the live Finney
  validator.
- Vulnerabilities requiring a compromised miner hotkey (the threat model
  assumes the hotkey holder IS the miner).

## Security posture

- **Fail-closed / fail-soft design**: the validator scores `0` on missing or
  ambiguous evidence; a Rancher outage skips the cycle; a Taostats price
  failure skips the cycle and previous on-chain weights persist.
- **No secrets in code**: all credentials (hotkey seed, Rancher token, Taostats
  key, Hippius keys) are read from environment variables via `config.py`; the
  `.env` file is gitignored and never committed.
- **No shell-out**: the validator uses `urllib`/`httpx` for HTTP and does not
  invoke `subprocess` with `shell=True`.
- **TLS verification**: the Rancher client supports a CA file via
  `ssl.create_default_context(cafile=...)`; no `CERT_NONE` / `verify=False`.
- **Flat, auditable unit**: the `validator/` directory is a flat set of
  bare-import modules with no `__init__.py`, so the full runtime is reviewable
  in one directory.
