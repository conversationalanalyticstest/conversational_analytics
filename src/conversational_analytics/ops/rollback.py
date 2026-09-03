"""Rollback automatico ante un fallo de la evaluacion post-deploy (US3, ADR-002, FR-009 a FR-011).

*Forward-fix*: no se "deshace" nada, se vuelve a desplegar la ultima release buena conocida con
la misma logica de `ops/deploy.py`. Si el propio rollback falla, el job termina en rojo sin
reintentar (FR-011): un rollback que reintenta indefinidamente puede agravar un incidente.
"""

from __future__ import annotations

import argparse
import sys

from conversational_analytics.ops import deploy, deployments_log


def resolve_rollback_target(*, failed_sha: str) -> str:
    """Localiza el commit al que hay que volver: el tag Git `deployed-good` si existe y no
    coincide con `failed_sha`; si no, la ultima fila `SUCCESS` de `DEPLOYMENTS` distinta de
    `failed_sha` (T024).

    Raises:
        RuntimeError: no hay ninguna release `SUCCESS` anterior a `failed_sha` en `DEPLOYMENTS`
            (no hay a donde volver: incidente que requiere intervencion manual).
    """
    tag_sha = deploy.read_deployed_good_sha()
    if tag_sha and tag_sha != failed_sha:
        return tag_sha

    previous = deployments_log.last_successful_deploy(exclude_commit_sha=failed_sha)
    if previous is None:
        raise RuntimeError(
            "No hay ninguna release SUCCESS anterior a "
            f"{failed_sha} en DEPLOYMENTS: no hay a donde hacer rollback"
        )
    return previous["target_commit_sha"]


def rollback(*, failed_sha: str) -> str:
    """Ejecuta el rollback automatico completo: localiza el objetivo, re-despliega esa release,
    registra `ACTION=AUTO_ROLLBACK` y confirma el tag `deployed-good`.

    Returns:
        El commit SHA al que se volvio.

    Raises:
        Exception: si `apply_release_artifacts` falla, se registra la fila `STATUS='FAILED'`
            y se relanza la excepcion (FR-011: sin reintentos, el job debe terminar en rojo).
    """
    target_sha = resolve_rollback_target(failed_sha=failed_sha)
    actor = deploy.resolve_actor()
    workflow_run_url = deploy.resolve_workflow_run_url()

    try:
        deploy.apply_release_artifacts(target_sha)
    except Exception as exc:
        deployments_log.record(
            action="AUTO_ROLLBACK",
            target_commit_sha=target_sha,
            previous_commit_sha=failed_sha,
            status="FAILED",
            reason=str(exc),
            triggered_by=actor,
            workflow_run_url=workflow_run_url,
        )
        raise

    deployments_log.record(
        action="AUTO_ROLLBACK",
        target_commit_sha=target_sha,
        previous_commit_sha=failed_sha,
        status="SUCCESS",
        reason="Evaluacion post-deploy fallida; forward-fix a la ultima release buena conocida",
        triggered_by=actor,
        workflow_run_url=workflow_run_url,
    )
    deploy.move_deployed_good_tag(target_sha)
    return target_sha


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--failed-sha",
        required=True,
        help="Commit que fallo la evaluacion post-deploy (GITHUB_SHA del run actual)",
    )
    args = parser.parse_args(argv)

    target_sha = rollback(failed_sha=args.failed_sha)
    print(f"Rollback completado: Snowflake vuelve a {target_sha}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
