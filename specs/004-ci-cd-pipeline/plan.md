# Implementation Plan: Pipeline de CI/CD con protección de rama, despliegue y rollback

**Branch**: `004-ci-cd-pipeline` | **Date**: 2026-09-03 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/004-ci-cd-pipeline/spec.md`

## Summary

Tres workflows de GitHub Actions y un pequeño paquete Python testeable (`ops/`) que los
implementa:

| Workflow | Disparador | Qué hace |
|---|---|---|
| `pr-checks.yml` | PR abierta/actualizada contra `main` | Despliega una versión **candidata** de la semantic view (sin tocar la activa) y ejecuta la suite completa de tests contra ella. Bloquea el merge si falla (FR-001 a FR-004). |
| `deploy.yml` | Push a `main` (merge) | Re-ejecuta la suite completa; si pasa, despliega (agente + semantic view versionada); ejecuta la evaluación post-deploy contra lo ya desplegado; si falla, dispara rollback automático (*forward-fix*); en cualquier caso, actualiza la señal de *drift* (FR-005 a FR-011, FR-015, FR-021, FR-022). |
| `revert.yml` | Manual (`workflow_dispatch`, input `target_commit_sha`) | Reactiva la release indicada (agente + semantic view) sin reconstruir pasos a mano; rechaza SHAs sin despliegue exitoso previo (FR-012 a FR-014). |

El punto de diseño no obvio, heredado de [ADR-001](decisions/001-estrategia-de-revert.md) y
[ADR-002](decisions/002-rollback-automatico.md): **la semantic view no se sobrescribe, se
versiona**. Cada despliegue crea un objeto `SV_PHARMA_SALES_V<sha_corto>` nuevo y mueve un
**puntero** en una tabla de Snowflake; "revertir la semantic view" es cambiar ese puntero, no
volver a ejecutar DDL. El rollback/revert de la *release* sigue siendo atómico (agente + semantic
view juntos, FR-019); lo que cambia es que la parte de semantic view de esa operación es barata
e instantánea.

Toda la lógica de despliegue/rollback/revert vive en Python (`src/conversational_analytics/ops/`),
no en `bash` incrustado en YAML: así se puede testear con `pytest` (Principio II) y los workflows
quedan como orquestación fina que invoca comandos `poetry run python -m ...`.

## Technical Context

**Language/Version**: Python (sin cambios, `>=3.11,<3.15`) + YAML de GitHub Actions.

**Primary Dependencies**: ninguna dependencia Python nueva. Se reutiliza
`snowflake-connector-python` (ya presente) para aplicar SQL y gestionar versiones/punteros; el
propio `conn.execute_string()` del conector basta para ejecutar los scripts numerados, así que
**no** se introduce el CLI `snow` en CI (evita instalar y configurar una herramienta adicional
solo para el pipeline; ver decisión D-01 en [research.md](./research.md)). Acciones de
GitHub Marketplace usadas: `actions/checkout`, `actions/setup-python` — ambas ya oficiales de
GitHub, fijadas por versión mayor. No se añade ninguna acción de terceros no oficial.

**Storage**: Snowflake, esquema `CICD_DEMO.DEVOPS` (ya existe). Tablas nuevas:

- `DEPLOYMENTS` — registro insert-only de toda acción de despliegue/rollback/revert (auditoría,
  ADR-002).
- `SEMANTIC_VIEW_VERSIONS` — registro insert-only de cada versión desplegada de una semantic
  view, con su DDL completo (ADR-001).
- `SEMANTIC_VIEW_ACTIVE` — tabla de configuración **mutable** (una fila por semantic view base)
  que apunta a la versión activa. Es el único objeto de este diseño que se actualiza en lugar de
  solo insertarse en él, porque es un puntero, no un histórico.

**Testing**: `pytest` (ya presente), extendiendo la suite existente. Tests nuevos, todos capaces
de correr sin credenciales reales salvo los que ya tocaban Snowflake:

- `tests/test_ops_deploy.py` — aplica un despliegue de prueba contra el esquema real (marcado
  `writes_db`) y verifica que `DEPLOYMENTS` y `SEMANTIC_VIEW_VERSIONS` reciben una fila.
- `tests/test_ops_semantic_view_registry.py` — crea dos versiones y comprueba activar/consultar
  sin `git`.
- `tests/test_ops_drift.py` — no toca Snowflake; opera sobre SHAs de ejemplo y verifica la lógica
  de comparación.
- `tests/test_cortex_analyst_resolves_active_view.py` — verifica que `cortex_analyst.py` resuelve
  la vista activa vía la tabla puntero cuando no hay override por variable de entorno.

**Target Platform**: GitHub Actions (`ubuntu-latest`) + la misma cuenta Snowflake de siempre.

**Project Type**: Single project. Se añade un subpaquete `ops/` dentro de
`src/conversational_analytics/` y workflows en `.github/workflows/`.

**Performance Goals**: sin objetivo de latencia nuevo. Restricciones heredadas de la spec:
rollback automático completo en <10 min (SC-003), revert manual en <5 min (SC-004), detección de
drift en <1 min tras consultarlo (SC-008).

**Constraints**:

- Ningún secreto en el repositorio; todo vía GitHub Secrets, en un **Environment** `production`
  con protección (Principio V).
- La suite de tests en PR y en post-merge es la **suite completa** existente, no un subconjunto
  (Principio II literal); se acepta el coste y la duración que eso implica (ver D-03).
- Los despliegues MUST serializarse (FR-015): `concurrency` de GitHub Actions con
  `cancel-in-progress: false` sobre un grupo único de despliegue.
- El revert y el rollback automático MUST NOT usar `git reset`, `git push --force` ni reescribir
  el historial de `main` (FR-016, y restricción general de la spec).
- Pre-commit local (paso 1 del Principio III) queda **fuera de alcance** de esta feature: no
  existe todavía `.pre-commit-config.yaml` en el repo y añadirlo es una decisión independiente,
  no pedida explícitamente. Se documenta como assumption.

**Scale/Scope**: 3 workflows, 1 subpaquete Python (~5 módulos), 2 tablas nuevas + 1 tabla de
configuración, 4 ficheros de test nuevos, 1 cambio pequeño en `cortex_analyst.py`.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design. Constitución v2.0.0.*

### Principio I — Simplicidad Orientada a la Demo (NON-NEGOTIABLE)

**PASA, con justificación escrita**:

| Elemento | Justificación |
|---|---|
| 3 workflows en vez de 1 | Cada uno responde a un disparador y una audiencia distintos (PR, merge, acción manual). Fusionarlos en uno con `if` anidados sería más corto pero menos explicable en cinco minutos: cada fichero es "una caja del diagrama". |
| Paquete `ops/` en Python en vez de `bash` en YAML | Es lo mínimo que permite testear la lógica de despliegue/rollback con `pytest` (Principio II exige tests, no solo scripts). El YAML queda reducido a invocar comandos, que es su rol correcto. |
| Semantic view versionada + puntero, en vez de `CREATE OR ALTER` in-place | Decisión ya justificada y aceptada en [ADR-001](decisions/001-estrategia-de-revert.md): es lo que hace el revert de la semantic view instantáneo y no destructivo, a cambio de una tabla más. |
| Forward-fix en vez de `git revert` automático | Decisión ya justificada y aceptada en [ADR-002](decisions/002-rollback-automatico.md). |
| **Rechazado**: `snow` CLI en CI | Añadiría una herramienta y su configuración de conexión solo para el pipeline, cuando `conn.execute_string()` del conector ya presente hace lo mismo con el código que ya existe en `db.py`. |
| **Rechazado**: pre-commit en esta feature | No estaba en la petición del usuario y el repo no lo tiene hoy; añadirlo aquí ensancharía el alcance sin necesidad. |

### Principio II — Evaluación del Agente como Test (NON-NEGOTIABLE)

**PASA**. Tanto `pr-checks.yml` como el paso de tests de `deploy.yml` ejecutan la suite completa
existente (`test_agent_evaluation.py` y el resto), sin excepciones ni *skips*. La evaluación
post-deploy de `deploy.yml` es la misma suite, apuntando al entorno ya desplegado (FR-009). Toda
la lógica nueva de `ops/` se escribe con sus tests **antes** de la tarea de implementación
correspondiente (se fijará el orden en `tasks.md`).

### Principio III — CI/CD Es el Producto

**PASA — es el objeto mismo de esta feature.** Cubre explícitamente los 5 pasos de la cadena que
la constitución exige: pre-commit local queda fuera de alcance (ver Constraints); PR (paso 2),
merge→despliegue (paso 3), post-deploy (paso 4) y rollback automático (paso 5) quedan cubiertos
por `pr-checks.yml` y `deploy.yml`. Todo artefacto desplegable (SQL, semantic view, código del
agente) sigue viviendo en Git; nada se aplica a mano. Cada despliegue queda identificado por
commit SHA (`DEPLOYMENTS.TARGET_COMMIT_SHA`) y el rollback es un mecanismo **probado**, no solo
documentado: usa el mismo camino de código que el despliegue normal (ver
[ADR-002](decisions/002-rollback-automatico.md)).

### Principio IV — Observabilidad y Control de Coste

**PASA**. `DEPLOYMENTS` y `SEMANTIC_VIEW_VERSIONS` son consultables con SQL como el resto del
proyecto. No se introduce coste de tokens nuevo (esta feature no toca prompts ni modelo). El
coste operativo nuevo es el de ejecutar la suite completa de tests (que ya invoca Cortex Analyst
y, según `LLM_PROVIDER`, la API de OpenAI) en cada PR y en cada merge; se documenta como
consecuencia aceptada en [research.md](./research.md), D-03, no como coste oculto.

### Principio V — Reproducibilidad y Gestión de Secretos

**PASA**. Ningún secreto nuevo distinto de los que ya usa `db.py` y `agent.py`
(`SNOWFLAKE_ACCOUNT`, `SNOWFLAKE_USER`, `SNOWFLAKE_PAT`, `SNOWFLAKE_ROLE`, `SNOWFLAKE_WAREHOUSE`,
`SNOWFLAKE_DATABASE`, `OPENAI_API_KEY`/variables de proveedor). Lo nuevo es **dónde** viven:
GitHub Secrets dentro de un Environment `production` con protección, en vez de solo en `.env`
local. Poner en marcha el pipeline no exige más que rellenar esos mismos secretos una vez en el
repositorio de GitHub.

### Re-check post-diseño (Fase 1)

Reevaluado tras `research.md`, `data-model.md`, `contracts/` y `quickstart.md`.

| Principio | Antes | Después | Comentario |
|---|---|---|---|
| I Simplicidad | PASA | **PASA** | El diseño final mantiene 3 workflows y 5 módulos en `ops/`; ninguno creció por encima de lo descrito aquí. |
| II Evaluación como test | PASA | **PASA** | Los 4 ficheros de test nuevos quedan enumerados en [quickstart.md](./quickstart.md) con su escenario de validación. |
| III CI/CD | PASA | **PASA** | El contrato de workflows ([contracts/workflows.md](contracts/workflows.md)) fija disparadores, permisos y *concurrency* exactos. |
| IV Observabilidad | PASA | **PASA** | Los esquemas de `DEPLOYMENTS` y `SEMANTIC_VIEW_VERSIONS` quedan cerrados en [data-model.md](./data-model.md) y [contracts/deployments-table.md](contracts/deployments-table.md). |
| V Reproducibilidad | PASA | **PASA** | Sin cambios; ver lista de secretos requeridos en [quickstart.md](./quickstart.md). |

Sin violaciones nuevas.

## Project Structure

### Documentation (this feature)

```text
specs/004-ci-cd-pipeline/
├── plan.md                              # Este fichero
├── research.md                          # Fase 0 — decisiones D-01..D-12
├── data-model.md                        # Fase 1 — entidades: Deployment, SemanticViewVersion, SemanticViewActive
├── quickstart.md                        # Fase 1 — guion de validación end-to-end
├── contracts/
│   ├── workflows.md                     # Contrato de los 3 workflows de GitHub Actions
│   ├── deployments-table.md             # DDL y consultas de DEPLOYMENTS
│   └── semantic-view-versioning.md      # DDL de SEMANTIC_VIEW_VERSIONS/ACTIVE + contrato de ops/
├── checklists/
│   └── requirements.md                  # Fase specify (ya existente)
├── decisions/
│   ├── 001-estrategia-de-revert.md      # ADR-001 (ya existente)
│   └── 002-rollback-automatico.md       # ADR-002 (ya existente)
└── tasks.md                             # Fase 3 — NO lo genera speckit-plan
```

### Source Code (repository root)

```text
.github/
└── workflows/
    ├── pr-checks.yml      # NUEVO — despliegue candidato + suite completa en PR
    ├── deploy.yml         # NUEVO — tests + despliegue + post-deploy + rollback automático + drift
    └── revert.yml         # NUEVO — workflow_dispatch de revert manual

src/conversational_analytics/
├── db.py                          # existente — sin cambios
├── cortex_analyst.py              # MODIFICAR — resuelve la semantic view activa vía puntero
└── ops/                           # NUEVO subpaquete
    ├── __init__.py
    ├── sql_runner.py               # aplica ficheros .sql idempotentes vía db.get_connection()
    ├── semantic_view_registry.py   # crea versiones, activa/consulta el puntero, retención
    ├── deployments_log.py          # inserta filas en DEPLOYMENTS
    ├── deploy.py                   # orquesta un despliegue completo (release → Snowflake)
    ├── rollback.py                 # localiza última release buena y re-despliega (forward-fix)
    ├── revert.py                   # revert manual a un commit SHA concreto, con validación
    └── drift.py                   # compara "deployed-good" vs HEAD de main, sin credenciales

tests/
├── test_ops_deploy.py                       # NUEVO
├── test_ops_semantic_view_registry.py       # NUEVO
├── test_ops_drift.py                        # NUEVO
└── test_cortex_analyst_resolves_active_view.py  # NUEVO

snowflake/
├── 006_deployments.sql              # NUEVO — tabla DEPLOYMENTS
└── 007_semantic_view_registry.sql   # NUEVO — SEMANTIC_VIEW_VERSIONS + SEMANTIC_VIEW_ACTIVE
```

**Structure Decision**: Single project. El subpaquete `ops/` vive dentro del paquete ya existente
(`src/conversational_analytics/`) para poder importar `db.py` sin trucos de `PYTHONPATH` y para
que `pytest` lo recoja igual que al resto del código. Los workflows quedan reducidos a invocar
`poetry run python -m conversational_analytics.ops.<algo>`.

## Complexity Tracking

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|---------------------------------------|
| Dos tablas nuevas (`DEPLOYMENTS`, `SEMANTIC_VIEW_VERSIONS`) más una tabla de configuración (`SEMANTIC_VIEW_ACTIVE`) | Auditoría (insert-only) y puntero (mutable) tienen semánticas distintas; mezclarlas en una sola tabla obligaría a "actualizar" filas de un histórico, rompiendo la garantía de insert-only que exige la trazabilidad (ADR-001, ADR-002). | Una única tabla mutable con una columna `IS_ACTIVE`: ya se descartó en el ADR-001 porque complica saber "qué pasó" frente a "qué está activo ahora"; aquí se separan por la misma razón. |
| Despliegue de una semantic view **candidata** en cada PR (no solo tests unitarios) | La constitución exige que la suite de evaluación pase contra Cortex Analyst real; un cambio de semantic view no se puede validar sin desplegar (aunque sea una copia) esa definición. | Testear solo con mocks de Cortex Analyst: no cumpliría el Principio II ("SQL sintácticamente válido y ejecutable" contra la vista real), y ya se descartó implícitamente en la feature 003. |
| Paquete `ops/` en Python (5 módulos) en vez de scripts `bash` sueltos | Es la única forma de que la lógica de despliegue/rollback tenga tests (Principio II); un script de shell sin tests es exactamente lo que la constitución quiere evitar para "todo cambio en la lógica del agente **o del pipeline**". | `bash` embebido en cada YAML: más rápido de escribir, pero no testeable, duplicado entre workflows, y es la causa típica de que "el rollback nunca se ha probado" (cita literal del Principio III). |

