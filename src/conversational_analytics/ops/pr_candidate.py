"""CLI para aislar el check de una PR con una semantic view candidata efimera.

Invocado desde `pr-checks.yml` (ver
`specs/005-pr-checks-semantic-isolation/contracts/pr-candidate-workflow.md`) como
`python -m conversational_analytics.ops.pr_candidate build --pr-number N` y
`... drop --pr-number N`. Reintroduce, de forma acotada y sin tabla de registro, el mecanismo de
"semantic view candidata" que ADR-003 (feature 004-ci-cd-pipeline) elimino solo para
`pr-checks.yml`; ver
`specs/005-pr-checks-semantic-isolation/decisions/001-aislar-semantic-view-candidata-en-pr.md`.

La candidata es un objeto `SEMANTIC VIEW` adicional en el mismo esquema que produccion
(`CICD_DEMO.DATA`), con nombre 100% derivable del numero de PR
(`SV_PHARMA_SALES_PR<numero>`) — no hace falta persistir ningun registro de que candidatas
estan vivas.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from conversational_analytics.ops import sql_runner

REPO_ROOT = Path(__file__).resolve().parents[3]

#: Fichero fuente de la semantic view de produccion; unica fuente de verdad (FR-008, Git). La
#: candidata nunca introduce una segunda copia versionada de esta definicion.
SEMANTIC_VIEW_SQL_PATH = REPO_ROOT / "snowflake" / "004_semantic_view.sql"

#: Nombre corto (sin esquema) del objeto de produccion, tal como aparece literalmente en
#: `SEMANTIC_VIEW_SQL_PATH` (12 apariciones: el `CREATE OR ALTER` y las `AI_VERIFIED_QUERIES`).
PRODUCTION_OBJECT_SHORT_NAME = "SV_PHARMA_SALES"

#: Esquema donde vive tanto la semantic view de produccion como todas las candidatas de PR
#: (D-04, research.md: no se clona ninguna tabla fisica, solo el objeto SEMANTIC VIEW).
CANDIDATE_SCHEMA = "CICD_DEMO.DATA"


def candidate_object_name(pr_number: str) -> str:
    """Nombre completamente cualificado de la candidata de la PR `pr_number`.

    Determinista: `CICD_DEMO.DATA.SV_PHARMA_SALES_PR<pr_number>`. No requiere conexion a
    Snowflake ni estado persistido (D-02, research.md) — puede llamarse desde cualquier paso
    del workflow, o para comprobar que dos PRs distintas nunca colisionan (User Story 2).
    """
    return f"{CANDIDATE_SCHEMA}.{PRODUCTION_OBJECT_SHORT_NAME}_PR{pr_number}"


def render_candidate_ddl(sql_text: str, object_name: str) -> str:
    """Sustituye el token `SV_PHARMA_SALES` por el nombre corto de `object_name` en `sql_text`.

    Funcion pura (sin I/O), testeable sin Snowflake (D-01, research.md). `sql_text` es el
    contenido integro de `snowflake/004_semantic_view.sql`; se sustituyen las 12 apariciones
    del token (la del `CREATE OR ALTER` y las de las `AI_VERIFIED_QUERIES`). `object_name` puede
    venir completamente cualificado (`CICD_DEMO.DATA.SV_PHARMA_SALES_PR42`): solo se usa su
    ultimo segmento como texto de sustitucion, para no duplicar el prefijo de esquema en las
    lineas que ya lo incluyen (`CICD_DEMO.DATA.SV_PHARMA_SALES` -> `CICD_DEMO.DATA.SV_PHARMA_SALES_PR42`,
    no `CICD_DEMO.DATA.CICD_DEMO.DATA.SV_PHARMA_SALES_PR42`).
    """
    short_name = object_name.rsplit(".", 1)[-1]
    return sql_text.replace(PRODUCTION_OBJECT_SHORT_NAME, short_name)


def build_candidate(pr_number: str) -> None:
    """Lee `snowflake/004_semantic_view.sql` del working tree, renderiza la candidata
    (`render_candidate_ddl`) y la ejecuta contra Snowflake (`sql_runner.run_sql_string`).

    No captura ninguna excepcion: si la creacion falla (DDL invalido, cuota, permisos), el
    error se propaga tal cual para que el paso del workflow que lo invoca falle explicitamente
    en vez de continuar validando contra produccion (FR-007).
    """
    sql_text = SEMANTIC_VIEW_SQL_PATH.read_text(encoding="utf-8")
    object_name = candidate_object_name(pr_number)
    candidate_sql = render_candidate_ddl(sql_text, object_name)
    sql_runner.run_sql_string(candidate_sql)


def drop_candidate(pr_number: str) -> None:
    """`DROP SEMANTIC VIEW IF EXISTS <candidate_object_name(pr_number)>`.

    Idempotente: no falla si la candidata ya no existe (limpieza normal ya ejecutada, o nunca
    llego a crearse). Se invoca con `if: always()` desde el workflow, tanto al terminar cada
    ejecucion como cuando la PR se cierra (User Story 3).
    """
    object_name = candidate_object_name(pr_number)
    sql_runner.run_sql_string(f"DROP SEMANTIC VIEW IF EXISTS {object_name};")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    build_parser = subparsers.add_parser(
        "build", help="Construye o actualiza la candidata de una PR"
    )
    build_parser.add_argument("--pr-number", required=True, metavar="N")

    drop_parser = subparsers.add_parser("drop", help="Elimina la candidata de una PR")
    drop_parser.add_argument("--pr-number", required=True, metavar="N")

    args = parser.parse_args(argv)

    if args.command == "build":
        build_candidate(args.pr_number)
        print(f"Candidata construida: {candidate_object_name(args.pr_number)}")
    else:
        drop_candidate(args.pr_number)
        print(f"Candidata eliminada: {candidate_object_name(args.pr_number)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
