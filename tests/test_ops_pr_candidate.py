"""Tests de `ops.pr_candidate` (feature 005-pr-checks-semantic-isolation).

Los tests marcados `writes_db` construyen/eliminan de verdad una semantic view candidata en
Snowflake; el resto (incluido el de propagacion de errores, via `monkeypatch`) son puros y no
requieren conexion.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from conversational_analytics.ops import pr_candidate

REPO_ROOT = Path(__file__).resolve().parents[1]
SEMANTIC_VIEW_SQL = (REPO_ROOT / "snowflake" / "004_semantic_view.sql").read_text(
    encoding="utf-8"
)


# ---------------------------------------------------------------------------
# candidate_object_name / render_candidate_ddl (T001, puros)
# ---------------------------------------------------------------------------


def test_candidate_object_name_is_deterministic_per_pr() -> None:
    assert pr_candidate.candidate_object_name("42") == "CICD_DEMO.DATA.SV_PHARMA_SALES_PR42"


def test_candidate_object_name_differs_for_different_pr_numbers() -> None:
    """T009 (US2): la garantia de no colision entre PRs concurrentes depende de esto."""
    assert pr_candidate.candidate_object_name("101") != pr_candidate.candidate_object_name(
        "202"
    )


def test_render_candidate_ddl_replaces_every_occurrence() -> None:
    object_name = pr_candidate.candidate_object_name("42")

    rendered = pr_candidate.render_candidate_ddl(SEMANTIC_VIEW_SQL, object_name)

    assert rendered.count("SV_PHARMA_SALES_PR42") == 12
    assert "SV_PHARMA_SALES" not in rendered.replace("SV_PHARMA_SALES_PR42", "")


def test_render_candidate_ddl_accepts_fully_qualified_object_name_without_duplicating_schema() -> (
    None
):
    """`object_name` puede venir cualificado; solo su ultimo segmento sustituye al token."""
    object_name = "CICD_DEMO.DATA.SV_PHARMA_SALES_PR7"

    rendered = pr_candidate.render_candidate_ddl(SEMANTIC_VIEW_SQL, object_name)

    assert "CICD_DEMO.DATA.CICD_DEMO.DATA" not in rendered
    assert "CICD_DEMO.DATA.SV_PHARMA_SALES_PR7" in rendered


def test_render_candidate_ddl_is_pure() -> None:
    """No debe mutar el string de entrada ni tocar disco (FR-008: unica fuente = Git)."""
    original = SEMANTIC_VIEW_SQL

    pr_candidate.render_candidate_ddl(SEMANTIC_VIEW_SQL, pr_candidate.candidate_object_name("1"))

    assert SEMANTIC_VIEW_SQL == original


# ---------------------------------------------------------------------------
# build_candidate / drop_candidate (T003)
# ---------------------------------------------------------------------------


def _unique_pr_number() -> str:
    return f"test{uuid.uuid4().hex[:8]}"


@pytest.mark.writes_db
def test_build_and_drop_candidate_round_trip(scalar: Callable[[str], Any]) -> None:
    """Camino feliz: la candidata existe tras `build_candidate` y desaparece tras `drop_candidate`."""
    pr_number = _unique_pr_number()
    object_name = pr_candidate.candidate_object_name(pr_number)

    pr_candidate.build_candidate(pr_number)
    try:
        ddl = scalar(f"SELECT GET_DDL('SEMANTIC_VIEW', '{object_name}')")
        assert object_name.rsplit(".", 1)[-1] in ddl
    finally:
        pr_candidate.drop_candidate(pr_number)

    with pytest.raises(Exception):
        scalar(f"SELECT GET_DDL('SEMANTIC_VIEW', '{object_name}')")


@pytest.mark.writes_db
def test_build_and_drop_candidate_does_not_modify_production(
    scalar: Callable[[str], Any],
) -> None:
    """SC-002: construir/eliminar una candidata no deja ningun cambio observable en
    `SV_PHARMA_SALES` de produccion."""
    production_name = f"{pr_candidate.CANDIDATE_SCHEMA}.{pr_candidate.PRODUCTION_OBJECT_SHORT_NAME}"
    ddl_before = scalar(f"SELECT GET_DDL('SEMANTIC_VIEW', '{production_name}')")

    pr_number = _unique_pr_number()
    pr_candidate.build_candidate(pr_number)
    pr_candidate.drop_candidate(pr_number)

    ddl_after = scalar(f"SELECT GET_DDL('SEMANTIC_VIEW', '{production_name}')")

    assert ddl_after == ddl_before


def test_build_candidate_propagates_errors_from_sql_runner(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """FR-007: si falla la creacion de la candidata, el error se propaga (no se degrada en
    silencio a validar contra produccion)."""

    def _boom(sql_text: str) -> None:
        raise RuntimeError("simulated Snowflake failure")

    monkeypatch.setattr(pr_candidate.sql_runner, "run_sql_string", _boom)

    with pytest.raises(RuntimeError, match="simulated Snowflake failure"):
        pr_candidate.build_candidate("999")


def test_drop_candidate_propagates_errors_from_sql_runner(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _boom(sql_text: str) -> None:
        raise RuntimeError("simulated Snowflake failure")

    monkeypatch.setattr(pr_candidate.sql_runner, "run_sql_string", _boom)

    with pytest.raises(RuntimeError, match="simulated Snowflake failure"):
        pr_candidate.drop_candidate("999")
