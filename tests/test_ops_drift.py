"""Test de la logica de deteccion de drift (T018): funcion pura, sin Snowflake ni Git real."""

from __future__ import annotations

from pathlib import Path

import pytest

from conversational_analytics.ops import deploy, deployments_log, drift
from conversational_analytics.ops.drift import check_drift


def test_check_drift_no_drift_when_shas_match() -> None:
    status = check_drift(deployed_sha="abc1234", head_sha="abc1234")
    assert status.has_drift is False
    assert status.deployed_sha == status.head_sha == "abc1234"


def test_check_drift_has_drift_when_shas_differ() -> None:
    status = check_drift(deployed_sha="abc1234", head_sha="def5678")
    assert status.has_drift is True
    assert status.deployed_sha == "abc1234"
    assert status.head_sha == "def5678"


# ---------------------------------------------------------------------------
# main() — salida `reason` (T038/T039, D-09 research.md)
# ---------------------------------------------------------------------------


def test_main_writes_reason_from_latest_deployments_row(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    output_file = tmp_path / "github_output.txt"
    monkeypatch.setenv("GITHUB_OUTPUT", str(output_file))
    monkeypatch.setattr(deploy, "read_deployed_good_sha", lambda: "abc1234")
    monkeypatch.setattr(
        deployments_log,
        "latest_row",
        lambda: {
            "action": "DEPLOY",
            "reason": "fallo simulado en evaluacion post-deploy",
            "target_commit_sha": "abc1234",
        },
    )

    exit_code = drift.main(["--head-sha", "abc1234"])

    assert exit_code == 0
    content = output_file.read_text(encoding="utf-8")
    assert "reason=fallo simulado en evaluacion post-deploy" in content


def test_main_writes_empty_reason_when_no_deployments_row(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    output_file = tmp_path / "github_output.txt"
    monkeypatch.setenv("GITHUB_OUTPUT", str(output_file))
    monkeypatch.setattr(deploy, "read_deployed_good_sha", lambda: None)
    monkeypatch.setattr(deployments_log, "latest_row", lambda: None)

    exit_code = drift.main(["--head-sha", "abc1234"])

    assert exit_code == 0
    content = output_file.read_text(encoding="utf-8")
    assert "reason=\n" in content
