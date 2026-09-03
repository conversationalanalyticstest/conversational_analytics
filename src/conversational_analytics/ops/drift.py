"""Deteccion de *drift* entre lo desplegado y `main` (US2/US3, FR-021, FR-022).

Funcion pura de comparacion de SHAs: no abre conexion a Snowflake ni ejecuta comandos Git. Quien
la invoca (el workflow, o el CLI de este modulo) resuelve antes los dos SHA — `deployed-good` y
el HEAD de `main` — y se los pasa ya resueltos, para que la logica de decision sea trivial de
testear sin credenciales ni repositorio real (T018).
"""

from __future__ import annotations

import argparse
import os
import sys
from dataclasses import dataclass

from conversational_analytics.ops import deploy


@dataclass(frozen=True)
class DriftStatus:
    """Resultado de comparar la ultima release buena conocida con el HEAD real de `main`."""

    has_drift: bool
    deployed_sha: str
    head_sha: str


def check_drift(*, deployed_sha: str, head_sha: str) -> DriftStatus:
    """Compara `deployed_sha` (tag `deployed-good`) con `head_sha` (HEAD de `main`).

    Hay drift cuando difieren: significa que `main` avanzo mas alla de lo realmente desplegado
    (p. ej. tras un rollback automatico) o que el ultimo merge nunca llego a desplegarse.
    """
    return DriftStatus(
        has_drift=deployed_sha != head_sha, deployed_sha=deployed_sha, head_sha=head_sha
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--head-sha",
        default=os.environ.get("GITHUB_SHA"),
        help="HEAD de main a comparar (por defecto, GITHUB_SHA)",
    )
    args = parser.parse_args(argv)

    if not args.head_sha:
        parser.error("falta --head-sha (o la variable de entorno GITHUB_SHA)")

    deployed_sha = deploy.read_deployed_good_sha()
    if deployed_sha is None:
        print("drift: sin tag deployed-good todavia (primer despliegue) -> sin drift")
        deploy.write_github_output("has_drift", "false")
        return 0

    status = check_drift(deployed_sha=deployed_sha, head_sha=args.head_sha)
    deploy.write_github_output("has_drift", "true" if status.has_drift else "false")
    deploy.write_github_output("deployed_sha", status.deployed_sha)
    deploy.write_github_output("head_sha", status.head_sha)
    print(
        f"drift: deployed={status.deployed_sha} head={status.head_sha} "
        f"has_drift={status.has_drift}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
