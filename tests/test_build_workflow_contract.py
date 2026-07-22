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


def test_production_publish_normalizes_the_ghcr_repository_name():
    text = WORKFLOW.read_text(encoding="utf-8")

    normalized_image = (
        'IMAGE=ghcr.io/$(echo "${{ github.repository }}" | '
        "tr '[:upper:]' '[:lower:]')"
    )
    assert text.count(normalized_image) == 2
    assert 'IMAGE: ghcr.io/${{ github.repository }}' not in text


def test_production_publish_makes_image_public_before_anonymous_smoke():
    text = WORKFLOW.read_text(encoding="utf-8")
    visibility_step = text.index("- name: Make image public")
    smoke_step = text.index("- name: Pull and import-smoke the published production image")
    visibility_block = text[visibility_step:smoke_step]
    smoke_block = text[smoke_step:]

    assert visibility_step < smoke_step
    assert "continue-on-error: true" not in visibility_block
    assert "|| true" not in visibility_block
    assert "curl -sf -X PATCH" in visibility_block
    assert "docker logout ghcr.io" in smoke_block
    assert 'docker image rm "${IMAGE}:latest" || true' in smoke_block
    assert smoke_block.index("docker logout ghcr.io") < smoke_block.index(
        'docker pull "${IMAGE}:latest"'
    )
