"""CLI de despliegue: candidato de PR (`--candidate`) o release completa de produccion.

Invocado siempre como `python -m conversational_analytics.ops.deploy [--candidate]` desde los
workflows (ver contracts/workflows.md). `apply_release_artifacts` es la logica compartida que
tambien reutilizan `ops/rollback.py` y `ops/revert.py` para re-desplegar una release anterior.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

from conversational_analytics.ops import deployments_log, semantic_view_registry, sql_runner

BASE_NAME = "SV_PHARMA_SALES"
DEPLOYED_GOOD_TAG = "deployed-good"

REPO_ROOT = Path(__file__).resolve().parents[3]
SNOWFLAKE_DIR = REPO_ROOT / "snowflake"
SEMANTIC_VIEW_DDL_PATH = SNOWFLAKE_DIR / "004_semantic_view.sql"

#: Scripts idempotentes que se re-aplican en cada release completa. No incluye
#: `001_bootstrap.sql` (requiere ACCOUNTADMIN; es infraestructura de una sola vez, la aplica un
#: humano, ver snowflake/README.md) ni `004_semantic_view.sql` (se versiona aparte via
#: `semantic_view_registry`, nunca se sobreescribe in place).
RELEASE_SQL_SCRIPTS = (
    "002_tables.sql",
    "003_seed.sql",
    "005_telemetry.sql",
    "006_deployments.sql",
    "007_semantic_view_registry.sql",
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


def apply_release_artifacts(commit_sha: str) -> str:
    """Aplica los artefactos de una release: scripts SQL idempotentes + version de semantic
    view activada + limpieza de versiones antiguas (T033/US5).

    No registra nada en `DEPLOYMENTS` ni mueve el tag `deployed-good`: eso es responsabilidad
    de quien llama (`deploy_release`, `ops/rollback.py`, `ops/revert.py`), que conoce el
    `ACTION`/`TRIGGERED_BY` correcto para su caso.

    Returns:
        El `OBJECT_NAME` de semantic view activado.
    """
    for script_name in RELEASE_SQL_SCRIPTS:
        sql_runner.run_sql_file(SNOWFLAKE_DIR / script_name)

    ddl_template = SEMANTIC_VIEW_DDL_PATH.read_text(encoding="utf-8")
    semantic_view_registry.deploy_version(
        base_name=BASE_NAME, ddl_template=ddl_template, commit_sha=commit_sha, is_candidate=False
    )
    semantic_view_registry.activate_version(
        base_name=BASE_NAME, commit_sha=commit_sha, updated_by=resolve_actor()
    )

    dropped = semantic_view_registry.cleanup_old_versions(base_name=BASE_NAME)
    if dropped:
        print(f"cleanup_old_versions: eliminadas {len(dropped)} version(es) antigua(s): {dropped}")

    return semantic_view_registry.resolve_active(base_name=BASE_NAME)


def deploy_candidate(*, commit_sha: str | None = None) -> str:
    """Modo `--candidate` (US1): despliega una semantic view candidata para validar una PR.

    No toca `DEPLOYMENTS` ni `SEMANTIC_VIEW_ACTIVE`, ni aplica el resto de scripts SQL: es un
    objeto desechable que el propio workflow borra con `if: always()` al final de
    `pr-checks.yml`.

    Returns:
        El `OBJECT_NAME` creado (para `SNOWFLAKE_SEMANTIC_VIEW` / `$GITHUB_OUTPUT`).
    """
    sha = commit_sha or _resolve_commit_sha()
    ddl_template = SEMANTIC_VIEW_DDL_PATH.read_text(encoding="utf-8")
    object_name = semantic_view_registry.deploy_version(
        base_name=BASE_NAME, ddl_template=ddl_template, commit_sha=sha, is_candidate=True
    )
    write_github_output("object_name", object_name)
    return object_name


def deploy_release(*, commit_sha: str | None = None) -> str:
    """Release completa de produccion (US2): aplica los artefactos y registra la fila
    `ACTION=DEPLOY` en `DEPLOYMENTS`.

    No mueve el tag `deployed-good`: el workflow lo hace en un paso aparte, **despues** de que
    la evaluacion post-deploy confirme que la release quedo sana (contracts/workflows.md,
    `deploy.yml` paso 7; ADR-002).

    Returns:
        El `OBJECT_NAME` de semantic view activado.
    """
    sha = commit_sha or _resolve_commit_sha()
    previous = deployments_log.last_successful_deploy()
    previous_sha = previous["target_commit_sha"] if previous else None

    object_name = apply_release_artifacts(sha)

    deployments_log.record(
        action="DEPLOY",
        target_commit_sha=sha,
        previous_commit_sha=previous_sha,
        status="SUCCESS",
        reason=None,
        triggered_by=resolve_actor(),
        workflow_run_url=resolve_workflow_run_url(),
    )
    return object_name


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--candidate", action="store_true", help="Despliega una semantic view candidata de PR"
    )
    group.add_argument(
        "--confirm",
        metavar="SHA",
        help="Mueve el tag deployed-good a SHA (paso 7 del contrato, evaluacion post-deploy en verde)",
    )
    group.add_argument(
        "--drop-candidate",
        metavar="OBJECT_NAME",
        help="Elimina el objeto candidato de PR (paso if: always() de pr-checks.yml)",
    )
    args = parser.parse_args(argv)

    if args.candidate:
        object_name = deploy_candidate()
        print(f"Semantic view candidata desplegada: {object_name}")
    elif args.confirm:
        move_deployed_good_tag(args.confirm)
        print(f"Tag {DEPLOYED_GOOD_TAG} movido a {args.confirm}")
    elif args.drop_candidate:
        semantic_view_registry.drop_candidate(object_name=args.drop_candidate)
        print(f"Candidato eliminado: {args.drop_candidate}")
    else:
        object_name = deploy_release()
        print(f"Release desplegada. Semantic view activa: {object_name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
