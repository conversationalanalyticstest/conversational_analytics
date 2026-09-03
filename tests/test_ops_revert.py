"""Tests de `ops.revert` (T027): un SHA sin despliegue `SUCCESS` se rechaza antes de tocar
Snowflake (FR-014); uno valido re-despliega esa release y registra `MANUAL_REVERT`.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from typing import Any

import pytest

from conversational_analytics.ops import deploy, deployments_log, revert


def _record_deploy(sha: str, run: int) -> None:
    deployments_log.record(
        action="DEPLOY",
        target_commit_sha=sha,
        status="SUCCESS",
        triggered_by="pytest",
        workflow_run_url=f"https://example.invalid/run/{run}",
    )


@pytest.mark.writes_db
def test_revert_rejects_unknown_sha_without_touching_snowflake(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _fail_if_called(sha: str) -> str:
        pytest.fail("un SHA invalido no debe desplegar nada")

    monkeypatch.setattr(deploy, "apply_release_artifacts", _fail_if_called)

    with pytest.raises(revert.InvalidRevertTargetError):
        revert.revert(target_commit_sha=f"does-not-exist-{uuid.uuid4().hex[:8]}")


@pytest.mark.writes_db
def test_revert_valid_sha_redeploys_and_records_manual_revert(
    monkeypatch: pytest.MonkeyPatch, fetch_one: Callable[[str], Any]
) -> None:
    target_sha = uuid.uuid4().hex[:12]
    _record_deploy(target_sha, run=1)

    applied: list[str] = []
    monkeypatch.setattr(
        deploy, "apply_release_artifacts", lambda sha: applied.append(sha) or "SV_STUB"
    )
    tag_moves: list[str] = []
    monkeypatch.setattr(deploy, "move_deployed_good_tag", lambda sha: tag_moves.append(sha))
    monkeypatch.setenv("GITHUB_ACTOR", "octocat")

    result = revert.revert(target_commit_sha=target_sha)

    assert result == target_sha
    assert applied == [target_sha]
    assert tag_moves == [target_sha]

    row = fetch_one(
        "SELECT ACTION, TARGET_COMMIT_SHA, TRIGGERED_BY, STATUS "
        f"FROM CICD_DEMO.DEVOPS.DEPLOYMENTS WHERE TARGET_COMMIT_SHA = '{target_sha}' "
        "AND ACTION = 'MANUAL_REVERT'"
    )
    assert row == ("MANUAL_REVERT", target_sha, "octocat", "SUCCESS")
