"""Registro insert-only de despliegues/rollbacks/reverts (tabla `CICD_DEMO.DEVOPS.DEPLOYMENTS`).

Unica puerta de entrada para escribir en esa tabla; ningun otro modulo hace
`INSERT INTO DEPLOYMENTS` directamente (misma disciplina que `Telemetry.record` en
`telemetry.py`, ver contracts/deployments-table.md).
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from conversational_analytics import db

VALID_ACTIONS = ("DEPLOY", "AUTO_ROLLBACK", "MANUAL_REVERT")
VALID_STATUSES = ("SUCCESS", "FAILED")


def record(
    *,
    action: str,
    target_commit_sha: str,
    status: str,
    triggered_by: str,
    workflow_run_url: str,
    previous_commit_sha: str | None = None,
    reason: str | None = None,
) -> str:
    """Inserta una fila en `DEPLOYMENTS` y devuelve el `DEPLOYMENT_ID` generado.

    Args:
        action: `DEPLOY` | `AUTO_ROLLBACK` | `MANUAL_REVERT`.
        target_commit_sha: commit que queda desplegado tras esta accion.
        status: `SUCCESS` | `FAILED`.
        triggered_by: `github-actions[bot]` para acciones automaticas, o el actor de GitHub
            que disparo un revert manual.
        workflow_run_url: URL del run de GitHub Actions que genero la fila.
        previous_commit_sha: commit que estaba desplegado antes. Obligatorio para
            `AUTO_ROLLBACK` y `MANUAL_REVERT` (siempre hay un estado anterior del que se viene).
        reason: motivo legible (p. ej. el test que fallo en la evaluacion post-deploy).

    Raises:
        ValueError: `action`/`status` con un valor no reconocido, o falta
            `previous_commit_sha` en una accion que lo requiere.
    """
    if action not in VALID_ACTIONS:
        raise ValueError(f"ACTION invalido: {action!r} (validos: {VALID_ACTIONS})")
    if status not in VALID_STATUSES:
        raise ValueError(f"STATUS invalido: {status!r} (validos: {VALID_STATUSES})")
    if action in ("AUTO_ROLLBACK", "MANUAL_REVERT") and not previous_commit_sha:
        raise ValueError(f"{action} requiere previous_commit_sha")

    deployment_id = str(uuid.uuid4())
    conn = db.get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO CICD_DEMO.DEVOPS.DEPLOYMENTS (
                    DEPLOYMENT_ID, ACTION, TARGET_COMMIT_SHA, PREVIOUS_COMMIT_SHA,
                    STATUS, REASON, TRIGGERED_BY, WORKFLOW_RUN_URL, DEPLOYED_AT
                ) VALUES (
                    %(id)s, %(action)s, %(target)s, %(previous)s,
                    %(status)s, %(reason)s, %(triggered_by)s, %(url)s, %(deployed_at)s
                )
                """,
                {
                    "id": deployment_id,
                    "action": action,
                    "target": target_commit_sha,
                    "previous": previous_commit_sha,
                    "status": status,
                    "reason": reason,
                    "triggered_by": triggered_by,
                    "url": workflow_run_url,
                    "deployed_at": datetime.now(timezone.utc),
                },
            )
        conn.commit()
    finally:
        conn.close()
    return deployment_id


def last_successful_deploy(*, exclude_commit_sha: str | None = None) -> dict[str, Any] | None:
    """Devuelve la fila `STATUS='SUCCESS'` mas reciente de `DEPLOYMENTS`.

    Usada por `ops/rollback.py` para localizar la ultima release buena conocida (excluyendo,
    si se pasa, el commit que acaba de fallar la evaluacion post-deploy: esa fila tambien tiene
    `STATUS='SUCCESS'` porque el despliegue en si funciono, aunque la evaluacion posterior no).

    Returns:
        `{"target_commit_sha": ..., "deployed_at": ...}`, o `None` si no hay ninguna fila
        `SUCCESS` (entorno recien creado, primer despliegue del proyecto).
    """
    conn = db.get_connection()
    try:
        with conn.cursor() as cur:
            if exclude_commit_sha:
                cur.execute(
                    """
                    SELECT TARGET_COMMIT_SHA, DEPLOYED_AT
                    FROM CICD_DEMO.DEVOPS.DEPLOYMENTS
                    WHERE STATUS = 'SUCCESS' AND TARGET_COMMIT_SHA != %(sha)s
                    ORDER BY DEPLOYED_AT DESC
                    LIMIT 1
                    """,
                    {"sha": exclude_commit_sha},
                )
            else:
                cur.execute(
                    """
                    SELECT TARGET_COMMIT_SHA, DEPLOYED_AT
                    FROM CICD_DEMO.DEVOPS.DEPLOYMENTS
                    WHERE STATUS = 'SUCCESS'
                    ORDER BY DEPLOYED_AT DESC
                    LIMIT 1
                    """
                )
            row = cur.fetchone()
    finally:
        conn.close()
    if row is None:
        return None
    return {"target_commit_sha": row[0], "deployed_at": row[1]}


def latest_row() -> dict[str, Any] | None:
    """Devuelve `ACTION`/`REASON`/`TARGET_COMMIT_SHA` de la fila mas reciente de `DEPLOYMENTS`.

    A diferencia de `last_successful_deploy`, no filtra por `STATUS`: sirve para que `ops/drift.py`
    incluya el motivo de la ultima accion (exitosa o no) en el Issue de drift (D-09,
    research.md), sin importar si esa fila fue un deploy, un rollback o un revert.

    Returns:
        `{"action": ..., "reason": ..., "target_commit_sha": ...}`, o `None` si `DEPLOYMENTS`
        todavia no tiene ninguna fila.
    """
    conn = db.get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT ACTION, REASON, TARGET_COMMIT_SHA
                FROM CICD_DEMO.DEVOPS.DEPLOYMENTS
                ORDER BY DEPLOYED_AT DESC
                LIMIT 1
                """
            )
            row = cur.fetchone()
    finally:
        conn.close()
    if row is None:
        return None
    return {"action": row[0], "reason": row[1], "target_commit_sha": row[2]}


def exists_successful_deploy(*, target_commit_sha: str) -> bool:
    """FR-014: valida que un SHA objetivo de revert tenga un despliegue exitoso registrado.

    Se consulta **antes** de tocar Snowflake: un SHA inventado se rechaza sin ningun efecto.
    """
    conn = db.get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT COUNT(*) FROM CICD_DEMO.DEVOPS.DEPLOYMENTS
                WHERE TARGET_COMMIT_SHA = %(sha)s AND STATUS = 'SUCCESS'
                """,
                {"sha": target_commit_sha},
            )
            (count,) = cur.fetchone()
    finally:
        conn.close()
    return count > 0
