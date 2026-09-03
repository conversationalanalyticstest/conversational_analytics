"""Tests de la precedencia de resolucion de la semantic view (ADR-003):

`SNOWFLAKE_SEMANTIC_VIEW` (env) > `DEFAULT_SEMANTIC_VIEW`.

No requieren credenciales de Snowflake: la semantic view es un unico objeto fisico, sin
mecanismo de versionado propio (ver contracts/semantic-view-versioning.md).
"""

from __future__ import annotations

import pytest

from conversational_analytics import cortex_analyst


def test_env_override_takes_precedence_over_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SNOWFLAKE_SEMANTIC_VIEW", "CICD_DEMO.DATA.SV_ENV_OVERRIDE")

    assert cortex_analyst._resolve_semantic_view() == "CICD_DEMO.DATA.SV_ENV_OVERRIDE"


def test_default_used_when_no_env_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SNOWFLAKE_SEMANTIC_VIEW", raising=False)

    assert cortex_analyst._resolve_semantic_view() == cortex_analyst.DEFAULT_SEMANTIC_VIEW

