# Contrato: despliegue de la semantic view (sin versionado propio)

**Feature**: [004-ci-cd-pipeline](../spec.md) · **Data model**: [../data-model.md](../data-model.md) ·
**Decisión**: [../decisions/003-simplificacion-semantic-view.md](../decisions/003-simplificacion-semantic-view.md)
(supersede a [../decisions/001-estrategia-de-revert.md](../decisions/001-estrategia-de-revert.md)
en esta parte)

> Este contrato reemplaza al que existía originalmente aquí (dos tablas,
> `SEMANTIC_VIEW_VERSIONS`/`SEMANTIC_VIEW_ACTIVE`, y una convención de nombres con sufijo de
> commit). Se conserva el mismo nombre de fichero porque otros documentos ya enlazan a él.

## Diseño vigente

La semantic view es **un único objeto físico**, sin sufijo de commit:
`CICD_DEMO.DATA.SV_PHARMA_SALES`. Se despliega ejecutando
`snowflake/004_semantic_view.sql` tal cual, exactamente igual que cualquier otro script SQL
idempotente de la release (`002_tables.sql`, `003_seed.sql`, `005_telemetry.sql`,
`006_deployments.sql`): `CREATE OR ALTER SEMANTIC VIEW` hace que la definición converja siempre
a lo que dice el fichero, sin borrar ni recrear el objeto.

**No hay tablas de registro en Snowflake para esto.** El historial de definiciones es Git:
`git log -- snowflake/004_semantic_view.sql`.

## Recuperar una definición anterior (rollback / revert)

`ops/deploy.py` expone `apply_release_artifacts(commit_sha: str) -> None`, usada tanto por un
despliegue normal como por `ops/rollback.py` y `ops/revert.py`. Para cada script de
`RELEASE_SQL_SCRIPTS` (incluido `004_semantic_view.sql`), lee su contenido **tal como estaba en
`commit_sha`** con `git show <commit_sha>:snowflake/<script>.sql` — no del working tree actual —
y lo ejecuta contra Snowflake. Esto funciona sin necesidad de que el checkout esté en ese commit
concreto, siempre que el repositorio tenga historial completo (`fetch-depth: 0`, ya usado en los
3 workflows).

```python
def apply_release_artifacts(commit_sha: str) -> None:
    """Aplica, contra Snowflake, cada script de RELEASE_SQL_SCRIPTS tal como estaba
    definido en `commit_sha` (git show, no el working tree). No registra nada en
    DEPLOYMENTS ni mueve el tag deployed-good: responsabilidad de quien llama."""
```

## Cambio de contrato en `cortex_analyst.py`

`generate_sql()` resuelve la semantic view a consultar con esta precedencia (idéntica a la de la
feature 003, sin la resolución de puntero que existió durante la Opción 2):

1. `SNOWFLAKE_SEMANTIC_VIEW` en el entorno, si está definida (override explícito para desarrollo
   local y tests).
2. Si no: `DEFAULT_SEMANTIC_VIEW` (`CICD_DEMO.DATA.SV_PHARMA_SALES`).

## PR checks: sin despliegue de candidato

`pr-checks.yml` **no despliega nada**. Ejecuta `poetry run pytest` directamente contra la
semantic view activa en producción (sin overrides). Es una limitación consciente: un cambio de
`004_semantic_view.sql` en una PR no se valida contra Cortex Analyst real hasta el merge; la
evaluación post-deploy y el rollback automático de `deploy.yml` son la red de seguridad para ese
caso (ver ADR-003, sección Consecuencias).

