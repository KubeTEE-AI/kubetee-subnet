# Release & Versioning

The KubeTEE subnet validator follows **Semantic Versioning 2.0.0** (`MAJOR.MINOR.PATCH`), with image tags published to `ghcr.io/kubetee-ai/kubetee-validator` by the [`release-image.yml`](../.github/workflows/release-image.yml) GitHub Actions workflow.

## Version scheme

| Bump | When | Example |
|------|------|---------|
| **MAJOR** (`v2.0.0`) | Breaking change to the on-chain weight protocol, the price-card schema (`version` field), the payout.json schema, the proxy auth protocol, or any change that makes old reader validators produce different weights than new ones. Also: a subnet migration (netuid change, chain fork). | Adding a new required field to `payout.json` that old readers don't understand → bump `version` in the JSON AND major. |
| **MINOR** (`v1.1.0`) | New feature that is backward-compatible — old readers keep working unchanged, but new readers gain capability. New GPU class added to the card, new fallback tier, new env var with a safe default. | Adding `RTX6000` to `DEFAULT_USD_CARD`; adding the S3 price fallback. |
| **PATCH** (`v1.0.1`) | Bug fix, doc change, log wording, test addition, image rebuild with no behavior change. Old readers and new readers produce identical weights. | Fixing a log message; updating doc examples. |

**The test for "is this a major bump?": would an old validator and a new validator, both reading the same metagraph + the same S3 snapshot, produce different `set_weights` vectors?** If yes → major. If no but behavior changed → minor. If only logs/docs → patch.

## Image tags

The [`release-image.yml`](../.github/workflows/release-image.yml) workflow builds `linux/amd64` + `linux/arm64` via `docker buildx` and pushes to `ghcr.io/kubetee-ai/kubetee-validator`. The tag is resolved as:

| Trigger | Image tag |
|---------|-----------|
| `git push tag v1.0.0` | `v1.0.0` + `latest` |
| `workflow_dispatch` with `tag=v1.0.0` | `v1.0.0` + `latest` |
| Push to `main` (validator/subtensor changes) | `sha-<short-sha>` + `latest` |

The `latest` tag always points to the most recent build. The Fleet deployment pins a specific version tag (e.g. `v1.0.0`) — **never** `latest` — so a pod restart always pulls the intended version, not whatever was last pushed.

## Release procedure

1. **Verify tests pass** on `main`:
   ```bash
   cd validator && python -m pytest tests/ -q
   ```

2. **Tag the release** on the `kubetee-subnet` repo:
   ```bash
   git tag -a v1.0.0 -m "v1.0.0 — first public release"
   git push origin v1.0.0
   ```
   The tag push triggers `release-image.yml` automatically.

3. **Wait for the image build** to complete:
   ```bash
   gh run watch -R KubeTEE-AI/kubetee-subnet --workflow release-image.yml
   ```

4. **Update the Fleet deployment** in the `kubetee-fleet` repo to the new tag:
   ```yaml
   # fleet-gitops/infrastructure/kubetee-validator-proxy/staging/deployment.yaml
   image: ghcr.io/kubetee-ai/kubetee-validator:v1.0.0
   ```
   Commit + push, then force-resync:
   ```bash
   kubectl --context stagingrancher annotate gitrepo \
     kubetee-validator-proxy-staging -n fleet-default \
     fleet.cattle.io/force-update="$(date +%s)" --overwrite
   ```

5. **Verify the pod** comes up `1/1 Running` with the new image:
   ```bash
   kubectl --context k3s-staging -n kubetee get pods
   kubectl --context k3s-staging -n kubetee get pod -l app=validator \
     -o jsonpath='{.items[0].spec.containers[0].image}'
   ```

6. **Delete old image tags** from ghcr (optional cleanup):
   ```bash
   # List all tagged versions
   gh api /orgs/kubetee-ai/packages/container/kubetee-validator/versions \
     --paginate | jq '.[] | select(.metadata.container.tags | length > 0) | {id, tags: .metadata.container.tags}'

   # Delete a specific version by ID
   gh api --method DELETE /orgs/kubetee-ai/packages/container/kubetee-validator/versions/<ID>
   ```

7. **Smoke-test the proxy** from a reader perspective:
   ```bash
   VALIDATOR_HOTKEY_SEED=<mnemonic> python scripts/smoke_proxy.py
   ```

## Changelog

Document user-visible changes in the commit message body of the release tag. The convention:

```
v1.0.0 — first public release

Features:
- Hotkey-authenticated Rancher proxy (validator.kubetee.ai)
- Reader-mode RancherClient (third-party validators use the proxy, no bearer token)
- S3 price fallback (reader validators survive Taostats outages)
- Multi-arch image (amd64 + arm64) via GitHub Actions
- GPU price card with RTX6000 support
- Public dashboard on Hippius S3

Fixes:
- (list any bug fixes)
```

## Pre-release / development tags

During active development before a release, the workflow tags images as `sha-<short-sha>` on every `main` push. These are for testing only — never pin a Fleet deployment to a `sha-*` tag. Once the version is stable, tag it `vX.Y.Z` and update the Fleet deployment.
