"""Tests de la precedencia de resolucion de la semantic view (T009, FR-018):

`SNOWFLAKE_SEMANTIC_VIEW` (env) > `semantic_view_registry.resolve_active()` > `DEFAULT_SEMANTIC_VIEW`.

No requieren credenciales de Snowflake: `resolve_active` se sustituye por un doble en cada test.
"""

from __future__ import annotations

import pytest

from conversational_analytics import cortex_analyst
from conversational_analytics.ops import semantic_view_registry


def test_env_override_takes_precedence_over_resolve_active(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SNOWFLAKE_SEMANTIC_VIEW", "CICD_DEMO.DATA.SV_ENV_OVERRIDE")

    def _fail_if_called(**_: object) -> str:
        raise AssertionError("resolve_active no debe llamarse: el env var ya resuelve")

    monkeypatch.setattr(semantic_view_registry, "resolve_active", _fail_if_called)

    assert cortex_analyst._resolve_semantic_view() == "CICD_DEMO.DATA.SV_ENV_OVERRIDE"


def test_resolve_active_used_when_no_env_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SNOWFLAKE_SEMANTIC_VIEW", raising=False)
    monkeypatch.setattr(
        semantic_view_registry, "resolve_active", lambda **_: "SV_PHARMA_SALES_VDEADBEE"
    )

    assert (
        cortex_analyst._resolve_semantic_view() == "CICD_DEMO.DATA.SV_PHARMA_SALES_VDEADBEE"
    )


def test_default_used_when_resolve_active_raises_lookup_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("SNOWFLAKE_SEMANTIC_VIEW", raising=False)

    def _raise(**_: object) -> str:
        raise LookupError("SEMANTIC_VIEW_ACTIVE sin fila")

    monkeypatch.setattr(semantic_view_registry, "resolve_active", _raise)

    assert cortex_analyst._resolve_semantic_view() == cortex_analyst.DEFAULT_SEMANTIC_VIEW


def test_default_used_when_resolve_active_fails_to_connect(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Un fallo de conectividad (p. ej. tablas de registro aun no desplegadas en local) no debe
    tumbar la resolucion de la semantic view: cae al valor por defecto en vez de propagar."""
    monkeypatch.delenv("SNOWFLAKE_SEMANTIC_VIEW", raising=False)

    def _raise(**_: object) -> str:
        raise RuntimeError("Faltan variables de entorno de Snowflake: SNOWFLAKE_ACCOUNT")

    monkeypatch.setattr(semantic_view_registry, "resolve_active", _raise)

    assert cortex_analyst._resolve_semantic_view() == cortex_analyst.DEFAULT_SEMANTIC_VIEW
