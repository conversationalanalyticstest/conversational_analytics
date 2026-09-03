"""Tests de `ops.rollback` (T023): localizacion de la ultima release buena y forward-fix.

`apply_release_artifacts` se sustituye por un doble ligero (su propia logica de lectura via
`git show` se cubre en `tests/test_ops_deploy.py`, ADR-003): aqui se valida solo la logica
propia de `ops.rollback` — que release es "la buena", que se registra con los campos
correctos, y que no reintenta si el propio rollback falla (FR-011).
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from typing import Any

import pytest

from conversational_analytics.ops import deploy, deployments_log, rollback


def _record_deploy(sha: str, run: int) -> None:
    deployments_log.record(
        action="DEPLOY",
        target_commit_sha=sha,
        status="SUCCESS",
        triggered_by="pytest",
        workflow_run_url=f"https://example.invalid/run/{run}",
    )


# ---------------------------------------------------------------------------
# resolve_rollback_target
# ---------------------------------------------------------------------------


def test_resolve_rollback_target_uses_tag_when_available(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    good_sha = uuid.uuid4().hex[:12]
    failed_sha = uuid.uuid4().hex[:12]
    monkeypatch.setattr(deploy, "read_deployed_good_sha", lambda: good_sha)

    assert rollback.resolve_rollback_target(failed_sha=failed_sha) == good_sha


@pytest.mark.writes_db
def test_resolve_rollback_target_falls_back_to_deployments_when_no_tag(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    good_sha = uuid.uuid4().hex[:12]
    failed_sha = uuid.uuid4().hex[:12]
    _record_deploy(good_sha, run=1)
    _record_deploy(failed_sha, run=2)

    monkeypatch.setattr(deploy, "read_deployed_good_sha", lambda: None)

    assert rollback.resolve_rollback_target(failed_sha=failed_sha) == good_sha


def test_resolve_rollback_target_falls_back_when_tag_matches_failed_sha(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Si el tag no se movio a tiempo y coincide con el commit que acaba de fallar, no sirve
    como objetivo de rollback: hay que caer al historico de DEPLOYMENTS."""
    good_sha = uuid.uuid4().hex[:12]
    failed_sha = uuid.uuid4().hex[:12]
    _record_deploy(good_sha, run=1)
    monkeypatch.setattr(deploy, "read_deployed_good_sha", lambda: failed_sha)

    assert rollback.resolve_rollback_target(failed_sha=failed_sha) == good_sha


def test_resolve_rollback_target_raises_when_nothing_to_roll_back_to(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(deploy, "read_deployed_good_sha", lambda: None)
    monkeypatch.setattr(deployments_log, "last_successful_deploy", lambda **_: None)

    with pytest.raises(RuntimeError):
        rollback.resolve_rollback_target(failed_sha="does-not-matter")


# ---------------------------------------------------------------------------
# rollback()
# ---------------------------------------------------------------------------


@pytest.mark.writes_db
def test_rollback_records_auto_rollback_row_and_moves_tag(
    monkeypatch: pytest.MonkeyPatch, fetch_one: Callable[[str], Any]
) -> None:
    good_sha = uuid.uuid4().hex[:12]
    failed_sha = uuid.uuid4().hex[:12]
    monkeypatch.setattr(deploy, "read_deployed_good_sha", lambda: good_sha)

    applied: list[str] = []
    monkeypatch.setattr(
        deploy, "apply_release_artifacts", lambda sha: applied.append(sha) or "SV_STUB"
    )
    tag_moves: list[str] = []
    monkeypatch.setattr(deploy, "move_deployed_good_tag", lambda sha: tag_moves.append(sha))

    target = rollback.rollback(failed_sha=failed_sha)

    assert target == good_sha
    assert applied == [good_sha]
    assert tag_moves == [good_sha]

    row = fetch_one(
        "SELECT ACTION, TARGET_COMMIT_SHA, PREVIOUS_COMMIT_SHA, STATUS "
        f"FROM CICD_DEMO.DEVOPS.DEPLOYMENTS WHERE TARGET_COMMIT_SHA = '{good_sha}' "
        f"AND PREVIOUS_COMMIT_SHA = '{failed_sha}'"
    )
    assert row == ("AUTO_ROLLBACK", good_sha, failed_sha, "SUCCESS")


@pytest.mark.writes_db
def test_rollback_records_failed_row_and_does_not_retry_when_apply_fails(
    monkeypatch: pytest.MonkeyPatch, fetch_one: Callable[[str], Any]
) -> None:
    good_sha = uuid.uuid4().hex[:12]
    failed_sha = uuid.uuid4().hex[:12]
    monkeypatch.setattr(deploy, "read_deployed_good_sha", lambda: good_sha)

    attempts: list[str] = []

    def _boom(sha: str) -> str:
        attempts.append(sha)
        raise RuntimeError("fallo simulado de despliegue")

    monkeypatch.setattr(deploy, "apply_release_artifacts", _boom)
    monkeypatch.setattr(
        deploy,
        "move_deployed_good_tag",
        lambda sha: pytest.fail("no debe mover el tag si el rollback fallo"),
    )

    with pytest.raises(RuntimeError):
        rollback.rollback(failed_sha=failed_sha)

    assert attempts == [good_sha]  # sin reintentos (FR-011)

    row = fetch_one(
        "SELECT ACTION, STATUS FROM CICD_DEMO.DEVOPS.DEPLOYMENTS "
        f"WHERE TARGET_COMMIT_SHA = '{good_sha}' AND PREVIOUS_COMMIT_SHA = '{failed_sha}'"
    )
    assert row == ("AUTO_ROLLBACK", "FAILED")
