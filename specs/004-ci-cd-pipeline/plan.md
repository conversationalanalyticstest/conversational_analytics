# Implementation Plan: Pipeline de CI/CD con protección de rama, despliegue y rollback

**Branch**: `004-ci-cd-pipeline` | **Date**: 2026-09-03 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/004-ci-cd-pipeline/spec.md`

## Summary

Tres workflows de GitHub Actions y un pequeño paquete Python testeable (`ops/`) que los
implementa:

| Workflow | Disparador | Qué hace |
|---|---|---|
| `pr-checks.yml` | PR abierta/actualizada contra `main` | Ejecuta la suite completa de tests contra la semantic view activa en producción, sin desplegar nada. Bloquea el merge si falla (FR-001 a FR-004). |
| `deploy.yml` | Push a `main` (merge) | Re-ejecuta la suite completa; si pasa, despliega (agente + semantic view, ambos actualizados in place); ejecuta la evaluación post-deploy contra lo ya desplegado; si falla, dispara rollback automático (*forward-fix*); en cualquier caso, actualiza la señal de *drift* (FR-005 a FR-011, FR-015, FR-021, FR-022). |
| `revert.yml` | Manual (`workflow_dispatch`, input `target_commit_sha`) | Reactiva la release indicada (agente + semantic view) sin reconstruir pasos a mano; rechaza SHAs sin despliegue exitoso previo (FR-012 a FR-014). |

El punto de diseño no obvio, heredado de [ADR-003](decisions/003-simplificacion-semantic-view.md)
(que revierte la parte de versionado con puntero de
[ADR-001](decisions/001-estrategia-de-revert.md)) y
[ADR-002](decisions/002-rollback-automatico.md): **la semantic view es un único objeto físico**,
actualizado siempre in place con `CREATE OR ALTER SEMANTIC VIEW`, igual que cualquier otro
script SQL idempotente. No hay tabla de versiones ni puntero en Snowflake: el historial de
definiciones es Git. El rollback/revert de la *release* sigue siendo atómico (agente + semantic
view juntos, FR-019); para recuperar una definición anterior de la semantic view, se lee su
contenido en el commit objetivo con `git show` y se re-aplica.

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

**Storage**: Snowflake, esquema `CICD_DEMO.DEVOPS` (ya existe). Tabla nueva:

- `DEPLOYMENTS` — registro insert-only de toda acción de despliegue/rollback/revert (auditoría,
  ADR-002).

No hay tablas de versionado de semantic view (ver [ADR-003](decisions/003-simplificacion-semantic-view.md)):
la semantic view es un único objeto físico, gobernado por Git igual que el resto de scripts de
`snowflake/`.

**Testing**: `pytest` (ya presente), extendiendo la suite existente. Tests nuevos, todos capaces
de correr sin credenciales reales salvo los que ya tocaban Snowflake:

- `tests/test_ops_deploy.py` — aplica un despliegue de prueba contra el esquema real (marcado
  `writes_db`) y verifica que `DEPLOYMENTS` recibe una fila, y que `apply_release_artifacts` lee
  cada script vía `git show <sha>:snowflake/<script>.sql`.
- `tests/test_ops_drift.py` — no toca Snowflake; opera sobre SHAs de ejemplo y verifica la lógica
  de comparación.
- `tests/test_cortex_analyst_resolves_active_view.py` — verifica que `cortex_analyst.py` resuelve
  `DEFAULT_SEMANTIC_VIEW` cuando no hay override por variable de entorno.

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
- Pre-commit local queda **fuera de alcance** de esta feature: la constitución (enmienda
  v3.0.0) ya no lo exige como parte de la cadena de CI/CD; no existe `.pre-commit-config.yaml`
  en el repo y añadirlo, si se quiere en el futuro, es una decisión independiente de esta
  feature.

**Scale/Scope**: 3 workflows, 1 subpaquete Python (~4 módulos), 1 tabla nueva, 3 ficheros de test
nuevos, 1 cambio pequeño en `cortex_analyst.py`.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design. Constitución v2.0.0.*

### Principio I — Simplicidad Orientada a la Demo (NON-NEGOTIABLE)

**PASA, con justificación escrita**:

| Elemento | Justificación |
|---|---|
| 3 workflows en vez de 1 | Cada uno responde a un disparador y una audiencia distintos (PR, merge, acción manual). Fusionarlos en uno con `if` anidados sería más corto pero menos explicable en cinco minutos: cada fichero es "una caja del diagrama". |
| Paquete `ops/` en Python en vez de `bash` en YAML | Es lo mínimo que permite testear la lógica de despliegue/rollback con `pytest` (Principio II exige tests, no solo scripts). El YAML queda reducido a invocar comandos, que es su rol correcto. |
| Semantic view como objeto único, actualizado in place (`CREATE OR ALTER`) | Decisión de [ADR-003](decisions/003-simplificacion-semantic-view.md): el historial ya vive en Git; una tabla de versiones en Snowflake lo duplicaba sin necesidad. |
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

**PASA — es el objeto mismo de esta feature.** Cubre explícitamente los 4 pasos de la cadena que
la constitución exige (enmienda v3.0.0, sin pre-commit local): PR (paso 1),
merge→despliegue (paso 2), post-deploy (paso 3) y rollback automático (paso 4) quedan cubiertos
por `pr-checks.yml` y `deploy.yml`. Todo artefacto desplegable (SQL, semantic view, código del
agente) sigue viviendo en Git; nada se aplica a mano. Cada despliegue queda identificado por
commit SHA (`DEPLOYMENTS.TARGET_COMMIT_SHA`) y el rollback es un mecanismo **probado**, no solo
documentado: usa el mismo camino de código que el despliegue normal (ver
[ADR-002](decisions/002-rollback-automatico.md)).

### Principio IV — Observabilidad y Control de Coste

**PASA**. `DEPLOYMENTS` es consultable con SQL como el resto del
proyecto; el historial de la semantic view es consultable con `git log`. No se introduce coste de tokens nuevo (esta feature no toca prompts ni modelo). El
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
| I Simplicidad | PASA | **PASA** | El diseño final mantiene 3 workflows y 4 módulos en `ops/`; se simplificó tras detectar duplicación con Git (ADR-003). |
| II Evaluación como test | PASA | **PASA** | Los ficheros de test nuevos quedan enumerados en [quickstart.md](./quickstart.md) con su escenario de validación. |
| III CI/CD | PASA | **PASA** | El contrato de workflows ([contracts/workflows.md](contracts/workflows.md)) fija disparadores, permisos y *concurrency* exactos. |
| IV Observabilidad | PASA | **PASA** | El esquema de `DEPLOYMENTS` queda cerrado en [data-model.md](./data-model.md) y [contracts/deployments-table.md](contracts/deployments-table.md). |
| V Reproducibilidad | PASA | **PASA** | Sin cambios; ver lista de secretos requeridos en [quickstart.md](./quickstart.md). |

Sin violaciones nuevas.

## Project Structure

### Documentation (this feature)

```text
specs/004-ci-cd-pipeline/
├── plan.md                              # Este fichero
├── research.md                          # Fase 0 — decisiones D-01..D-12
├── data-model.md                        # Fase 1 — entidad: Deployment
├── quickstart.md                        # Fase 1 — guion de validación end-to-end
├── contracts/
│   ├── workflows.md                     # Contrato de los 3 workflows de GitHub Actions
│   ├── deployments-table.md             # DDL y consultas de DEPLOYMENTS
│   └── semantic-view-versioning.md      # Diseño vigente: objeto único, sin tablas propias
├── checklists/
│   └── requirements.md                  # Fase specify (ya existente)
├── decisions/
│   ├── 001-estrategia-de-revert.md      # ADR-001 (ya existente, parcialmente superseded)
│   ├── 002-rollback-automatico.md       # ADR-002 (ya existente)
│   └── 003-simplificacion-semantic-view.md  # ADR-003 — elimina el versionado con puntero
└── tasks.md                             # Fase 3 — NO lo genera speckit-plan
```

### Source Code (repository root)

```text
.github/
└── workflows/
    ├── pr-checks.yml      # NUEVO — suite completa en PR, sin desplegar nada
    ├── deploy.yml         # NUEVO — tests + despliegue + post-deploy + rollback automático + drift
    └── revert.yml         # NUEVO — workflow_dispatch de revert manual

src/conversational_analytics/
├── db.py                          # existente — sin cambios
├── cortex_analyst.py              # MODIFICAR — env override → DEFAULT_SEMANTIC_VIEW
└── ops/                           # NUEVO subpaquete
    ├── __init__.py
    ├── sql_runner.py               # aplica ficheros/contenido .sql idempotentes vía db.get_connection()
    ├── deployments_log.py          # inserta filas en DEPLOYMENTS
    ├── deploy.py                   # orquesta un despliegue completo (release → Snowflake, vía git show)
    ├── rollback.py                 # localiza última release buena y re-despliega (forward-fix)
    ├── revert.py                   # revert manual a un commit SHA concreto, con validación
    └── drift.py                   # compara "deployed-good" vs HEAD de main, sin credenciales

tests/
├── test_ops_deploy.py                       # NUEVO
├── test_ops_drift.py                        # NUEVO
└── test_cortex_analyst_resolves_active_view.py  # NUEVO

snowflake/
└── 006_deployments.sql              # NUEVO — tabla DEPLOYMENTS
```

**Structure Decision**: Single project. El subpaquete `ops/` vive dentro del paquete ya existente
(`src/conversational_analytics/`) para poder importar `db.py` sin trucos de `PYTHONPATH` y para
que `pytest` lo recoja igual que al resto del código. Los workflows quedan reducidos a invocar
`poetry run python -m conversational_analytics.ops.<algo>`.

## Complexity Tracking

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|---------------------------------------|
| Paquete `ops/` en Python (4 módulos) en vez de scripts `bash` sueltos | Es la única forma de que la lógica de despliegue/rollback tenga tests (Principio II); un script de shell sin tests es exactamente lo que la constitución quiere evitar para "todo cambio en la lógica del agente **o del pipeline**". | `bash` embebido en cada YAML: más rápido de escribir, pero no testeable, duplicado entre workflows, y es la causa típica de que "el rollback nunca se ha probado" (cita literal del Principio III). |

> **Nota**: esta feature llegó a tener, durante su implementación inicial, una fila adicional
> aquí sobre versionado de semantic view con puntero y despliegue de candidatos en PR. Se
> eliminó por [ADR-003](decisions/003-simplificacion-semantic-view.md): ambas piezas duplicaban
> mecanismos que ya existían (Git como historial; la suite de tests corriendo sin aislamiento en
> la feature 003) sin aportar beneficio proporcional a la complejidad añadida.

