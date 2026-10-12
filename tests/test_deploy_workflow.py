"""Regression checks for the production deployment sequence."""

from __future__ import annotations

from pathlib import Path

WORKFLOW = Path(__file__).parents[1] / ".github" / "workflows" / "deploy.yml"


def test_deployment_validates_configuration_before_replacing_services() -> None:
    workflow = WORKFLOW.read_text()

    build = workflow.index("docker compose build")
    preflight = workflow.index("settings.validate_production_secrets()")
    replace = workflow.index("docker compose up -d --no-build --remove-orphans")

    assert build < preflight < replace


def test_deployment_preserves_rollback_image_until_portal_is_healthy() -> None:
    workflow = WORKFLOW.read_text()

    healthy = workflow.index('if [ "$status" = "200" ]')
    prune = workflow.index("docker image prune -f")

    assert healthy < prune
    assert "docker compose restart portal" not in workflow
