---

description: "Task list template for feature implementation"
---

# Tasks: Pipeline de CI/CD con protección de rama, despliegue y rollback

**Input**: Documentos de diseño de `specs/004-ci-cd-pipeline/`

**Prerequisites**: [plan.md](./plan.md), [spec.md](./spec.md), [research.md](./research.md),
[data-model.md](./data-model.md), [contracts/](./contracts/), [quickstart.md](./quickstart.md)

**Tests**: Incluidas y **obligatorias** para todo lo que vive en `ops/` y el cambio en
`cortex_analyst.py` (Principio II de la constitución, que cubre explícitamente "todo cambio en la
lógica del agente **o del pipeline**"). Los workflows YAML en sí no tienen tests unitarios; su
validación es el guion manual de [quickstart.md](./quickstart.md), que se ejecuta como tarea al
final de cada fase de historia y de nuevo, completo, en el Polish final.

**Organization**: Agrupadas por historia de usuario según `spec.md`. US1 y US2 son P1 y juntas
forman el MVP (una PR con tests rotos no mergea; un merge válido despliega con SHA identificable).
US3 y US4 (P2) añaden la capacidad de deshacer una release, automática y manualmente.

> ⚠️ **US5 (P3) fue retirada** por [ADR-003](decisions/003-simplificacion-semantic-view.md): la
> semantic view es un único objeto físico actualizado in place, sin historial propio en
> Snowflake que consultar/reactivar. Las tareas T031-T034 (Phase 7) quedan marcadas como
> superseded más abajo; ver Phase 10 para las tareas de la simplificación.

**Arquitectura (recordatorio de plan.md)**: toda la lógica de despliegue/rollback/revert vive en
`src/conversational_analytics/ops/` (Python, testeable); los tres workflows de
`.github/workflows/` son orquestación fina que invoca `poetry run python -m
conversational_analytics.ops.<modulo>`. ⚠️ La semantic view **ya no se versiona** en Snowflake:
es un único objeto físico, actualizado siempre in place con `CREATE OR ALTER SEMANTIC VIEW`; el
historial y la recuperación de versiones anteriores se apoyan en `git show` (ver Phase 10,
[ADR-003](decisions/003-simplificacion-semantic-view.md)).

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Puede ejecutarse en paralelo (ficheros distintos, sin dependencias pendientes)
- **[Story]**: A qué historia de usuario pertenece (US1-US5)
- Cada tarea incluye la ruta de fichero exacta

## Path Conventions

Proyecto único (ver "Project Structure" en [plan.md](./plan.md)):

- `.github/workflows/` — los 3 workflows nuevos
- `src/conversational_analytics/ops/` — subpaquete nuevo con toda la lógica de despliegue
- `src/conversational_analytics/cortex_analyst.py` — se modifica (resolución de vista activa)
- `snowflake/` — 1 script SQL nuevo (`006_deployments.sql`); `007_semantic_view_registry.sql`
  se creó y luego se eliminó (ver Phase 10, ADR-003)
- `tests/` — 4+ ficheros de test nuevos

---

## Phase 1: Setup

**Purpose**: Dejar listas las condiciones del repositorio y de GitHub que ningún test puede
verificar por sí solo.

- [X] T001 [P] Crear el subpaquete `src/conversational_analytics/ops/__init__.py` (vacío, solo
      para que `ops` sea un paquete importable y que `pytest` lo recoja).
- [ ] T002 [P] **Manual (GitHub, requiere al usuario)** Crear en GitHub el Environment
      `production` con protección de revisión y añadir en él los secretos listados en la
      sección "Prerrequisitos" de [quickstart.md](./quickstart.md) (`SNOWFLAKE_ACCOUNT`,
      `SNOWFLAKE_USER`, `SNOWFLAKE_PAT`, `SNOWFLAKE_ROLE`, `SNOWFLAKE_WAREHOUSE`,
      `SNOWFLAKE_DATABASE`, `LLM_PROVIDER`, `OPENAI_API_KEY`); duplicar los mismos nombres como
      secretos de **repositorio** (sin Environment) para que `pr-checks.yml` pueda leerlos.
      También crear la etiqueta (`label`) `drift` en el repositorio — la necesitan
      `deploy.yml`/`revert.yml` para `gh issue create --label drift` y no está cubierta por
      `quickstart.md`.
- [ ] T003 **Manual (GitHub, requiere al usuario)** Configurar la protección de rama de `main`
      en GitHub: PR obligatoria, check `pr-checks` marcado como *required status check*, mínimo
      1 aprobación, sin push directo (FR-001, FR-004); seguir la sección "Prerrequisitos" de
      [quickstart.md](./quickstart.md).

**Checkpoint**: el repositorio está listo para recibir los workflows; ningún cambio de código
todavía.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Las 3 tablas de Snowflake, los módulos base de `ops/` y el cambio en
`cortex_analyst.py` que **todas** las historias de usuario necesitan (incluso US1, que despliega
una semantic view candidata con este mismo mecanismo).

**⚠️ CRITICAL**: Ninguna historia de usuario puede completarse hasta que esta fase termine.

- [X] T004 [P] Crear `snowflake/006_deployments.sql` con el DDL de `DEPLOYMENTS`
      (`CREATE TABLE IF NOT EXISTS`, ver [contracts/deployments-table.md](contracts/deployments-table.md)).
- [X] T005 [P] ⚠️ SUPERSEDED (ver Phase 10) Crear `snowflake/007_semantic_view_registry.sql` con
      el DDL de `SEMANTIC_VIEW_VERSIONS` y `SEMANTIC_VIEW_ACTIVE`
      (ver [contracts/semantic-view-versioning.md](contracts/semantic-view-versioning.md)).
- [X] T006 ⚠️ SUPERSEDED (ver Phase 10) Ejecutar `006_deployments.sql` y
      `007_semantic_view_registry.sql` contra Snowflake (una vez, igual que
      `001_bootstrap.sql`..`005_telemetry.sql`) y verificar con
      `SHOW TABLES IN SCHEMA CICD_DEMO.DEVOPS;` que las 3 tablas existen (depende de T004, T005).
- [X] T007 [P] Escribir `tests/test_ops_deploy.py` cubriendo `ops.sql_runner.run_sql_file()`
      (aplica un `.sql` de prueba idempotente) y `ops.deployments_log.record()` (inserta una fila
      y se puede releer); marcar con `@pytest.mark.writes_db`. Debe **fallar** antes de T010/T011.
- [X] T008 [P] ⚠️ SUPERSEDED (ver Phase 10) Escribir `tests/test_ops_semantic_view_registry.py`
      cubriendo `deploy_version()` (crea objeto + fila en `SEMANTIC_VIEW_VERSIONS`),
      `activate_version()` (actualiza `SEMANTIC_VIEW_ACTIVE`, recrea el objeto físico desde
      `DDL_TEXT` si ya fue purgado) y `resolve_active()`; marcar `@pytest.mark.writes_db`. Debe
      **fallar** antes de T012.
- [X] T009 [P] Escribir `tests/test_cortex_analyst_resolves_active_view.py` cubriendo la
      precedencia: `SNOWFLAKE_SEMANTIC_VIEW` (env) > `resolve_active()` > `DEFAULT_SEMANTIC_VIEW`.
      Debe **fallar** antes de T013.
- [X] T010 [P] Implementar `run_sql_file(path: Path) -> None` en
      `src/conversational_analytics/ops/sql_runner.py` usando `db.get_connection()` +
      `conn.execute_string()` (hace pasar la parte de T007 correspondiente).
- [X] T011 Implementar `record(*, action, target_commit_sha, previous_commit_sha, status, reason,
      triggered_by, workflow_run_url) -> None` en
      `src/conversational_analytics/ops/deployments_log.py` (hace pasar el resto de T007;
      depende de T006, T010).
- [X] T012 ⚠️ SUPERSEDED (ver Phase 10) Implementar `deploy_version()`, `activate_version()` y
      `resolve_active()` en `src/conversational_analytics/ops/semantic_view_registry.py`, con la
      convención de nombre `<BASE_NAME>_V<sha_corto>` (hace pasar T008; depende de T006).
- [X] T013 Modificar `src/conversational_analytics/cortex_analyst.py` para resolver la semantic
      view con la precedencia env var → `resolve_active()` → constante por defecto (hace pasar
      T009; depende de T012).

**Checkpoint**: infraestructura compartida lista — las historias de usuario pueden empezar.

---

## Phase 3: User Story 1 - Nadie puede saltarse la validación antes de main (Priority: P1) 🎯 MVP (parte 1/2)

**Goal**: Una PR con tests rotos no se puede fusionar a `main`.

**Independent Test**: Abrir una PR con un test roto a propósito, comprobar que el check
`pr-checks` falla y el merge queda bloqueado; corregir el test y comprobar que pasa y el merge se
habilita (ver Escenario 1 de [quickstart.md](./quickstart.md)).

- [X] T014 [US1] ⚠️ SUPERSEDED (ver Phase 10) Implementar el modo `--candidate` de la CLI en
      `src/conversational_analytics/ops/deploy.py`: invoca
      `semantic_view_registry.deploy_version(is_candidate=True, commit_sha=<sha de la PR>)` y
      escribe el `OBJECT_NAME` resultante en `$GITHUB_OUTPUT` (depende de T012). Además se añadió
      `--drop-candidate OBJECT_NAME` (no estaba en el plan original de esta tarea, pero es
      necesario para el paso de limpieza de T015; ver `semantic_view_registry.drop_candidate()`).
- [X] T015 [US1] Crear `.github/workflows/pr-checks.yml` según
      [contracts/workflows.md](contracts/workflows.md): trigger `pull_request` contra `main`,
      `permissions: contents: read`, `concurrency` con `cancel-in-progress: true`; pasos:
      checkout → setup-python + `poetry install` → desplegar candidata (T014) → `poetry run
      pytest` con `SNOWFLAKE_SEMANTIC_VIEW` apuntando al objeto candidato → `if: always()` DROP
      del objeto candidato.
- [ ] T016 [US1] **Manual (requiere PR real en GitHub)** Validar el Escenario 1 de
      [quickstart.md](./quickstart.md): PR con test roto bloquea el merge; PR corregida lo
      habilita. Pendiente de T002/T003.

**Checkpoint**: User Story 1 funcional de forma independiente.

---

## Phase 4: User Story 2 - El merge a main despliega solo si todo sigue en verde (Priority: P1) 🎯 MVP (parte 2/2)

**Goal**: Un merge a `main` re-ejecuta la suite completa y, si pasa, despliega a Snowflake con SHA
identificable; si falla, no despliega nada.

**Independent Test**: Fusionar una PR válida y comprobar que `DEPLOYMENTS`/`SEMANTIC_VIEW_ACTIVE`
quedan con el nuevo commit SHA; forzar un fallo post-merge y comprobar que Snowflake no cambia
(ver Escenario 2 de [quickstart.md](./quickstart.md)).

- [X] T017 [US2] Extender `tests/test_ops_deploy.py` con el modo de release completa: aplica los
      scripts SQL vía `sql_runner`, llama `deploy_version(is_candidate=False)` +
      `activate_version()`, inserta en `DEPLOYMENTS` con `ACTION=DEPLOY`. Debe **fallar** antes de
      T019.
- [X] T018 [US2] Escribir `tests/test_ops_drift.py`: dado un `deployed_sha` y un `head_sha` de
      ejemplo (sin tocar Snowflake ni Git real), verifica la lógica de comparación que determina
      si hay *drift*. Debe **fallar** antes de T020.
- [X] T019 [US2] Implementar el modo de release completa (sin `--candidate`) en
      `src/conversational_analytics/ops/deploy.py`: aplica `snowflake/*.sql` idempotentes vía
      `sql_runner.run_sql_file()`, despliega y activa la versión de semantic view, registra la
      fila en `DEPLOYMENTS` vía `deployments_log.record()`. **Desviación del ADR-002**: el tag
      Git `deployed-good` NO se mueve aquí, sino en un paso `--confirm` separado que solo se
      ejecuta si la evaluación post-deploy pasa (ver T021) — así el tag nunca apunta a una
      release que falló su propia evaluación (hace pasar T017; depende de T010-T013).
- [X] T020 [US2] Implementar `src/conversational_analytics/ops/drift.py` con una función pura de
      comparación de SHAs (`deployed-good` vs HEAD de `main`) que no requiere credenciales de
      Snowflake (hace pasar T018).
- [X] T021 [US2] Crear `.github/workflows/deploy.yml` según
      [contracts/workflows.md](contracts/workflows.md): trigger `push` a `main`,
      `permissions: contents: write, issues: write`, `concurrency: deploy-production` con
      `cancel-in-progress: false`; pasos: checkout → aviso de drift previo (si existe, FR-022) →
      `poetry run pytest` (si falla, parar sin desplegar) → despliegue (T019) → evaluación
      post-deploy (`pytest tests/test_agent_evaluation.py` contra lo ya desplegado) → si pasa,
      confirmar tag `deployed-good` → `if: always()` recalcular drift (T020) y
      crear/actualizar/cerrar Issue `drift`.
- [ ] T022 [US2] **Manual (requiere merge real en GitHub)** Validar el Escenario 2 de
      [quickstart.md](./quickstart.md): el merge despliega y el SHA queda identificable en
      `DEPLOYMENTS`, `SEMANTIC_VIEW_ACTIVE` y el tag `deployed-good`. Pendiente de T002/T003.

**Checkpoint**: User Stories 1 y 2 funcionan de forma independiente — **MVP completo**: una PR
rota no mergea, una PR válida despliega con trazabilidad de SHA.

---

## Phase 5: User Story 3 - Un despliegue que rompe producción se deshace solo (Priority: P2)

**Goal**: Si la evaluación post-deploy falla, Snowflake vuelve automáticamente a la última
release buena, sin intervención manual.

**Independent Test**: Desplegar un cambio que se sabe que falla la evaluación post-deploy y
comprobar que, sin intervención manual, Snowflake vuelve al commit SHA anterior (ver Escenario 3
de [quickstart.md](./quickstart.md)).

- [X] T023 [US3] Escribir `tests/test_ops_rollback.py`: dado un historial de `DEPLOYMENTS` con una
      release buena anterior, verifica que se localiza correctamente y que se re-invoca el
      despliegue de esa release; y que si el propio rollback falla, no reintenta indefinidamente
      (FR-011). Debe **fallar** antes de T024.
- [X] T024 [US3] Implementar `src/conversational_analytics/ops/rollback.py`: lee el tag Git
      `deployed-good` (o, si no coincide, la última fila `SUCCESS` de `DEPLOYMENTS`), re-invoca la
      lógica de `ops/deploy.py` para esa release, y registra la fila con
      `ACTION=AUTO_ROLLBACK` (hace pasar T023; depende de T019).
- [X] T025 [US3] Añadir a `.github/workflows/deploy.yml` el paso/job de rollback automático:
      disparado cuando la evaluación post-deploy (paso de T021) falla, invoca `ops/rollback.py`,
      y si éste también falla, el job termina en rojo sin reintentar y marca el Issue de drift
      como incidente manual (FR-011).
- [ ] T026 [US3] **Manual (requiere disparar un deploy real que falle en GitHub)** Validar el
      Escenario 3 de [quickstart.md](./quickstart.md): un fallo post-deploy dispara el rollback
      automático y se abre el Issue `drift`; cronometrar que el rollback completo tarda menos de
      10 minutos (SC-003) y que el estado de drift se determina en menos de 1 minuto mirando solo
      el Issue (SC-008). Pendiente de T002/T003 y de la etiqueta `drift`.

**Checkpoint**: User Stories 1-3 funcionan de forma independiente.

---

## Phase 6: User Story 4 - Revertir rápido una release ya en producción (Priority: P2)

**Goal**: Cualquier miembro del equipo puede revertir manualmente a una release anterior con una
única acción.

**Independent Test**: Disparar manualmente el revert hacia una release distinta a la actual y
comprobar que Snowflake queda en el estado de esa release; y que un SHA inválido se rechaza sin
tocar Snowflake (ver Escenario 5 de [quickstart.md](./quickstart.md)).

- [X] T027 [US4] Escribir `tests/test_ops_revert.py`: un `target_commit_sha` sin fila
      `STATUS='SUCCESS'` en `DEPLOYMENTS` se rechaza **antes** de tocar Snowflake (FR-014); un
      `target_commit_sha` válido re-despliega esa release y registra la fila con
      `ACTION=MANUAL_REVERT`. Debe **fallar** antes de T028.
- [X] T028 [US4] Implementar `src/conversational_analytics/ops/revert.py`: valida
      `target_commit_sha` contra `DEPLOYMENTS`, re-invoca la lógica de `ops/deploy.py` para esa
      release, registra `TRIGGERED_BY` = actor de GitHub (hace pasar T027; depende de T019).
- [X] T029 [US4] Crear `.github/workflows/revert.yml` según
      [contracts/workflows.md](contracts/workflows.md): `workflow_dispatch` con input
      `target_commit_sha`, mismo `concurrency: deploy-production` que `deploy.yml`, mismo
      Environment `production`; pasos: validar (T028) → checkout → re-desplegar → registrar →
      `if: always()` recalcular drift. **Nota**: el checkout no cambia al commit histórico (el
      workspace se queda en la rama que disparó el `workflow_dispatch`); `ops/revert.py`
      re-aplica esa release reconstruyendo el objeto de semantic view desde `DDL_TEXT` guardado
      en `SEMANTIC_VIEW_VERSIONS`, no desde ficheros del checkout de ese commit antiguo.
- [ ] T030 [US4] **Manual (requiere disparar `workflow_dispatch` real en GitHub)** Validar el
      Escenario 5 de [quickstart.md](./quickstart.md): revert manual válido y rechazo de un SHA
      inventado; cronometrar que el revert completo (una única acción) tarda menos de 5 minutos
      (SC-004). Pendiente de T002/T003.

**Checkpoint**: User Stories 1-4 funcionan de forma independiente.

---

## Phase 7: User Story 5 - Volver atrás en la definición de una tabla semántica sin tocar Git (Priority: P3)

> ⚠️ **Historia completa SUPERSEDED por [ADR-003](decisions/003-simplificacion-semantic-view.md)**
> (ver Phase 10). Se conserva sin editar como registro histórico de lo que se construyó y por
> qué se revirtió.

**Goal**: Consultar y reactivar versiones anteriores de una semantic view sin `git reset` ni
`git revert`, con una política de retención acotada.

**Independent Test**: Desplegar dos versiones sucesivas de una semantic view, consultar el
historial y reactivar la anterior sin ejecutar ningún comando de Git (ver Escenario 6 de
[quickstart.md](./quickstart.md)).

- [X] T031 [US5] ⚠️ SUPERSEDED (ver Phase 10) Extender `tests/test_ops_semantic_view_registry.py`
      con casos para `cleanup_old_versions()`: conserva las `keep_last` versiones de producción
      más recientes, nunca borra la versión activa, y no borra las filas de
      `SEMANTIC_VIEW_VERSIONS` (solo el objeto físico). Debe **fallar** antes de T032.
- [X] T032 [US5] ⚠️ SUPERSEDED (ver Phase 10) Implementar
      `cleanup_old_versions(*, base_name, keep_last=5)` en
      `src/conversational_analytics/ops/semantic_view_registry.py` (hace pasar T031; depende de
      T012).
- [X] T033 [US5] ⚠️ SUPERSEDED (ver Phase 10) Invocar `cleanup_old_versions()` al final del modo
      de release completa de `ops/deploy.py` (depende de T019, T032).
- [ ] T034 [US5] ⚠️ SUPERSEDED (ver Phase 10) **Manual (requiere dos releases reales
      desplegadas)** Validar el Escenario 6 de [quickstart.md](./quickstart.md): consultar
      `SEMANTIC_VIEW_VERSIONS`/`SHOW SEMANTIC VIEWS` sin Git y reactivar una versión anterior.

**Checkpoint**: Las 5 historias de usuario funcionan de forma independiente.

---

## Phase 8: Polish & Cross-Cutting Concerns

**Purpose**: Cierre de la feature completa.

- [X] T035 [P] Añadir al [README.md](../../README.md) una sección breve de CI/CD (los 3
      workflows, enlace a [quickstart.md](./quickstart.md)).
- [X] T036 Revisar los 3 workflows (`.github/workflows/*.yml`) para confirmar que ningún secreto
      se imprime en logs (p. ej. `echo` de variables de entorno, salida de `pytest -v` con datos
      sensibles). Revisión hecha: ningún workflow hace `echo`/`print` de un secreto ni activa
      `set -x`; los únicos valores volcados a `$GITHUB_STEP_SUMMARY`/Issues son SHAs y números de
      Issue, no credenciales.
- [ ] T037 **Manual (requiere entorno GitHub configurado, T002/T003)** Ejecutar de punta a punta
      los 6 escenarios de [quickstart.md](./quickstart.md) en orden, sin saltarse ninguno, como
      validación final de la feature completa.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: sin dependencias, puede empezar de inmediato.
- **Foundational (Phase 2)**: depende de Setup — BLOQUEA las 5 historias de usuario.
- **US1 y US2 (Phases 3-4)**: dependen solo de Foundational; **ambas P1**, forman el MVP juntas.
  US2 reutiliza el mismo fichero `ops/deploy.py` que crea US1 (T014), pero cada una es
  verificable de forma independiente (US1 no necesita que exista el modo release completa).
- **US3 (Phase 5)**: depende de Foundational y de T019 (modo release completa de US2), porque
  "re-desplegar la última release buena" reutiliza esa misma lógica.
- **US4 (Phase 6)**: depende de Foundational y de T019, igual que US3; no depende de US3.
- **US5 (Phase 7)**: depende de Foundational (T012) para T031/T032; T033 depende además de T019
  (US2), porque modifica el mismo `ops/deploy.py`.
- **Polish (Phase 8)**: depende de que todas las historias deseadas estén completas.

### User Story Dependencies

- **US1 (P1)**: solo Foundational.
- **US2 (P1)**: Foundational + reutiliza el `ops/deploy.py` que US1 empieza a crear (T014); son
  el mismo fichero pero cada modo (`--candidate` vs release completa) es independiente en
  comportamiento y en test.
- **US3 (P2)**: Foundational + T019 (US2).
- **US4 (P2)**: Foundational + T019 (US2); no depende de US3.
- **US5 (P3)**: Foundational (T012) para T031/T032; T033 depende además de T019 (US2).

### Within Each User Story

- Tests MUST escribirse y **fallar** antes de la implementación correspondiente (Principio II).
- Los workflows YAML se crean después de que los módulos `ops/` que invocan ya tengan sus tests
  en verde.
- La validación manual de quickstart.md cierra cada fase.

### Parallel Opportunities

- Todas las tareas `[P]` de Setup y Foundational pueden hacerse en paralelo entre sí.
- T007, T008, T009 (tests de Foundational) son paralelos entre sí (ficheros distintos).
- Una vez completada Foundational, **US1 y US5 pueden trabajarse en paralelo** por personas
  distintas para sus tareas iniciales (T014-T016 de US1 no comparten fichero con T031/T032 de
  US5). US2 debe esperar a que T014 (US1) exista si se quiere evitar tocar `ops/deploy.py` a la
  vez desde dos ramas de trabajo distintas. T033 (US5) además debe esperar a T019 (US2), por lo
  que la persona en US5 solo puede cerrar su fase por completo después de que US2 esté lista.
- US3 y US4 pueden trabajarse en paralelo una vez que T019 (US2) está listo.

---

## Parallel Example: Foundational

```bash
# Lanzar los 3 tests de Foundational en paralelo (ficheros distintos, deben fallar primero):
Task: "Escribir tests/test_ops_deploy.py"
Task: "Escribir tests/test_ops_semantic_view_registry.py"
Task: "Escribir tests/test_cortex_analyst_resolves_active_view.py"

# Lanzar los 2 scripts SQL en paralelo:
Task: "Crear snowflake/006_deployments.sql"
Task: "Crear snowflake/007_semantic_view_registry.sql"
```

---

## Implementation Strategy

### MVP First (User Stories 1 + 2)

1. Completar Fase 1: Setup.
2. Completar Fase 2: Foundational (bloqueante).
3. Completar Fase 3: US1 — una PR rota no mergea.
4. Completar Fase 4: US2 — un merge válido despliega con SHA identificable.
5. **PARAR y VALIDAR**: ejecutar Escenarios 1 y 2 de quickstart.md de forma independiente.
6. Esto ya es una demo completa de "CI/CD con protección de rama y despliegue automático".

### Incremental Delivery

1. Setup + Foundational → infraestructura lista.
2. US1 + US2 → MVP (PR bloqueada + despliegue automático con SHA).
3. US3 → rollback automático ante fallo post-deploy.
4. US4 → revert manual a demanda.
5. US5 → conveniencia extra sobre versiones de semantic view (ya cubiertas en su mecanismo base
   desde Foundational).
6. Cada historia añade valor sin romper las anteriores.

### Parallel Team Strategy

Con varias personas:

1. El equipo completa junto Setup + Foundational (es compartido por todas las historias).
2. Una vez lista Foundational:
   - Persona A: US1 (pr-checks.yml)
   - Persona B: US5, solo T031/T032 (retención) — no dependen de US1. T033 debe esperar a que
     Persona A (o quien lo haga) complete T019 de US2.
3. Cuando T019 (release completa) está lista:
   - Persona A continúa con US2 (deploy.yml)
   - Persona B cierra US5 con T033 y luego pasa a US3 o US4 (rollback/revert), en paralelo entre
     sí

---

## Notes

- `[P]` = ficheros distintos, sin dependencias pendientes.
- `[Story]` mapea cada tarea a su historia de usuario para trazabilidad.
- `ops/deploy.py` es el fichero compartido entre **US1, US2 y US5** (tres modos/usos de la misma
  CLI: `--candidate` en US1, release completa en US2, invocación de retención al final de la
  release completa en US5/T033); el resto de ficheros son exclusivos de una historia.
- Verificar que los tests fallan antes de implementar.
- Commitear tras cada tarea o grupo lógico de tareas.
- Parar en cualquier checkpoint para validar una historia de forma independiente.
- Evitar: tareas vagas, conflictos de mismo fichero sin necesidad, dependencias cruzadas entre
  historias que rompan su independencia.

---

## Phase 9: Convergence

**Purpose**: cerrar dos huecos detectados por `speckit-converge` entre lo que documenta el
diseño (`research.md` D-09, `contracts/workflows.md`) y lo que implementan de verdad
`deploy.yml`/`revert.yml`: el Issue de *drift* no incluye el motivo del último despliegue, y no
se distingue como incidente cuando el propio rollback automático falla.

- [X] T038 [P] Extender `tests/test_ops_drift.py` con un caso para la nueva salida `reason` de
      `ops/drift.py`, y añadir en `tests/test_ops_deploy.py` un test (marcado
      `@pytest.mark.writes_db`) para una función nueva en `ops/deployments_log.py` que devuelva
      el `REASON` de la fila más reciente de `DEPLOYMENTS`. Debe **fallar** antes de T039.
- [X] T039 Implementar en `src/conversational_analytics/ops/deployments_log.py` una función
      (p. ej. `latest_row()`) que devuelva `ACTION`/`REASON`/`TARGET_COMMIT_SHA` de la fila más
      reciente de `DEPLOYMENTS`, y extender `src/conversational_analytics/ops/drift.py` para
      exponer ese motivo como salida `reason` en `$GITHUB_OUTPUT` (hace pasar T038; depende de
      T038) per D-09 (research.md) (partial).
- [X] T040 Actualizar el paso de crear/actualizar el Issue de *drift* en
      `.github/workflows/deploy.yml` y `.github/workflows/revert.yml` para incluir en el cuerpo
      el motivo (`reason`) resuelto en T039, tal como especifica D-09 (depende de T039) per D-09
      (partial).
- [X] T041 Marcar explícitamente el Issue de *drift* como incidente (texto adicional en el
      título/cuerpo, p. ej. "🚨 INCIDENTE: revisar manualmente") cuando el paso de rollback
      automático de `.github/workflows/deploy.yml` falla, en vez de reutilizar el mismo mensaje
      genérico de *drift* rutinario, per contracts/workflows.md (paso 8 de `deploy.yml`) / FR-011
      (partial). Implementado añadiendo `id: rollback` al paso de rollback y comprobando
      `steps.rollback.outcome == 'failure'` en el paso del Issue.

---

## Phase 10: Simplificación del versionado de semantic view (ADR-003)

**Purpose**: revertir el mecanismo de versionado con puntero (`SEMANTIC_VIEW_VERSIONS` +
`SEMANTIC_VIEW_ACTIVE`, User Story 5, modo `--candidate`) por duplicar a Git como fuente de
verdad y por un bug real de mislabeling detectado al revisar `apply_release_artifacts` (leía
`004_semantic_view.sql` del working tree actual en vez del commit objetivo en rollback/revert).
Ver [ADR-003](decisions/003-simplificacion-semantic-view.md) para el detalle de la decisión.

- [X] T042 [P] Eliminar `src/conversational_analytics/ops/semantic_view_registry.py`,
      `snowflake/007_semantic_view_registry.sql` y
      `tests/test_ops_semantic_view_registry.py`.
- [X] T043 [P] Añadir `run_sql_string(sql_text: str) -> None` en
      `src/conversational_analytics/ops/sql_runner.py` (ejecuta SQL ya en memoria) y refactorizar
      `run_sql_file()` para que delegue en ella (lee el fichero y llama a `run_sql_string`).
- [X] T044 Reescribir `src/conversational_analytics/ops/deploy.py`: nuevo helper
      `_read_sql_at_commit(commit_sha, script_name) -> str` (usa `git show
      <sha>:snowflake/<script>.sql`, sin tocar el working tree); `RELEASE_SQL_SCRIPTS` pasa a
      incluir `004_semantic_view.sql` como script idempotente más; `apply_release_artifacts()`
      reescrita para leer cada script vía `_read_sql_at_commit` y ejecutarlo con
      `sql_runner.run_sql_string()`; `deploy_release()` pasa a devolver `None`; eliminados el modo
      `--candidate`/`--drop-candidate` de `main()` y las constantes `BASE_NAME`/
      `SEMANTIC_VIEW_DDL_PATH` (depende de T042, T043).
- [X] T045 [P] Simplificar `src/conversational_analytics/cortex_analyst.py`:
      `_resolve_semantic_view()` vuelve a la precedencia de 2 niveles
      (`SNOWFLAKE_SEMANTIC_VIEW` env → `DEFAULT_SEMANTIC_VIEW`), sin `resolve_active()` (depende
      de T042).
- [X] T046 [P] Actualizar `tests/test_ops_deploy.py`: eliminar
      `test_deploy_candidate_does_not_touch_deployments`; ajustar
      `test_deploy_release_records_deploy_row_with_previous_sha` a que `deploy_release()` no
      devuelve nada; añadir `test_apply_release_artifacts_reads_every_script_at_target_commit`
      (mockea `_read_sql_at_commit`/`sql_runner.run_sql_string`, verifica una llamada por script
      de `RELEASE_SQL_SCRIPTS`) (depende de T044).
- [X] T047 [P] Reescribir `tests/test_cortex_analyst_resolves_active_view.py` con 2 tests
      (override de env gana; por defecto sin override) en vez de los 4 anteriores basados en
      `semantic_view_registry` (depende de T045).
- [X] T048 Actualizar `.github/workflows/pr-checks.yml`: eliminar los pasos "Deploy candidate
      semantic view" y "Drop candidate semantic view"; el paso de tests pasa a ejecutar `poetry
      run pytest` directo contra la semantic view activa en producción, sin overrides ni
      despliegue (depende de T044).
- [X] T049 [P] Actualizar comentarios en `.github/workflows/deploy.yml` (paso 5) y
      `.github/workflows/revert.yml` (comentario sobre `apply_release_artifacts`) para reflejar
      la lectura vía `git show` en vez del registro de versiones en Snowflake (depende de T044).
- [X] T050 [P] Actualizar documentación de diseño: `spec.md` (retirar US5/FR-016-018/020/
      SC-006-007), `research.md` (D-04/05/06 → superseded), `data-model.md` (retirar entidades
      `SemanticViewVersion`/`SemanticViewActive`), `contracts/semantic-view-versioning.md`
      (reescritura completa), `contracts/workflows.md` (pr-checks/deploy/revert), `plan.md`
      (Summary, Technical Context, Constitution Check, Project Structure, Complexity Tracking),
      `quickstart.md` (retirar Escenario 6, ajustar Escenario 2 y 5), `README.md` (tabla CI/CD),
      y crear `decisions/003-simplificacion-semantic-view.md` con la nota de "parcialmente
      superseded" añadida a `decisions/001-estrategia-de-revert.md`.
- [ ] T051 **Manual (requiere acceso a Snowflake con ACCOUNTADMIN o rol equivalente)** Limpiar
      objetos obsoletos creados durante el desarrollo de US5 y de los tests `writes_db`: `DROP
      TABLE IF EXISTS CICD_DEMO.DEVOPS.SEMANTIC_VIEW_VERSIONS;`, `DROP TABLE IF EXISTS
      CICD_DEMO.DEVOPS.SEMANTIC_VIEW_ACTIVE;`, y `SHOW SEMANTIC VIEWS IN SCHEMA CICD_DEMO.DATA;`
      para localizar y borrar cualquier objeto residual con sufijo `_V<sha>` o de prueba
      (`SV_OPS_TEST*`, `SV_OPS_CLEANUP_*`).
- [ ] T052 **Manual (requiere entorno GitHub configurado)** Re-ejecutar el guion completo de
      [quickstart.md](./quickstart.md) (ya sin Escenario 6) para confirmar que la demo sigue
      siendo válida de punta a punta tras la simplificación.

**Checkpoint**: mecanismo de versionado con puntero eliminado; despliegue/rollback/revert basados
en `git show`; toda la documentación y los workflows reflejan el diseño vigente.

