"""Fixtures compartidas de la suite.

Una unica conexion a Snowflake para toda la sesion de tests: abrir una por test multiplicaria
la latencia sin aportar aislamiento (los tests son de solo lectura salvo los marcados
`writes_db`).
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from typing import Any

import pytest

from conversational_analytics.db import get_connection


@pytest.fixture(scope="session")
def sf_conn() -> Iterator[Any]:
    """Conexion a Snowflake compartida por toda la sesion de tests."""
    conn = get_connection()
    try:
        yield conn
    finally:
        conn.close()


@pytest.fixture(scope="session")
def fetch_one(sf_conn: Any) -> Callable[[str], tuple[Any, ...] | None]:
    """Ejecuta una consulta y devuelve la primera fila (o None si no hay resultados)."""

    def _fetch_one(sql: str) -> tuple[Any, ...] | None:
        with sf_conn.cursor() as cur:
            cur.execute(sql)
            return cur.fetchone()

    return _fetch_one


@pytest.fixture(scope="session")
def fetch_all(sf_conn: Any) -> Callable[[str], list[tuple[Any, ...]]]:
    """Ejecuta una consulta y devuelve todas las filas."""

    def _fetch_all(sql: str) -> list[tuple[Any, ...]]:
        with sf_conn.cursor() as cur:
            cur.execute(sql)
            return cur.fetchall()

    return _fetch_all


@pytest.fixture(scope="session")
def scalar(fetch_one: Callable[[str], tuple[Any, ...] | None]) -> Callable[[str], Any]:
    """Ejecuta una consulta que devuelve un unico valor y lo extrae."""

    def _scalar(sql: str) -> Any:
        row = fetch_one(sql)
        assert row is not None, f"La consulta no devolvio ninguna fila:\n{sql}"
        return row[0]

    return _scalar
