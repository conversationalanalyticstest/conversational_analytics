"""CLI de despliegue: release completa de produccion.

Invocado siempre como `python -m conversational_analytics.ops.deploy` desde `deploy.yml` (ver
contracts/workflows.md). `apply_release_artifacts` es la logica compartida que tambien
reutilizan `ops/rollback.py` y `ops/revert.py` para re-desplegar una release anterior: lee cada
script SQL tal como estaba en el commit objetivo (`git show`), no del working tree actual (ver
ADR-003, decisions/003-simplificacion-semantic-view.md).
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

from conversational_analytics.ops import deployments_log, sql_runner

DEPLOYED_GOOD_TAG = "deployed-good"

REPO_ROOT = Path(__file__).resolve().parents[3]

#: Scripts idempotentes que se re-aplican en cada release completa, incluida la semantic view
#: (`004_semantic_view.sql`, `CREATE OR ALTER` sobre un unico objeto fisico, sin sufijo de
#: commit). No incluye `001_bootstrap.sql` (requiere ACCOUNTADMIN; es infraestructura de una
#: sola vez, la aplica un humano, ver snowflake/README.md).
RELEASE_SQL_SCRIPTS = (
    "002_tables.sql",
    "003_seed.sql",
    "004_semantic_view.sql",
    "005_telemetry.sql",
    "006_deployments.sql",
)


def _resolve_commit_sha() -> str:
    """SHA del commit a desplegar: `GITHUB_SHA` en CI, `git rev-parse HEAD` en local."""
    sha = os.environ.get("GITHUB_SHA")
    if sha:
        return sha
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        check=True,
        cwd=REPO_ROOT,
    )
    return result.stdout.strip()


def resolve_actor() -> str:
    """Actor de GitHub que dispara la accion. En CI, `GITHUB_ACTOR`; si no esta, el bot."""
    return os.environ.get("GITHUB_ACTOR") or "github-actions[bot]"


def resolve_workflow_run_url() -> str:
    server = os.environ.get("GITHUB_SERVER_URL", "")
    repo = os.environ.get("GITHUB_REPOSITORY", "")
    run_id = os.environ.get("GITHUB_RUN_ID", "")
    if server and repo and run_id:
        return f"{server}/{repo}/actions/runs/{run_id}"
    return "local"


def write_github_output(name: str, value: str) -> None:
    """Anota `name=value` en `$GITHUB_OUTPUT` si el workflow lo define; no-op en local."""
    output_path = os.environ.get("GITHUB_OUTPUT")
    if not output_path:
        return
    with open(output_path, "a", encoding="utf-8") as fh:
        fh.write(f"{name}={value}\n")


def read_deployed_good_sha() -> str | None:
    """Lee el tag Git `deployed-good` (puntero operativo de la ultima release buena, ADR-002).

    Returns:
        El SHA al que apunta el tag, o `None` si el tag no existe todavia (primer despliegue).
    """
    try:
        result = subprocess.run(
            ["git", "rev-parse", DEPLOYED_GOOD_TAG],
            capture_output=True,
            text=True,
            check=True,
            cwd=REPO_ROOT,
        )
        return result.stdout.strip() or None
    except (OSError, subprocess.CalledProcessError):
        return None


def move_deployed_good_tag(commit_sha: str) -> None:
    """Mueve el tag Git ligero `deployed-good` a `commit_sha` y lo empuja al remoto.

    Se invoca solo tras confirmar que una release quedo sana (evaluacion post-deploy en verde,
    o rollback/revert completados con exito): es el puntero que usa `ops/rollback.py` para
    saber a que volver.
    """
    subprocess.run(["git", "tag", "-f", DEPLOYED_GOOD_TAG, commit_sha], check=True, cwd=REPO_ROOT)
    subprocess.run(
        ["git", "push", "origin", DEPLOYED_GOOD_TAG, "--force"], check=True, cwd=REPO_ROOT
    )


def _read_sql_at_commit(commit_sha: str, script_name: str) -> str:
    """Lee `snowflake/<script_name>` tal como estaba definido en `commit_sha`.

    Usa `git show <sha>:<path>`, que solo lee el blob de ese commit: no modifica el working
    tree ni requiere que el checkout este en ese commit (a diferencia de `git checkout <sha> --
    <path>`). Requiere historial completo (`fetch-depth: 0`, ya usado en los 3 workflows).
    """
    relative_path = f"snowflake/{script_name}"
    result = subprocess.run(
        ["git", "show", f"{commit_sha}:{relative_path}"],
        capture_output=True,
        text=True,
        check=True,
        cwd=REPO_ROOT,
    )
    return result.stdout


def apply_release_artifacts(commit_sha: str) -> None:
    """Aplica los artefactos de una release: cada script de `RELEASE_SQL_SCRIPTS` (incluida la
    semantic view) tal como estaba definido en `commit_sha` (ADR-003).

    No registra nada en `DEPLOYMENTS` ni mueve el tag `deployed-good`: eso es responsabilidad
    de quien llama (`deploy_release`, `ops/rollback.py`, `ops/revert.py`), que conoce el
    `ACTION`/`TRIGGERED_BY` correcto para su caso.
    """
    for script_name in RELEASE_SQL_SCRIPTS:
        sql_text = _read_sql_at_commit(commit_sha, script_name)
        sql_runner.run_sql_string(sql_text)


def deploy_release(*, commit_sha: str | None = None) -> None:
    """Release completa de produccion (US2): aplica los artefactos y registra la fila
    `ACTION=DEPLOY` en `DEPLOYMENTS`.

    No mueve el tag `deployed-good`: el workflow lo hace en un paso aparte, **despues** de que
    la evaluacion post-deploy confirme que la release quedo sana (contracts/workflows.md,
    `deploy.yml` paso 7; ADR-002).
    """
    sha = commit_sha or _resolve_commit_sha()
    previous = deployments_log.last_successful_deploy()
    previous_sha = previous["target_commit_sha"] if previous else None

    apply_release_artifacts(sha)

    deployments_log.record(
        action="DEPLOY",
        target_commit_sha=sha,
        previous_commit_sha=previous_sha,
        status="SUCCESS",
        reason=None,
        triggered_by=resolve_actor(),
        workflow_run_url=resolve_workflow_run_url(),
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--confirm",
        metavar="SHA",
        help="Mueve el tag deployed-good a SHA (paso 7 del contrato, evaluacion post-deploy en verde)",
    )
    args = parser.parse_args(argv)

    if args.confirm:
        move_deployed_good_tag(args.confirm)
        print(f"Tag {DEPLOYED_GOOD_TAG} movido a {args.confirm}")
    else:
        sha = _resolve_commit_sha()
        deploy_release(commit_sha=sha)
        print(f"Release desplegada. Commit: {sha}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
