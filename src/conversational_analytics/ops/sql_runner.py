"""Aplica ficheros `.sql` idempotentes contra Snowflake.

Usa la misma conexion que el resto del proyecto (`db.get_connection()`), no el CLI `snow`: en
CI no hace falta instalar nada aparte de las dependencias de Poetry ya presentes (research.md,
D-01).
"""

from __future__ import annotations

from pathlib import Path

from conversational_analytics import db


def run_sql_string(sql_text: str) -> None:
    """Ejecuta el contenido completo de un bloque `.sql` idempotente, ya en memoria.

    Usada por `run_sql_file` (fichero en disco) y por
    `ops.deploy.apply_release_artifacts` (contenido leído de un commit histórico con
    `git show`, feature 004-ci-cd-pipeline, ADR-003).

    Args:
        sql_text: una o varias sentencias SQL, separadas por `;`.
    """
    conn = db.get_connection()
    try:
        for cursor in conn.execute_string(sql_text):
            cursor.fetchall()
    finally:
        conn.close()


def run_sql_file(path: Path | str) -> None:
    """Ejecuta el contenido completo de un fichero `.sql` idempotente, leído del disco.

    El fichero puede tener varias sentencias (p. ej. `USE ROLE`, `CREATE TABLE IF NOT EXISTS`);
    se ejecutan todas, en orden, en la misma conexión.

    Args:
        path: ruta al fichero `.sql` a ejecutar.
    """
    run_sql_string(Path(path).read_text(encoding="utf-8"))

