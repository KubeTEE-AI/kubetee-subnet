# Pull Request

## Summary

A 1-2 sentence description of what this PR changes and why.

## Type of change

- [ ] feat (new feature)
- [ ] fix (bug fix)
- [ ] docs (documentation only)
- [ ] refactor (no behavior change)
- [ ] chore (tooling, deps, CI)

## Checklist

- [ ] `black --line-length 79 --check .` passes
- [ ] `pytest validator/tests -q` passes
- [ ] Commit message follows `<type>(subnet): <description>` convention
- [ ] No secrets, private keys, or internal infrastructure details added
- [ ] If this changes validator behavior, the invariants are preserved:
  fail-closed readiness, miner/owner weight split, weights sum to 1.0

## Test plan

How did you verify this change? (unit tests, dry run, live cycle, etc.)

## Related issues

Closes #<issue>. Refs #<issue>.
