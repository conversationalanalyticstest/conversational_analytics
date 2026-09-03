# ADR-003: Eliminar el versionado con puntero de la semantic view

**Fecha**: 2026-09-15
**Feature**: [004-ci-cd-pipeline](../spec.md)
**Estado**: Aceptada
**Supersede a**: [ADR-001](./001-estrategia-de-revert.md) (solo en la parte de "Opción 2 aplicada
a la semantic view"; el resto de ADR-001 — release atómica, forward-fix — sigue vigente)
**Afecta a**: FR-010, FR-012, FR-016 a FR-020 · User Stories 4 y 5

## Contexto

ADR-001 decidió desplegar la semantic view **versionada con puntero**: cada release crea un
objeto físico nuevo `SV_PHARMA_SALES_V<sha_corto>` en Snowflake y mueve un puntero
(`SEMANTIC_VIEW_ACTIVE`) que indica cuál está activa. El historial de versiones queda en
`SEMANTIC_VIEW_VERSIONS`, insert-only.

Al implementarlo (feature 004, `ops/semantic_view_registry.py`) se hizo evidente un problema de
diseño que ADR-001 no había pesado lo suficiente:

- **El historial ya existe: es Git.** `snowflake/004_semantic_view.sql` está versionado en el
  repositorio desde la feature 002. Cualquier commit antiguo tiene la definición exacta de la
  semantic view en ese momento. Guardar además un `DDL_TEXT` por versión en una tabla de
  Snowflake es **duplicar una fuente de verdad que el Principio III de la constitución ya exige
  que sea Git**, no Snowflake.
- **El mecanismo de revert no llegó a usar Git para nada.** `ops/rollback.py` y `ops/revert.py`
  invocaban `apply_release_artifacts(target_sha)`, que leía `snowflake/004_semantic_view.sql`
  **del working tree actual** (no del commit `target_sha`) y lo re-etiquetaba con el SHA
  objetivo. Es decir: el revert nunca reconstruía de verdad la versión antigua salvo que,
  por casualidad, el fichero no hubiera cambiado entre commits. La única fuente fiable de la
  versión antigua era el propio historial de versiones de Snowflake — la pieza que se había
  añadido precisamente para evitar depender de Git.
- **Acumulación de estado sin beneficio claro.** Cada release deja un objeto físico nuevo en
  Snowflake (`cleanup_old_versions` los purga, pero las filas de `SEMANTIC_VIEW_VERSIONS`
  quedan para siempre) y dos tablas de configuración más que mantener, para un caso de uso —
  "reactivar una definición antigua sin `git reset`" (User Story 5) — que un `git show
  <sha>:snowflake/004_semantic_view.sql` resuelve en una línea.

En resumen: la Opción 2 de ADR-001 añadía una pieza conceptual entera (versionado + puntero)
para replicar, peor, algo que Git ya hace mejor.

## Decisión

**Se elimina la Opción 2 de ADR-001.** La semantic view pasa a ser **un único objeto físico**,
sin sufijo de commit, actualizado siempre in place:

1. `snowflake/004_semantic_view.sql` no cambia: sigue siendo `CREATE OR ALTER SEMANTIC VIEW
   SV_PHARMA_SALES` (nombre fijo, sin templating). Se aplica como un script idempotente más,
   igual que `002_tables.sql` o `005_telemetry.sql`.
2. **No hay `SEMANTIC_VIEW_VERSIONS` ni `SEMANTIC_VIEW_ACTIVE`.** Se elimina
   `snowflake/007_semantic_view_registry.sql` y todo `ops/semantic_view_registry.py`.
3. El rollback automático (FR-010) y el revert manual (FR-012) recuperan una release anterior
   leyendo los ficheros `.sql` **tal como estaban en ese commit** con `git show
   <target_sha>:snowflake/<script>.sql` — sin necesidad de que el working tree esté en ese
   commit (funciona igual en un runner que solo hizo checkout de `HEAD`, siempre que el checkout
   tenga historial completo — `fetch-depth: 0`, ya usado en los 3 workflows) — y ejecutándolos
   contra el único objeto de producción. Esto corrige, de paso, el bug descrito arriba: ahora el
   revert sí aplica el DDL histórico real, no una copia del working tree actual mal etiquetada.
4. **Se elimina el mecanismo de "semantic view candidata" en `pr-checks.yml`** (Opción de
   aislamiento para PRs, D-04 de research.md). Los tests de una PR corren contra la semantic
   view activa de producción, sin desplegar nada nuevo. Es una limitación consciente: una PR que
   cambia `004_semantic_view.sql` no valida ese cambio contra Cortex Analyst hasta que se
   fusiona; el propio `deploy.yml` (evaluación post-deploy + rollback automático) actúa como red
   de seguridad para ese caso. Se acepta este trade-off a cambio de eliminar una pieza entera del
   pipeline, en línea con el Principio I (simplicidad, explicable en 5 minutos).
5. **User Story 5 se retira de la spec.** "Volver atrás en una semantic view sin Git" deja de
   ser un requisito propio: queda cubierta por el revert de release completa (User Story 4), que
   ahora sí usa Git como mecanismo real.

## Consecuencias

**Positivas**

- Una única fuente de verdad para el DDL de la semantic view: Git. Se elimina la duplicación y
  el bug de re-etiquetado descrito en el contexto.
- Menos piezas: no hay tablas de registro que mantener, ni política de retención, ni resolución
  de puntero en `cortex_analyst.py` (vuelve a la precedencia simple de la feature 003: variable
  de entorno → constante por defecto).
- `pr-checks.yml` se simplifica a checkout + tests, sin pasos de despliegue ni limpieza.

**Negativas / aceptadas conscientemente**

- Un cambio de semantic view en una PR no se valida contra Cortex Analyst real hasta el merge.
  Mitigado por la evaluación post-deploy y el rollback automático de `deploy.yml`.
- Se pierde la demo visual de "`SHOW SEMANTIC VIEWS` muestra el historial completo en
  Snowflake": el historial ahora vive en `git log -- snowflake/004_semantic_view.sql`.
- Requiere una limpieza manual, una única vez, de los objetos y tablas creados mientras estuvo
  vigente la Opción 2 (`SEMANTIC_VIEW_VERSIONS`, `SEMANTIC_VIEW_ACTIVE`, objetos
  `SV_PHARMA_SALES_V*` y `SV_OPS_TEST*`/`SV_OPS_CLEANUP_*` de tests) — ver tasks.md, Phase 10.

## Notas relacionadas

- El resto de ADR-001 (release atómica como unidad de revert, forward-fix, `DEPLOYMENTS` como
  histórico insert-only) **sigue vigente**: esta ADR solo revierte la parte de versionado con
  puntero aplicada específicamente a la semantic view.
