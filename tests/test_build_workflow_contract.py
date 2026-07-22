"""Static release-contract tests for the published validator image."""

from __future__ import annotations

import pathlib

ROOT = pathlib.Path(__file__).parent.parent
WORKFLOW = ROOT / ".github" / "workflows" / "build.yml"


def test_production_publish_uses_repository_dockerfile():
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "docker buildx build -f Dockerfile --push" in text
    assert "Dockerfile.validator" not in text


def test_production_publish_has_traceable_tags_and_remote_smoke():
    text = WORKFLOW.read_text(encoding="utf-8")
    assert '${IMAGE}:latest' in text
    assert '${IMAGE}:v${VERSION}' in text
    assert '${IMAGE}:$(date +%Y-%m-%d-%H%M)' in text
    assert 'docker pull "${IMAGE}:latest"' in text
    assert 'remote import smoke OK' in text
    assert '"visibility":"public"' in text
