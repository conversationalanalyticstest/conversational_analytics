"""Revert manual a una release anterior ya desplegada (US4, ADR-001, FR-012 a FR-014).

Cualquier miembro del equipo puede disparar `revert.yml` con un `target_commit_sha`; este modulo
valida ese SHA contra `DEPLOYMENTS` **antes** de tocar Snowflake (FR-014) y reutiliza la misma
logica de despliegue que `ops/deploy.py`.
"""

from __future__ import annotations

import argparse
import sys

from conversational_analytics.ops import deploy, deployments_log


class InvalidRevertTargetError(Exception):
    """`target_commit_sha` no tiene ninguna fila `STATUS='SUCCESS'` en `DEPLOYMENTS`."""


def revert(*, target_commit_sha: str) -> str:
    """Re-despliega `target_commit_sha` y registra `ACTION=MANUAL_REVERT`.

    Args:
        target_commit_sha: commit al que se quiere volver. MUST tener una fila
            `STATUS='SUCCESS'` en `DEPLOYMENTS` (FR-014); si no, se rechaza sin tocar Snowflake.

    Returns:
        `target_commit_sha`, tras confirmarse el revert.

    Raises:
        InvalidRevertTargetError: `target_commit_sha` no tiene ningun despliegue exitoso
            registrado.
    """
    if not deployments_log.exists_successful_deploy(target_commit_sha=target_commit_sha):
        raise InvalidRevertTargetError(
            f"{target_commit_sha} no tiene ningun despliegue SUCCESS registrado en "
            "DEPLOYMENTS: revert rechazado sin tocar Snowflake"
        )

    actor = deploy.resolve_actor()
    workflow_run_url = deploy.resolve_workflow_run_url()
    previous = deployments_log.last_successful_deploy()
    previous_sha = previous["target_commit_sha"] if previous else None

    deploy.apply_release_artifacts(target_commit_sha)

    deployments_log.record(
        action="MANUAL_REVERT",
        target_commit_sha=target_commit_sha,
        previous_commit_sha=previous_sha,
        status="SUCCESS",
        reason=f"Revert manual disparado por {actor}",
        triggered_by=actor,
        workflow_run_url=workflow_run_url,
    )
    deploy.move_deployed_good_tag(target_commit_sha)
    return target_commit_sha


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--target", required=True, dest="target_commit_sha", help="Commit SHA al que revertir"
    )
    args = parser.parse_args(argv)

    try:
        revert(target_commit_sha=args.target_commit_sha)
    except InvalidRevertTargetError as exc:
        print(f"Revert rechazado: {exc}", file=sys.stderr)
        return 1

    print(f"Revert completado: Snowflake vuelve a {args.target_commit_sha}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
