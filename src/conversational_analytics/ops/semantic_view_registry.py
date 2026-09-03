"""Versionado de semantic views (feature 004-ci-cd-pipeline, ADR-001).

Cada despliegue crea un objeto fisico nuevo `<base_name>_V<sha_corto>` con
`CREATE OR ALTER SEMANTIC VIEW` en vez de sobreescribir el objeto de produccion in place: eso
permite tener a la vez un candidato de PR y la version de produccion, y volver atras
(rollback/revert) recreando una version anterior desde su `DDL_TEXT` guardado, sin depender de
`git checkout` (ver contracts/semantic-view-versioning.md).
"""

from __future__ import annotations

import re
from datetime import datetime, timezone

from conversational_analytics import db

#: Identificadores validos para BASE_NAME/OBJECT_NAME: letras, digitos y guion bajo. Se valida
#: explicitamente porque OBJECT_NAME se interpola directamente en sentencias DDL (`SHOW`,
#: `DROP`) que el conector no puede parametrizar con bind variables.
_VALID_IDENTIFIER = re.compile(r"^[A-Za-z0-9_]+$")
_VALID_COMMIT_SHA = re.compile(r"^[0-9a-fA-F]{7,40}$")

SEMANTIC_VIEW_SCHEMA = "CICD_DEMO.DATA"
#: Esquema de las tablas de registro (`SEMANTIC_VIEW_VERSIONS`/`SEMANTIC_VIEW_ACTIVE`), distinto
#: del esquema donde viven los objetos fisicos de semantic view (`SEMANTIC_VIEW_SCHEMA`).
REGISTRY_SCHEMA = "CICD_DEMO.DEVOPS"


def _object_name(base_name: str, commit_sha: str) -> str:
    if not _VALID_IDENTIFIER.match(base_name):
        raise ValueError(f"base_name invalido: {base_name!r}")
    if not _VALID_COMMIT_SHA.match(commit_sha):
        raise ValueError(f"commit_sha invalido: {commit_sha!r}")
    sha_corto = commit_sha[:7].upper()
    return f"{base_name}_V{sha_corto}"


def deploy_version(
    *, base_name: str, ddl_template: str, commit_sha: str, is_candidate: bool
) -> str:
    """Crea `<base_name>_V<sha_corto>` y registra la version en `SEMANTIC_VIEW_VERSIONS`.

    No toca `SEMANTIC_VIEW_ACTIVE`: eso lo hace `activate_version`, en un paso aparte.

    Args:
        base_name: nombre logico de la semantic view (p. ej. `SV_PHARMA_SALES`).
        ddl_template: contenido de `snowflake/004_semantic_view.sql` tal cual, con
            `base_name` apareciendo como el nombre del objeto y en las referencias
            completamente cualificadas de `AI_VERIFIED_QUERIES`.
        commit_sha: commit del que procede esta definicion.
        is_candidate: `True` para un despliegue de validacion de PR (no promocionable sin
            pasar por `activate_version`), `False` para una version de produccion.

    Returns:
        El `OBJECT_NAME` creado.
    """
    object_name = _object_name(base_name, commit_sha)
    rendered_ddl = ddl_template.replace(base_name, object_name)

    conn = db.get_connection()
    try:
        for cursor in conn.execute_string(rendered_ddl):
            cursor.fetchall()
        with conn.cursor() as cur:
            cur.execute(
                f"""
                INSERT INTO {REGISTRY_SCHEMA}.SEMANTIC_VIEW_VERSIONS (
                    BASE_NAME, OBJECT_NAME, COMMIT_SHA, DDL_TEXT, IS_CANDIDATE
                ) VALUES (
                    %(base_name)s, %(object_name)s, %(commit_sha)s, %(ddl_text)s,
                    %(is_candidate)s
                )
                """,
                {
                    "base_name": base_name,
                    "object_name": object_name,
                    "commit_sha": commit_sha,
                    "ddl_text": rendered_ddl,
                    "is_candidate": is_candidate,
                },
            )
        conn.commit()
    finally:
        conn.close()
    return object_name


def activate_version(*, base_name: str, commit_sha: str, updated_by: str) -> None:
    """Promociona `(base_name, commit_sha)` a version activa de produccion.

    Recrea el objeto fisico desde su `DDL_TEXT` si ya fue purgado por
    `cleanup_old_versions`, y actualiza `SEMANTIC_VIEW_ACTIVE` (MERGE por `BASE_NAME`).

    Raises:
        LookupError: si no hay ninguna version de produccion (`IS_CANDIDATE = FALSE`) de
            `(base_name, commit_sha)` en `SEMANTIC_VIEW_VERSIONS`.
    """
    conn = db.get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT OBJECT_NAME, DDL_TEXT
                FROM {REGISTRY_SCHEMA}.SEMANTIC_VIEW_VERSIONS
                WHERE BASE_NAME = %(base_name)s AND COMMIT_SHA = %(commit_sha)s
                      AND IS_CANDIDATE = FALSE
                ORDER BY DEPLOYED_AT DESC
                LIMIT 1
                """,
                {"base_name": base_name, "commit_sha": commit_sha},
            )
            row = cur.fetchone()
            if row is None:
                raise LookupError(
                    f"No hay version de produccion de {base_name} para el commit "
                    f"{commit_sha} en SEMANTIC_VIEW_VERSIONS"
                )
            object_name, ddl_text = row
            if not _VALID_IDENTIFIER.match(object_name):
                raise ValueError(f"OBJECT_NAME invalido en el registro: {object_name!r}")

            cur.execute(
                f"SHOW SEMANTIC VIEWS LIKE '{object_name}' IN SCHEMA {SEMANTIC_VIEW_SCHEMA}"
            )
            exists = cur.fetchone() is not None
            if not exists:
                for cursor in conn.execute_string(ddl_text):
                    cursor.fetchall()

            cur.execute(
                f"""
                MERGE INTO {REGISTRY_SCHEMA}.SEMANTIC_VIEW_ACTIVE AS target
                USING (SELECT %(base_name)s AS BASE_NAME) AS source
                ON target.BASE_NAME = source.BASE_NAME
                WHEN MATCHED THEN UPDATE SET
                    ACTIVE_OBJECT_NAME = %(object_name)s,
                    ACTIVE_COMMIT_SHA = %(commit_sha)s,
                    UPDATED_AT = %(updated_at)s,
                    UPDATED_BY = %(updated_by)s
                WHEN NOT MATCHED THEN INSERT (
                    BASE_NAME, ACTIVE_OBJECT_NAME, ACTIVE_COMMIT_SHA, UPDATED_AT, UPDATED_BY
                ) VALUES (
                    %(base_name)s, %(object_name)s, %(commit_sha)s, %(updated_at)s,
                    %(updated_by)s
                )
                """,
                {
                    "base_name": base_name,
                    "object_name": object_name,
                    "commit_sha": commit_sha,
                    "updated_at": datetime.now(timezone.utc),
                    "updated_by": updated_by,
                },
            )
        conn.commit()
    finally:
        conn.close()


def resolve_active(*, base_name: str) -> str:
    """Devuelve `ACTIVE_OBJECT_NAME` para `base_name`.

    Usada por `cortex_analyst.py` cuando no hay override explicito de
    `SNOWFLAKE_SEMANTIC_VIEW`.

    Raises:
        LookupError: si `SEMANTIC_VIEW_ACTIVE` no tiene fila para `base_name` (entorno
            recien creado, todavia sin ningun despliegue completo). El llamador interpreta
            esto como "usar `DEFAULT_SEMANTIC_VIEW`".
    """
    conn = db.get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                f"SELECT ACTIVE_OBJECT_NAME FROM {REGISTRY_SCHEMA}.SEMANTIC_VIEW_ACTIVE "
                "WHERE BASE_NAME = %(base_name)s",
                {"base_name": base_name},
            )
            row = cur.fetchone()
    finally:
        conn.close()
    if row is None:
        raise LookupError(f"SEMANTIC_VIEW_ACTIVE no tiene fila para {base_name}")
    return row[0]


def drop_candidate(*, object_name: str) -> None:
    """Elimina un objeto candidato de PR (US1) desechable creado por `deploy_version(...,
    is_candidate=True)`.

    No toca `SEMANTIC_VIEW_VERSIONS` (el candidato ya quedo registrado ahi con
    `IS_CANDIDATE=TRUE`, para trazabilidad) ni `SEMANTIC_VIEW_ACTIVE` (un candidato nunca se
    activa). Se invoca desde el paso `if: always()` de `pr-checks.yml`.
    """
    if not _VALID_IDENTIFIER.match(object_name):
        raise ValueError(f"OBJECT_NAME invalido: {object_name!r}")
    conn = db.get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(f"DROP SEMANTIC VIEW IF EXISTS {SEMANTIC_VIEW_SCHEMA}.{object_name}")
        conn.commit()
    finally:
        conn.close()


def cleanup_old_versions(*, base_name: str, keep_last: int = 5) -> list[str]:
    """Elimina el objeto fisico de las versiones de produccion mas antiguas que las
    `keep_last` mas recientes, sin tocar nunca la version activa actual.

    Las filas de `SEMANTIC_VIEW_VERSIONS` **no** se borran: el `DDL_TEXT` se conserva para
    poder recrear la version desde `activate_version` si hiciera falta mas adelante.

    Returns:
        Los `OBJECT_NAME` eliminados, en el orden en que se borraron (mas antiguo primero).
    """
    conn = db.get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT OBJECT_NAME
                FROM {REGISTRY_SCHEMA}.SEMANTIC_VIEW_VERSIONS
                WHERE BASE_NAME = %(base_name)s AND IS_CANDIDATE = FALSE
                ORDER BY DEPLOYED_AT DESC
                """,
                {"base_name": base_name},
            )
            all_versions = [row[0] for row in cur.fetchall()]

            cur.execute(
                f"SELECT ACTIVE_OBJECT_NAME FROM {REGISTRY_SCHEMA}.SEMANTIC_VIEW_ACTIVE "
                "WHERE BASE_NAME = %(base_name)s",
                {"base_name": base_name},
            )
            active_row = cur.fetchone()
            active_object_name = active_row[0] if active_row else None

            # `all_versions` viene en orden DEPLOYED_AT DESC (mas reciente primero); se
            # invierte para que `to_drop` quede en orden "mas antiguo primero", como
            # documenta el valor de retorno.
            to_drop = [
                name
                for name in reversed(all_versions[keep_last:])
                if name != active_object_name
            ]
            for object_name in to_drop:
                if not _VALID_IDENTIFIER.match(object_name):
                    raise ValueError(f"OBJECT_NAME invalido en el registro: {object_name!r}")
                cur.execute(
                    f"DROP SEMANTIC VIEW IF EXISTS {SEMANTIC_VIEW_SCHEMA}.{object_name}"
                )
        conn.commit()
    finally:
        conn.close()
    return to_drop
