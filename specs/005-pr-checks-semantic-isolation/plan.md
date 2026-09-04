# Implementation Plan: Aislar el check de PR contra una copia de la semantic view

**Branch**: `005-pr-checks-semantic-isolation` | **Date**: 2026-09-04 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/005-pr-checks-semantic-isolation/spec.md`

## Summary

`pr-checks.yml` deja de validar contra la semantic view de producción y pasa a construir, en
cada ejecución, un objeto `SEMANTIC VIEW` efímero adicional en el mismo esquema
(`CICD_DEMO.DATA.SV_PHARMA_SALES_PR<número-de-PR>`), derivado del contenido de
`snowflake/004_semantic_view.sql` tal como está en el working tree de la propia PR. La suite de
tests corre contra ese objeto (vía el override `SNOWFLAKE_SEMANTIC_VIEW` que `cortex_analyst.py`
ya soporta), y el objeto se elimina al final de la ejecución y de nuevo cuando la PR se cierra.

El nombre es 100% derivable del número de PR (`github.event.pull_request.number`), así que
**no hace falta ninguna tabla de registro**: es exactamente la pieza que
[ADR-003](../004-ci-cd-pipeline/decisions/003-simplificacion-semantic-view.md) (feature
004-ci-cd-pipeline) eliminó por duplicar a Git como fuente de verdad. Esta feature **revierte
únicamente el punto 4 de ADR-003** ("sin despliegue de candidato en PR") — formalizado como un
ADR propio, [decisions/001-aislar-semantic-view-candidata-en-pr.md](decisions/001-aislar-semantic-view-candidata-en-pr.md) —
y deja el resto de ADR-003 intacto: `SV_PHARMA_SALES` sigue siendo el único objeto físico de
producción, sin versionado con puntero ni tablas `SEMANTIC_VIEW_VERSIONS`/`SEMANTIC_VIEW_ACTIVE`.

De hecho, un mecanismo casi idéntico existió durante la implementación inicial de la feature 004
(`ops/semantic_view_registry.py`, modo `--candidate` en `deploy.py`, tasks T014/T015) y se
eliminó junto con el versionado persistente en la Fase 10 de esa feature. Esta feature recupera
la idea (candidata + limpieza) pero **no** el registro persistente que la acompañaba.

## Technical Context

**Language/Version**: Python (sin cambios, `>=3.11,<3.15`) + YAML de GitHub Actions.

**Primary Dependencies**: ninguna nueva. Se reutiliza `sql_runner.run_sql_string()` (ya existe,
usado por `ops/deploy.py`) para ejecutar el DDL de la candidata; ninguna acción de GitHub
Marketplace nueva.

**Storage**: Snowflake, mismo esquema `CICD_DEMO.DATA` que ya contiene `SV_PHARMA_SALES`. No hay
tablas nuevas ni cambios en `DEPLOYMENTS` — la candidata de PR nunca se registra ahí (no es un
despliegue de producción).

**Testing**: `pytest`, extendiendo la suite existente. Test nuevo:
`tests/test_ops_pr_candidate.py`, cubriendo `candidate_object_name()` y `render_candidate_ddl()`
(puros, sin Snowflake) y un test `@pytest.mark.writes_db` que construye y elimina una candidata
real de prueba.

**Target Platform**: GitHub Actions (`ubuntu-latest`) + la misma cuenta Snowflake de siempre.

**Project Type**: Single project. Módulo nuevo dentro de `src/conversational_analytics/ops/`.

**Performance Goals**: sin objetivo nuevo explícito. La construcción/eliminación de la candidata
es una única sentencia DDL cada una (segundos, no minutos); no cambia el orden de magnitud de la
duración total del check de PR, dominada por la suite de `pytest` igual que hoy.

**Constraints**:

- El rol de CI (`CICD_DEMO_ROLE`) MUST poder crear y eliminar semantic views en
  `CICD_DEMO.DATA` sin permisos nuevos: ya es el propietario de todos los objetos del esquema
  (confirmado en la limpieza manual de la feature 004, tasks.md T051).
- `snowflake/004_semantic_view.sql` en disco MUST NOT cambiar ni incorporar templating: la
  sustitución de nombre (`SV_PHARMA_SALES` → `SV_PHARMA_SALES_PR<n>`) ocurre solo en memoria, en
  el paso que construye la candidata (mantiene vigente el punto 1 de ADR-003 para producción).
- No MUST introducirse ninguna tabla de registro de candidatas vivas (mantiene vigente el
  argumento anti-acumulación de estado de ADR-003).
- La candidata MUST vivir en el mismo esquema que producción (no se clona físicamente ningún
  dato): los tests son de solo lectura sobre `DIM_PRODUCT`/`DIM_COUNTRY`/`FACT_SALES`.

**Scale/Scope**: 1 módulo Python nuevo (~4 funciones + CLI), 1 fichero de test nuevo, 1 workflow
modificado (`pr-checks.yml`: +1 tipo de disparador, +2 pasos, +1 variable de entorno), 1 ADR
nuevo, actualización de 3 documentos de la feature 004 (contratos y ADR-003) en la fase de
implementación.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design. Constitución v3.0.0.*

### Principio I — Simplicidad Orientada a la Demo (NON-NEGOTIABLE)

**PASA, con justificación escrita**:

| Elemento | Justificación |
|---|---|
| Nuevo módulo `ops/pr_candidate.py` (~4 funciones) | Es el mínimo necesario para poder testear con `pytest` la construcción/limpieza de la candidata (Principio II), en vez de `bash` incrustado en el YAML. Sigue el mismo patrón que `ops/deploy.py`/`ops/sql_runner.py` ya establecido en la feature 004. |
| +2 pasos y +1 tipo de disparador en `pr-checks.yml` | Es el contrato mínimo para crear, usar y limpiar un objeto efímero por PR sin tabla de registro. |
| Nombre determinista por número de PR (no por SHA) | Evita necesitar pasar outputs entre pasos o persistir un mapeo PR→objeto: el nombre se deriva directamente del contexto de GitHub Actions (`github.event.pull_request.number`). |
| **Rechazado**: revivir `SEMANTIC_VIEW_VERSIONS`/`SEMANTIC_VIEW_ACTIVE` | Es exactamente la pieza que ADR-003 eliminó por duplicar a Git como fuente de verdad; esta feature deliberadamente no la recupera (ver ADR de esta feature). |
| **Rechazado**: workflow de barrido programado (`schedule`/cron) para huérfanas | Añadiría un cuarto workflow para un caso ya cubierto por el trigger `closed` + `if: always()`; ver D-03 en research.md. |
| **Rechazado**: clon zero-copy del esquema completo por PR | Sobre-ingeniería para tests de solo lectura que no necesitan datos distintos entre PRs; ver D-04 en research.md. |

### Principio II — Evaluación del Agente como Test (NON-NEGOTIABLE)

**PASA**. `pr-checks.yml` sigue ejecutando la suite completa (`poetry run pytest`) sin excepciones
ni subconjuntos; solo cambia el objetivo (`SNOWFLAKE_SEMANTIC_VIEW` → candidata en vez de
producción), mecanismo que `cortex_analyst.py` ya soporta sin cambios de código. Los tests nuevos
de `ops/pr_candidate.py` se escriben antes de su implementación (se fija el orden en `tasks.md`).

### Principio III — CI/CD Es el Producto

**PASA — refuerza la cadena existente.** No cambia el número de pasos obligatorios de la
constitución (PR → merge → post-deploy → rollback); refuerza el primero: un cambio en la
semantic view ahora se valida *antes* de fusionar, no solo mediante el rollback automático de
`deploy.yml` tras el merge. Todo artefacto sigue viviendo en Git (`snowflake/004_semantic_view.sql`
no cambia); nada se aplica a mano.

### Principio IV — Observabilidad y Control de Coste

**PASA**. Los tests de PR ya usan `NullTelemetry` (`tests/conftest.py`): correr contra la
candidata en vez de producción no añade ni quita registros de `AGENT_TELEMETRY`. No hay coste de
tokens nuevo: la suite ya invocaba Cortex Analyst/OpenAI en cada PR antes de esta feature: el
único coste añadido es el de 2 sentencias DDL de Snowflake por ejecución (crear/eliminar una
semantic view), despreciable y sin unidad de coste propia que registrar.

### Principio V — Reproducibilidad y Gestión de Secretos

**PASA**. Ningún secreto nuevo: se reutilizan exactamente los mismos que ya usa `pr-checks.yml`
hoy. `SNOWFLAKE_SEMANTIC_VIEW` no es un secreto (ya es una variable de entorno pública, ver
`.env.example`), y su valor para el candidato se calcula en el propio YAML, no se guarda en
ningún sitio.

### Re-check post-diseño (Fase 1)

Reevaluado tras `research.md`, `data-model.md`, `contracts/` y `quickstart.md`.

| Principio | Antes | Después | Comentario |
|---|---|---|---|
| I Simplicidad | PASA | **PASA** | El diseño final no añade tablas ni workflows nuevos; ver Complexity Tracking. |
| II Evaluación como test | PASA | **PASA** | `tests/test_ops_pr_candidate.py` queda enumerado en [quickstart.md](./quickstart.md). |
| III CI/CD | PASA | **PASA** | Contrato exacto de los pasos nuevos en [contracts/pr-candidate-workflow.md](contracts/pr-candidate-workflow.md). |
| IV Observabilidad | PASA | **PASA** | Sin cambios de telemetría ni coste; ver Technical Context. |
| V Reproducibilidad | PASA | **PASA** | Sin secretos nuevos. |

Sin violaciones nuevas.

## Project Structure

### Documentation (this feature)

```text
specs/005-pr-checks-semantic-isolation/
├── plan.md                                   # Este fichero
├── research.md                               # Fase 0 — decisiones D-01..D-06
├── data-model.md                             # Fase 1 — entidad: candidata de PR (no persistente)
├── quickstart.md                             # Fase 1 — guion de validación end-to-end
├── contracts/
│   └── pr-candidate-workflow.md              # Extiende contracts/workflows.md de 004 (pr-checks.yml)
├── checklists/
│   └── requirements.md                       # Fase specify (ya existente)
├── decisions/
│   └── 001-aislar-semantic-view-candidata-en-pr.md  # ADR — supersede el punto 4 de ADR-003 (004)
└── tasks.md                                  # Fase 3 — NO lo genera speckit-plan
```

### Source Code (repository root)

```text
.github/workflows/
└── pr-checks.yml                  # MODIFICAR — +tipo `closed`, +pasos build/drop candidata

src/conversational_analytics/ops/
├── pr_candidate.py                 # NUEVO — candidate_object_name/render_candidate_ddl/build_candidate/drop_candidate + CLI
└── sql_runner.py                   # sin cambios, reutilizado (run_sql_string)

tests/
└── test_ops_pr_candidate.py        # NUEVO

specs/004-ci-cd-pipeline/contracts/
├── workflows.md                    # MODIFICAR (en implement) — sección pr-checks.yml actualizada
└── semantic-view-versioning.md     # MODIFICAR (en implement) — sección "PR checks" actualizada

specs/004-ci-cd-pipeline/decisions/
└── 003-simplificacion-semantic-view.md  # MODIFICAR (en implement) — nota de superseded parcial en punto 4
```

**Structure Decision**: Single project, sin cambios de estructura. `pr_candidate.py` se añade
junto a los módulos ya existentes de `ops/` (mismo paquete, mismas convenciones: funciones puras
testeables + una CLI fina invocada desde YAML con `poetry run python -m ...`).

## Complexity Tracking

*Sin violaciones de la Constitution Check que requieran justificación adicional a la ya
documentada en la tabla de Principio I.*

