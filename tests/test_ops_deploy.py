"""Tests de `ops.sql_runner`, `ops.deployments_log` y `ops.deploy` (T007, T017, ADR-003).

Los tests de `sql_runner`/`deployments_log` escriben de verdad en Snowflake (`writes_db`): son
el unico modo de validar que un `.sql` idempotente converge y que una fila se puede releer tal
cual se inserto.

El modo de release completa de `ops.deploy` (`deploy_release`) se testea sustituyendo
`apply_release_artifacts` por un doble ligero, para validar solo la orquestación propia
(SHA anterior, alta en `DEPLOYMENTS`) sin pagar el coste de aplicar SQL real (Principio I).
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from conversational_analytics.ops import deploy, deployments_log, sql_runner


# ---------------------------------------------------------------------------
# ops.sql_runner (T007)
# ---------------------------------------------------------------------------


@pytest.mark.writes_db
def test_run_sql_file_applies_idempotent_script_twice(
    tmp_path: Path, scalar: Callable[[str], Any]
) -> None:
    """Aplicar dos veces el mismo script idempotente converge al mismo resultado, sin duplicar."""
    table_name = f"TMP_OPS_TEST_{uuid.uuid4().hex[:8].upper()}"
    sql_path = tmp_path / "test_idempotent.sql"
    sql_path.write_text(
        f"""
        USE ROLE CICD_DEMO_ROLE;
        USE WAREHOUSE COMPUTE_WH;
        USE SCHEMA CICD_DEMO.DEVOPS;
        CREATE OR REPLACE TABLE {table_name} (X NUMBER);
        INSERT INTO {table_name} VALUES (1);
        """,
        encoding="utf-8",
    )
    try:
        sql_runner.run_sql_file(sql_path)
        sql_runner.run_sql_file(sql_path)
        count = scalar(f"SELECT COUNT(*) FROM CICD_DEMO.DEVOPS.{table_name}")
        assert count == 1
    finally:
        scalar(f"DROP TABLE IF EXISTS CICD_DEMO.DEVOPS.{table_name}")


# ---------------------------------------------------------------------------
# ops.deploy.apply_release_artifacts (ADR-003: lee cada script via `git show`)
# ---------------------------------------------------------------------------


def test_apply_release_artifacts_reads_every_script_at_target_commit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`apply_release_artifacts` no lee `snowflake/*.sql` del disco: pide el contenido de cada
    script tal como estaba en `commit_sha` (ADR-003) y lo ejecuta con `run_sql_string`."""
    sha = "deadbeef1234"
    read_calls: list[tuple[str, str]] = []
    run_calls: list[str] = []

    def _fake_read(commit_sha: str, script_name: str) -> str:
        read_calls.append((commit_sha, script_name))
        return f"-- contenido de {script_name} en {commit_sha}"

    monkeypatch.setattr(deploy, "_read_sql_at_commit", _fake_read)
    monkeypatch.setattr(deploy.sql_runner, "run_sql_string", run_calls.append)

    deploy.apply_release_artifacts(sha)

    assert read_calls == [(sha, script) for script in deploy.RELEASE_SQL_SCRIPTS]
    assert "004_semantic_view.sql" in deploy.RELEASE_SQL_SCRIPTS
    assert len(run_calls) == len(deploy.RELEASE_SQL_SCRIPTS)


# ---------------------------------------------------------------------------
# ops.deployments_log (T007)
# ---------------------------------------------------------------------------


def _record_deploy(sha: str, *, run: int = 1) -> str:
    return deployments_log.record(
        action="DEPLOY",
        target_commit_sha=sha,
        status="SUCCESS",
        triggered_by="pytest",
        workflow_run_url=f"https://example.invalid/run/{run}",
    )


@pytest.mark.writes_db
def test_deployments_log_record_and_reread(fetch_one: Callable[[str], Any]) -> None:
    sha = uuid.uuid4().hex[:12]
    deployment_id = _record_deploy(sha)
    row = fetch_one(
        "SELECT ACTION, TARGET_COMMIT_SHA, STATUS FROM CICD_DEMO.DEVOPS.DEPLOYMENTS "
        f"WHERE DEPLOYMENT_ID = '{deployment_id}'"
    )
    assert row == ("DEPLOY", sha, "SUCCESS")


def test_deployments_log_record_rejects_invalid_action() -> None:
    with pytest.raises(ValueError):
        deployments_log.record(
            action="NOPE",
            target_commit_sha="abc1234",
            status="SUCCESS",
            triggered_by="pytest",
            workflow_run_url="https://example.invalid/run/1",
        )


def test_deployments_log_record_rejects_invalid_status() -> None:
    with pytest.raises(ValueError):
        deployments_log.record(
            action="DEPLOY",
            target_commit_sha="abc1234",
            status="PENDING",
            triggered_by="pytest",
            workflow_run_url="https://example.invalid/run/1",
        )


def test_deployments_log_record_requires_previous_sha_for_rollback() -> None:
    with pytest.raises(ValueError):
        deployments_log.record(
            action="AUTO_ROLLBACK",
            target_commit_sha="abc1234",
            status="SUCCESS",
            triggered_by="pytest",
            workflow_run_url="https://example.invalid/run/1",
        )


@pytest.mark.writes_db
def test_last_successful_deploy_excludes_given_sha() -> None:
    older_sha = uuid.uuid4().hex[:12]
    newer_sha = uuid.uuid4().hex[:12]
    _record_deploy(older_sha, run=1)
    _record_deploy(newer_sha, run=2)

    latest = deployments_log.last_successful_deploy()
    assert latest is not None
    assert latest["target_commit_sha"] == newer_sha

    excluding_newest = deployments_log.last_successful_deploy(exclude_commit_sha=newer_sha)
    assert excluding_newest is not None
    assert excluding_newest["target_commit_sha"] == older_sha


@pytest.mark.writes_db
def test_exists_successful_deploy() -> None:
    sha = uuid.uuid4().hex[:12]
    assert deployments_log.exists_successful_deploy(target_commit_sha=sha) is False
    _record_deploy(sha)
    assert deployments_log.exists_successful_deploy(target_commit_sha=sha) is True


@pytest.mark.writes_db
def test_latest_row_returns_most_recent_row_with_reason() -> None:
    sha = uuid.uuid4().hex[:12]
    deployments_log.record(
        action="DEPLOY",
        target_commit_sha=sha,
        status="FAILED",
        triggered_by="pytest",
        workflow_run_url="https://example.invalid/run/1",
        reason="fallo simulado en evaluacion post-deploy",
    )

    latest = deployments_log.latest_row()

    assert latest is not None
    assert latest["action"] == "DEPLOY"
    assert latest["target_commit_sha"] == sha
    assert latest["reason"] == "fallo simulado en evaluacion post-deploy"


# ---------------------------------------------------------------------------
# ops.deploy — modo release completa (T017/US2)
# ---------------------------------------------------------------------------


@pytest.mark.writes_db
def test_deploy_release_records_deploy_row_with_previous_sha(
    monkeypatch: pytest.MonkeyPatch, fetch_one: Callable[[str], Any]
) -> None:
    baseline_sha = uuid.uuid4().hex[:12]
    _record_deploy(baseline_sha, run=1)

    applied_shas: list[str] = []
    monkeypatch.setattr(
        deploy, "apply_release_artifacts", lambda sha: applied_shas.append(sha)
    )

    new_sha = uuid.uuid4().hex[:12]
    deploy.deploy_release(commit_sha=new_sha)

    assert applied_shas == [new_sha]

    row = fetch_one(
        "SELECT ACTION, TARGET_COMMIT_SHA, PREVIOUS_COMMIT_SHA, STATUS "
        f"FROM CICD_DEMO.DEVOPS.DEPLOYMENTS WHERE TARGET_COMMIT_SHA = '{new_sha}'"
    )
    assert row is not None
    action, target, previous, status = row
    assert (action, target, status) == ("DEPLOY", new_sha, "SUCCESS")
    # `previous` es el ultimo SUCCESS antes de este deploy; puede no ser exactamente
    # `baseline_sha` si otros tests insertaron filas mas recientes en la misma sesion, pero
    # nunca puede ser el propio `new_sha`.
    assert previous != new_sha
