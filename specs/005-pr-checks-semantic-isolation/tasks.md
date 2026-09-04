---

description: "Task list for feature 005-pr-checks-semantic-isolation"
---

# Tasks: Aislar el check de PR contra una copia de la semantic view

**Input**: Design documents from `/specs/005-pr-checks-semantic-isolation/`

**Prerequisites**: [plan.md](./plan.md), [spec.md](./spec.md), [research.md](./research.md),
[data-model.md](./data-model.md), [contracts/pr-candidate-workflow.md](contracts/pr-candidate-workflow.md),
[quickstart.md](./quickstart.md)

**Tests**: Incluidos y **obligatorios** (Principio II de la constitución, NON-NEGOTIABLE: todo
cambio en la lógica del pipeline lleva sus tests, escritos antes de la implementación
correspondiente).

**Organización**: por historia de usuario de [spec.md](./spec.md), en orden de prioridad
(US1 y US2 son P1/MVP; US3 es P2).

## Path Conventions

Proyecto único (`src/`, `tests/` en la raíz del repo), igual que el resto del proyecto y que la
feature 004-ci-cd-pipeline.

---

## Phase 1: Setup

**Purpose**: no hace falta inicialización nueva — el paquete `ops/`, `pytest`, Poetry y el
esquema de Snowflake ya existen (feature 004). Esta fase queda vacía a propósito.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: las funciones base de `ops/pr_candidate.py` que usan las tres historias de usuario
(construir el nombre determinista, renderizar el DDL, crear y eliminar la candidata en
Snowflake).

**⚠️ CRITICAL**: ninguna historia de usuario puede completarse sin esta fase.

- [ ] T001 [P] Escribir `tests/test_ops_pr_candidate.py` cubriendo `candidate_object_name()`
      (nombre determinista `CICD_DEMO.DATA.SV_PHARMA_SALES_PR<n>` a partir de un número de PR) y
      `render_candidate_ddl()` (sustituye las 12 apariciones del token `SV_PHARMA_SALES` por el
      nombre corto de la candidata, sobre el contenido real de
      `snowflake/004_semantic_view.sql`); ambos sin tocar Snowflake. Debe **fallar** antes de
      T002 (ver [contracts/pr-candidate-workflow.md](contracts/pr-candidate-workflow.md)).
- [ ] T002 Implementar `candidate_object_name(pr_number: str) -> str` y
      `render_candidate_ddl(sql_text: str, object_name: str) -> str` en
      `src/conversational_analytics/ops/pr_candidate.py` (hace pasar T001).
- [ ] T003 [P] Extender `tests/test_ops_pr_candidate.py` con tres tests, todos deben **fallar**
      antes de T004 (depende de T002):
      1. `@pytest.mark.writes_db` — llama a `build_candidate()`, comprueba con
         `SHOW SEMANTIC VIEWS IN SCHEMA CICD_DEMO.DATA` que el objeto candidato existe, llama a
         `drop_candidate()` y comprueba que ya no existe (camino feliz).
      2. `@pytest.mark.writes_db` — antes de construir la candidata, captura
         `DESCRIBE SEMANTIC VIEW CICD_DEMO.DATA.SV_PHARMA_SALES` (producción); ejecuta el ciclo
         completo `build_candidate()` + `drop_candidate()`; vuelve a capturar el mismo
         `DESCRIBE` y **compara que es idéntico**. Automatiza SC-002 (la propiedad de seguridad
         central de la feature: la candidata nunca toca producción), en vez de dejarla solo en
         la validación manual de T008.
      3. Sin marcar `writes_db` — usa `monkeypatch` para que
         `sql_runner.run_sql_string` lance una excepción, y comprueba que `build_candidate()`
         **no la captura ni la convierte en un resultado silencioso** (se propaga tal cual).
         Cubre FR-007 ("si la creación de la copia falla, el check MUST fallar explícitamente")
         sin depender de Snowflake real.
- [ ] T004 Implementar `build_candidate(pr_number: str) -> None` (lee
      `snowflake/004_semantic_view.sql` del working tree, llama a `render_candidate_ddl` y
      ejecuta el resultado con `sql_runner.run_sql_string`) y
      `drop_candidate(pr_number: str) -> None` (`DROP SEMANTIC VIEW IF EXISTS
      <candidate_object_name(pr_number)>`, también vía `sql_runner.run_sql_string`) en
      `src/conversational_analytics/ops/pr_candidate.py` (hace pasar T003; depende de T002).
- [ ] T005 Añadir la CLI (`argparse`, mismo estilo que `ops/deploy.py`) a
      `src/conversational_analytics/ops/pr_candidate.py`: subcomandos `build --pr-number N` y
      `drop --pr-number N`, invocando `build_candidate`/`drop_candidate` (depende de T004).

**Checkpoint**: `ops/pr_candidate.py` completo y testeado — las historias de usuario pueden
empezar.

---

## Phase 3: User Story 1 - Un cambio en la semantic view se valida antes de fusionar, no después (Priority: P1) 🎯 MVP (parte 1/2)

**Goal**: el check de una PR construye la candidata, corre la suite contra ella, y la elimina al
terminar — sin tocar nunca `SV_PHARMA_SALES` de producción.

**Independent Test**: abrir una PR con un error deliberado en `snowflake/004_semantic_view.sql`
y comprobar que el check falla citando la candidata (`SV_PHARMA_SALES_PR<n>`), mientras
`SHOW SEMANTIC VIEWS` muestra `SV_PHARMA_SALES` sin cambios (Escenario 1 de
[quickstart.md](./quickstart.md)).

- [ ] T006 [US1] Modificar `.github/workflows/pr-checks.yml` según
      [contracts/pr-candidate-workflow.md](contracts/pr-candidate-workflow.md): añadir
      `SNOWFLAKE_SEMANTIC_VIEW: CICD_DEMO.DATA.SV_PHARMA_SALES_PR${{ github.event.pull_request.number }}`
      al bloque `env`; añadir el paso "Build candidate semantic view"
      (`poetry run python -m conversational_analytics.ops.pr_candidate build --pr-number
      ${{ github.event.pull_request.number }}`) antes del paso de tests existente (depende de
      T005). Actualizar también el comentario de cabecera del fichero (líneas 2-5, que hoy dice
      "...contra la semantic view activa en producción, sin desplegar nada... ver ADR-003") para
      que referencie en su lugar
      [contracts/pr-candidate-workflow.md](contracts/pr-candidate-workflow.md) y
      [decisions/001-aislar-semantic-view-candidata-en-pr.md](decisions/001-aislar-semantic-view-candidata-en-pr.md)
      — evita que quede describiendo un comportamiento ya superado, igual que se hace en T014-T016
      para la documentación de la feature 004.
- [ ] T007 [US1] En el mismo fichero, añadir el paso "Drop candidate semantic view" al final del
      job, con `if: always()`
      (`poetry run python -m conversational_analytics.ops.pr_candidate drop --pr-number
      ${{ github.event.pull_request.number }}`), de modo que la candidata de cada ejecución se
      elimine tanto si los tests pasan como si fallan (depende de T006).
- [ ] T008 [US1] **Manual (requiere PR real en GitHub)** Validar los Escenarios 1 y 2 de
      [quickstart.md](./quickstart.md): PR con error deliberado en la semantic view bloquea el
      check citando la candidata y no toca producción; PR corregida pasa y, tras terminar, la
      candidata ya no existe. Pendiente de T006, T007.

**Checkpoint**: User Story 1 funcional de forma independiente — el check valida contra una copia
aislada y se limpia solo al terminar cada ejecución.

---

## Phase 4: User Story 2 - Varias PRs abiertas a la vez no interfieren entre sí (Priority: P1) 🎯 MVP (parte 2/2)

**Goal**: PRs concurrentes usan objetos distintos y no colisionan.

**Independent Test**: simular dos checks de PR con distinto número y distinto contenido de
semantic view ejecutándose a la vez, y comprobar que cada uno valida su propio contenido
(Escenario 3 de [quickstart.md](./quickstart.md)).

### Tests for User Story 2

- [ ] T009 [P] [US2] Extender `tests/test_ops_pr_candidate.py` con un test que verifique que
      `candidate_object_name("101") != candidate_object_name("202")` (nombres distintos para
      números de PR distintos) — propiedad de la que depende toda la garantía de no colisión.
      Debe **fallar** solo si la implementación de T002 fuera incorrecta (test de regresión, no
      bloquea nueva implementación).

### Implementation for User Story 2

- [ ] T010 [US2] Ejecutar `poetry run pytest tests/test_ops_pr_candidate.py -v` y confirmar que
      el test de T009 pasa, y dejar constancia (en la descripción de la PR de esta fase) de que
      la propiedad de no colisión de User Story 2 no requiere código nuevo: ya la garantizan
      `candidate_object_name()` (T002, un objeto distinto por número de PR) y el
      `concurrency.group: pr-checks-${{ github.event.pull_request.number }}` ya existente en
      `pr-checks.yml` (sin cambios, feature 004).
- [ ] T011 [US2] **Manual (requiere 2 PRs reales en GitHub)** Validar el Escenario 3 de
      [quickstart.md](./quickstart.md): dos PRs con definiciones de semantic view distintas,
      checks en paralelo, cada uno con el resultado correcto para su propio contenido. Pendiente
      de T006, T007.

**Checkpoint**: User Stories 1 y 2 (MVP completo) funcionan de forma independiente.

---

## Phase 5: User Story 3 - Las copias huérfanas de una ejecución interrumpida no se acumulan (Priority: P2)

**Goal**: una candidata que sobrevive a una ejecución cancelada se elimina, como muy tarde, al
cerrarse la PR — sin tabla de registro ni workflow de barrido.

**Independent Test**: cancelar deliberadamente un check en curso y, tras cerrar la PR, comprobar
que su candidata ya no existe (Escenario 4 de [quickstart.md](./quickstart.md)).

- [ ] T012 [US3] Modificar `.github/workflows/pr-checks.yml`: añadir `closed` a
      `pull_request.types` (`[opened, synchronize, reopened, closed]`) y condicionar los pasos
      "Build candidate semantic view" y "Run test suite" (T006) con
      `if: github.event.action != 'closed'`, de modo que un evento `closed` solo ejecute el paso
      de limpieza (T007, ya incondicional vía `if: always()`) (depende de T006, T007).
- [ ] T013 [US3] **Manual (requiere PR real en GitHub)** Validar el Escenario 4 de
      [quickstart.md](./quickstart.md): push que cancela una ejecución en curso
      (`cancel-in-progress`), cierre de la PR, y comprobación de que
      `SV_PHARMA_SALES_PR<número>` no existe tras el cierre. Pendiente de T012.

**Checkpoint**: las tres historias de usuario funcionan de forma independiente; ninguna
candidata sobrevive indefinidamente a una PR cerrada.

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: dejar la documentación de la feature 004 (que este cambio revierte parcialmente) y
la documentación general del repo coherentes con el nuevo comportamiento.

- [ ] T014 [P] Actualizar
      `specs/004-ci-cd-pipeline/contracts/workflows.md` (sección `pr-checks.yml`): sustituir "sin
      desplegar nada... corre contra la semantic view activa en producción" por una referencia a
      [contracts/pr-candidate-workflow.md](contracts/pr-candidate-workflow.md) de esta feature.
- [ ] T015 [P] Actualizar
      `specs/004-ci-cd-pipeline/contracts/semantic-view-versioning.md` (sección "PR checks: sin
      despliegue de candidato"): reemplazar por una nota que remita a esta feature y a
      [decisions/001-aislar-semantic-view-candidata-en-pr.md](decisions/001-aislar-semantic-view-candidata-en-pr.md).
- [ ] T016 [P] Añadir en
      `specs/004-ci-cd-pipeline/decisions/003-simplificacion-semantic-view.md` una nota en el
      punto 4 (siguiendo el mismo estilo que la nota de "supersede a" que ADR-003 ya añadió sobre
      ADR-001): indica que ese punto queda parcialmente superseded por
      [ADR-001 de esta feature](decisions/001-aislar-semantic-view-candidata-en-pr.md).
- [ ] T017 [P] Actualizar la fila de `pr-checks.yml` en la tabla de CI/CD de `README.md` (línea
      ~99) para reflejar que valida contra una copia candidata, no contra producción.
- [ ] T018 [P] Actualizar `docs/ci-cd-pipeline.md` (§2 nota sobre "el check de pr-checks.yml es
      contra la semantic view actual de producción" y §5.5 "Trade-off aceptado: una PR no valida
      cambios de semantic view hasta el merge"), y el diagrama de la sección 2, para reflejar el
      nuevo comportamiento — este es el documento cuya observación motivó la feature.
- [ ] T019 **Manual (requiere acceso a Snowflake)** Confirmar que `CICD_DEMO_ROLE` puede crear y
      eliminar semantic views en `CICD_DEMO.DATA` sin conceder ningún permiso nuevo (ya es
      propietario del esquema, verificado en la feature 004, tasks.md T051); si hiciera falta un
      `GRANT`, documentarlo aquí y ejecutarlo.
- [ ] T020 Ejecutar el guion completo de [quickstart.md](./quickstart.md) de punta a punta
      (Escenarios 1 a 4 más la verificación de no regresión sobre `DEPLOYMENTS`) para confirmar
      que la demo sigue siendo válida tras esta feature.

**Checkpoint**: documentación de las features 004 y 005, y del repo en general, coherente con el
comportamiento vigente.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: vacía, sin dependencias.
- **Foundational (Phase 2)**: sin dependencias externas — BLOQUEA las tres historias de usuario.
- **User Story 1 (Phase 3)**: depende de Foundational. Sin dependencia de otras historias.
- **User Story 2 (Phase 4)**: depende de Foundational; sus tareas manuales (T011) dependen
  además de que User Story 1 (T006, T007) esté implementada, porque valida el mismo workflow.
- **User Story 3 (Phase 5)**: depende de Foundational y de que User Story 1 (T006, T007) esté
  implementada — añade el trigger `closed` sobre el mismo workflow.
- **Polish (Phase 6)**: depende de que las tres historias de usuario estén completas (documenta
  el comportamiento final).

### Dentro de cada historia

- Tests (T001, T003, T009) se escriben y deben fallar antes que su implementación
  correspondiente (Principio II).
- Foundational (funciones puras → funciones con I/O → CLI) antes que cualquier paso de workflow.
- Los pasos de workflow de US1 (T006, T007) son prerrequisito de las validaciones manuales de
  US2 y de la modificación de US3 sobre el mismo fichero.

### Parallel Opportunities

- T001 y T003 (tests de Foundational) pueden escribirse en paralelo (mismo fichero, pero
  secciones independientes — coordinar si se trabaja en paralelo).
- T014, T015, T016, T017, T018 (Polish, todos documentación en ficheros distintos) son
  totalmente paralelos entre sí.
- User Story 2 y User Story 3 no se pueden paralelizar entre sí de forma completa porque ambas
  tocan `.github/workflows/pr-checks.yml`, pero sus tareas de test/documentación sí.

---

## Parallel Example: Foundational

```bash
Task: "Escribir tests/test_ops_pr_candidate.py cubriendo candidate_object_name() y render_candidate_ddl()"
Task: "Extender tests/test_ops_pr_candidate.py con el ciclo de vida real (writes_db), el snapshot de no-modificación de SV_PHARMA_SALES (writes_db) y el test de propagación de error (monkeypatch, sin Snowflake)"
```

## Parallel Example: Polish

```bash
Task: "Actualizar specs/004-ci-cd-pipeline/contracts/workflows.md"
Task: "Actualizar specs/004-ci-cd-pipeline/contracts/semantic-view-versioning.md"
Task: "Añadir nota de superseded parcial en specs/004-ci-cd-pipeline/decisions/003-simplificacion-semantic-view.md"
Task: "Actualizar la tabla de CI/CD en README.md"
Task: "Actualizar docs/ci-cd-pipeline.md"
```

---

## Implementation Strategy

### MVP First (User Stories 1 y 2)

1. Completar Phase 2: Foundational.
2. Completar Phase 3: User Story 1 — **parar y validar** (Escenarios 1-2 de quickstart.md).
3. Completar Phase 4: User Story 2 — **parar y validar** (Escenario 3). En este punto el MVP
   (P1 + P1) está completo: el check de PR es aislado y seguro para PRs concurrentes.

### Incremental Delivery

1. Foundational → base lista.
2. User Story 1 → validar → ya se puede demostrar el aislamiento básico.
3. User Story 2 → validar → se puede demostrar con dos PRs a la vez.
4. User Story 3 → validar → se puede demostrar que una PR cancelada y cerrada no deja basura.
5. Polish → toda la documentación de 004 y del repo queda coherente con el comportamiento final.

---

## Notes

- Esta feature reintroduce, de forma acotada, un mecanismo que existió y se retiró en la feature
  004 ([ADR-003](../004-ci-cd-pipeline/decisions/003-simplificacion-semantic-view.md)) — pero
  sin la tabla de registro que aquel mecanismo tenía. Ver
  [decisions/001-aislar-semantic-view-candidata-en-pr.md](decisions/001-aislar-semantic-view-candidata-en-pr.md).
- `T006`/`T007`/`T012` tocan el mismo fichero (`pr-checks.yml`) en fases distintas: es
  intencional (cada fase añade justo lo que su historia de usuario necesita), no un error de
  planificación.
- Verificar que los tests fallan antes de implementar (T001→T002, T003→T004).
- Commitear tras cada tarea o grupo lógico de tareas, seguido de `poetry run pytest`.
- Este `tasks.md` incorpora las correcciones de la pasada `speckit-analyze` de la propia
  feature: T003 ahora automatiza SC-002 (no-modificación de producción) y FR-007 (fallo
  explícito en la creación) en vez de dejarlos solo en validación manual; T006 incluye
  actualizar el comentario de cabecera de `pr-checks.yml` para que no quede describiendo el
  comportamiento pre-005; T010 deja de ser una tarea vacía y pasa a una verificación concreta.
