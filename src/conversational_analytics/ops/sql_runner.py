"""Aplica ficheros `.sql` idempotentes contra Snowflake.

Usa la misma conexion que el resto del proyecto (`db.get_connection()`), no el CLI `snow`: en
CI no hace falta instalar nada aparte de las dependencias de Poetry ya presentes (research.md,
D-01).
"""

from __future__ import annotations

from pathlib import Path

from conversational_analytics import db


def run_sql_file(path: Path | str) -> None:
    """Ejecuta el contenido completo de un fichero `.sql` idempotente.

    El fichero puede tener varias sentencias (p. ej. `USE ROLE`, `CREATE TABLE IF NOT EXISTS`);
    se ejecutan todas, en orden, en la misma conexion.

    Args:
        path: ruta al fichero `.sql` a ejecutar.
    """
    sql_text = Path(path).read_text(encoding="utf-8")
    conn = db.get_connection()
    try:
        for cursor in conn.execute_string(sql_text):
            cursor.fetchall()
    finally:
        conn.close()
