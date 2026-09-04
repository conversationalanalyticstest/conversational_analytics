# Contrato: aislamiento de `pr-checks.yml` con semantic view candidata

**Feature**: [005-pr-checks-semantic-isolation](../spec.md) · **Plan**: [../plan.md](../plan.md)

**Extiende**: [../../004-ci-cd-pipeline/contracts/workflows.md](../../004-ci-cd-pipeline/contracts/workflows.md)
sección `pr-checks.yml`. Todo lo que ese contrato fija (disparador base, permisos, secretos,
concurrency) sigue vigente salvo lo que este documento cambia explícitamente.

## Cambios sobre el contrato existente

**Disparador**: se añade `closed` a `types`:
`pull_request: types: [opened, synchronize, reopened, closed]` contra `main`.

**Permisos**: sin cambios (`contents: read`). La candidata se crea/elimina vía credenciales de
Snowflake ya presentes en `env`, no vía permisos de GitHub.

**Concurrency**: sin cambios (`group: pr-checks-${{ github.event.pull_request.number }}`,
`cancel-in-progress: true`).

**Variable de entorno nueva** (bloque `env` del job, junto a las ya existentes):

```yaml
SNOWFLAKE_SEMANTIC_VIEW: CICD_DEMO.DATA.SV_PHARMA_SALES_PR${{ github.event.pull_request.number }}
```

**Pasos (contrato, no implementación)**:

1. `actions/checkout` de la PR (sin cambios).
2. `actions/setup-python` + `poetry install` (sin cambios).
3. NUEVO — `if: github.event.action != 'closed'` — **Build candidate semantic view**:
   `poetry run python -m conversational_analytics.ops.pr_candidate build --pr-number
   ${{ github.event.pull_request.number }}`. Lee `snowflake/004_semantic_view.sql` del working
   tree ya checkouteado y crea/actualiza el objeto candidato (ver
   [data-model.md](../data-model.md)).
4. NUEVO — `if: github.event.action != 'closed'` — **Run test suite**: `poetry run pytest`, sin
   cambios en el comando; el objetivo cambia por la variable de entorno del paso anterior.
5. NUEVO — `if: always()` — **Drop candidate semantic view**:
   `poetry run python -m conversational_analytics.ops.pr_candidate drop --pr-number
   ${{ github.event.pull_request.number }}`. Se ejecuta siempre (tests en verde, en rojo, o
   evento `closed`), garantizando que no quede la candidata de esta ejecución.
6. El resultado del paso 4 sigue determinando el estado del check `pr-checks` (FR-002, FR-003 de
   la feature 004; sin cambios). Cuando el evento es `closed`, el job no evalúa ningún test
   (pasos 3-4 saltados): su único propósito es la limpieza del paso 5.

**Salida observable**: check `pr-checks` en verde/rojo sobre la PR, ahora citando errores de
`SV_PHARMA_SALES_PR<n>` cuando la semantic view de la PR tiene un problema; `SV_PHARMA_SALES` de
producción no cambia en ningún momento; ninguna fila nueva en `DEPLOYMENTS`; ningún objeto
`SV_PHARMA_SALES_PR<n>` sobrevive al cierre de la PR ni al final de una ejecución cuyos pasos de
build/test se completaron.

## Contrato del módulo `ops/pr_candidate.py`

Sigue el mismo patrón que `ops/deploy.py`/`ops/sql_runner.py`: funciones puras testeables +
una CLI fina invocada desde el workflow.

```python
def candidate_object_name(pr_number: str) -> str:
    """Nombre completamente cualificado de la candidata de la PR `pr_number`.

    Determinista: `CICD_DEMO.DATA.SV_PHARMA_SALES_PR<pr_number>`. No requiere conexión a
    Snowflake ni estado persistido — puede llamarse desde cualquier paso del workflow.
    """


def render_candidate_ddl(sql_text: str, object_name: str) -> str:
    """Sustituye el token `SV_PHARMA_SALES` por el nombre corto de `object_name` en `sql_text`.

    Función pura (sin I/O), testeable sin Snowflake. `sql_text` es el contenido íntegro de
    `snowflake/004_semantic_view.sql`; se sustituyen las 12 apariciones del token (la del
    `CREATE OR ALTER` y las de las `AI_VERIFIED_QUERIES`).
    """


def build_candidate(pr_number: str) -> None:
    """Lee `snowflake/004_semantic_view.sql` del working tree, renderiza la candidata
    (`render_candidate_ddl`) y la ejecuta contra Snowflake (`sql_runner.run_sql_string`)."""


def drop_candidate(pr_number: str) -> None:
    """`DROP SEMANTIC VIEW IF EXISTS <candidate_object_name(pr_number)>`, vía
    `sql_runner.run_sql_string`. Idempotente: no falla si la candidata ya no existe."""
```

CLI (`python -m conversational_analytics.ops.pr_candidate`): subcomandos `build --pr-number N` y
`drop --pr-number N`, siguiendo el mismo estilo `argparse` que `ops/deploy.py`.
