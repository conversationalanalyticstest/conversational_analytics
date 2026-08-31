"""Smoke test de conectividad (T006).

Si estos tests fallan, ningun otro test de la suite puede pasar: el problema esta en el `.env`
o en los permisos del rol, no en los datos.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

EXPECTED_ROLE = "CICD_DEMO_ROLE"
EXPECTED_DATABASE = "CICD_DEMO"


def test_connection_works(scalar: Callable[[str], Any]) -> None:
    assert scalar("SELECT 1") == 1


def test_session_context_is_the_project_one(fetch_one: Callable[[str], Any]) -> None:
    row = fetch_one("SELECT CURRENT_ROLE(), CURRENT_DATABASE()")
    assert row is not None
    role, database = row
    assert role == EXPECTED_ROLE, (
        f"El rol activo es {role!r}, se esperaba {EXPECTED_ROLE!r}. Revisa SNOWFLAKE_ROLE en .env."
    )
    assert database == EXPECTED_DATABASE, (
        f"La base activa es {database!r}, se esperaba {EXPECTED_DATABASE!r}. "
        "Revisa SNOWFLAKE_DATABASE en .env."
    )
