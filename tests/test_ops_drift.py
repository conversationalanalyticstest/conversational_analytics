"""Test de la logica de deteccion de drift (T018): funcion pura, sin Snowflake ni Git real."""

from __future__ import annotations

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
