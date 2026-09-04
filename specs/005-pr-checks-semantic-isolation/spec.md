# Feature Specification: Aislar el check de PR contra una copia de la semantic view

**Feature Branch**: `005-pr-checks-semantic-isolation`

**Created**: 2026-09-04

**Status**: Draft

**Input**: User description: "El check de pr-checks.yml es contra la semantic view actual de
producción, no una copia aislada para la PR. Que el check sea contra una copia aislada para la
PR."

> **Nota de relación con ADR-003**: [ADR-003](../004-ci-cd-pipeline/decisions/003-simplificacion-semantic-view.md)
> (feature 004-ci-cd-pipeline, "Aceptada") decidió conscientemente que `pr-checks.yml` validara
> contra la semantic view activa de producción, sin aislamiento, para eliminar el mecanismo de
> versionado con puntero que existía antes. Esta feature **revierte ese punto concreto de
> ADR-003** (su punto 4) porque el equipo considera que validar cambios de semantic view antes
> de fusionar, y no solo después mediante rollback automático, es más seguro — aunque añada una
> pieza de infraestructura. El resto de ADR-003 (semantic view como objeto físico único en
> producción, sin versionado con puntero permanente) **sigue vigente**: esta feature no reintroduce
> `SEMANTIC_VIEW_VERSIONS` ni un puntero persistente, solo un objeto temporal por PR.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Un cambio en la semantic view se valida antes de fusionar, no después (Priority: P1)

Una persona del equipo abre una Pull Request que modifica la definición de la semantic view
(`snowflake/004_semantic_view.sql`). El check de la PR ejecuta la suite de tests contra una
copia de la semantic view construida a partir del contenido de esa PR, no contra la versión
publicada en producción. Si el cambio rompe algo (una métrica, una dimensión, una pregunta
verificada), el check falla y la PR queda bloqueada, sin haber tocado nunca el objeto de
producción.

**Why this priority**: Es la motivación completa de la feature. Con el comportamiento actual
(ADR-003, punto 4), un cambio de semantic view solo se descubre roto *después* de fusionar,
cuando el rollback automático de `deploy.yml` ya tuvo que actuar. Validar antes de fusionar
evita ese ciclo de despliegue-fallo-rollback para el caso más común: alguien cambiando la
propia semantic view.

**Independent Test**: Abrir una PR que introduzca un error deliberado en
`snowflake/004_semantic_view.sql` (p. ej. una métrica con una columna que no existe) y
comprobar que el check de la PR falla citando el error de la copia aislada, mientras que
`SHOW SEMANTIC VIEWS` en producción sigue mostrando la versión anterior sin cambios.

**Acceptance Scenarios**:

1. **Given** una PR que modifica `snowflake/004_semantic_view.sql` con un error de definición,
   **When** se ejecuta el check de la PR, **Then** el check falla y el mensaje de error hace
   referencia a la copia aislada de la PR, no a la semantic view de producción.
2. **Given** una PR que modifica `snowflake/004_semantic_view.sql` de forma correcta,
   **When** se ejecuta el check de la PR, **Then** el check pasa y la semantic view de
   producción no ha cambiado en ningún momento durante la ejecución.
3. **Given** una PR que no toca `snowflake/004_semantic_view.sql` en absoluto, **When** se
   ejecuta el check de la PR, **Then** el comportamiento (aislamiento) es el mismo que en los
   escenarios anteriores — no hay un camino especial para "PRs que no cambian la semantic view".

---

### User Story 2 - Varias PRs abiertas a la vez no interfieren entre sí (Priority: P1)

Dos personas tienen PRs abiertas a la vez, cada una con cambios distintos (o iguales) en la
semantic view. Los checks de ambas PRs corren en paralelo sin que la ejecución de una afecte al
resultado de la otra.

**Why this priority**: Sin esto, el aislamiento "por PR" sería aislamiento solo respecto a
producción, pero seguiría habiendo una carrera entre PRs concurrentes — el mismo problema que
`concurrency.group` ya resuelve para pushes repetidos a la misma PR, pero no entre PRs
distintas. Es indispensable para que la propiedad "aislado" sea real con un equipo de más de
una persona trabajando a la vez.

**Independent Test**: Lanzar (o simular) dos checks de PR distintos al mismo tiempo, cada uno
con una definición de semantic view distinta, y comprobar que cada uno ve y valida su propia
copia, sin que el resultado de uno dependa del orden de ejecución del otro.

**Acceptance Scenarios**:

1. **Given** dos PRs abiertas simultáneamente con definiciones de semantic view distintas,
   **When** ambos checks se ejecutan en paralelo, **Then** cada check usa una copia identificada
   de forma única (p. ej. por número de PR) y ambos terminan con el resultado correcto para su
   propio contenido.
2. **Given** una PR cuyo check está en curso, **When** se sube un nuevo commit a esa misma PR,
   **Then** la ejecución anterior se cancela (comportamiento ya existente, sin cambios) y no dejan
   dos copias simultáneas asociadas al mismo número de PR compitiendo entre sí.

---

### User Story 3 - Las copias temporales no se acumulan (Priority: P2)

Con el tiempo, decenas de PRs se abren, se cierran y se fusionan. Ninguna de las copias
temporales creadas para validar esas PRs queda huérfana en el entorno de Snowflake de forma
indefinida.

**Why this priority**: Es una consecuencia directa de introducir un objeto temporal: sin
limpieza, se acumula estado — exactamente el problema de fondo que ADR-003 identificó y quiso
evitar (viñeta "Acumulación de estado sin beneficio claro"). No es tan urgente como User Story 1
y 2 porque un entorno de demo con pocas PRs no sufre el problema de inmediato, pero sin esto la
feature reintroduce silenciosamente el defecto que motivó ADR-003.

**Independent Test**: Cerrar (fusionada o no) una PR que generó una copia temporal y comprobar
que, en un plazo acotado, esa copia deja de existir en Snowflake sin intervención manual.

**Acceptance Scenarios**:

1. **Given** una PR cuyo check creó una copia temporal de la semantic view, **When** la PR se
   cierra (fusionada o descartada), **Then** la copia asociada a esa PR se elimina.
2. **Given** una copia temporal que quedó huérfana por una ejecución interrumpida o fallida
   (p. ej. el runner se canceló a mitad de la limpieza), **When** pasa un tiempo razonable,
   **Then** existe un mecanismo (automático o manual documentado) que la detecta y la elimina,
   de forma que no se acumule estado indefinidamente.

---

### Edge Cases

- ¿Qué ocurre si dos commits consecutivos de la misma PR llegan a solaparse pese a
  `cancel-in-progress`, dejando dos copias con el mismo identificador de PR a la vez?
- ¿Qué pasa si la creación de la copia temporal falla (p. ej. cuota de objetos, permisos
  insuficientes del rol de CI)? El check MUST fallar de forma explícita, no degradar
  silenciosamente a validar contra producción.
- ¿Qué pasa si el paso de limpieza falla tras un check ya finalizado? No MUST bloquear el
  resultado del check (ya se reportó), pero la copia huérfana resultante MUST quedar cubierta
  por el mecanismo de la User Story 3.
- ¿Qué ocurre con una PR que no modifica `snowflake/004_semantic_view.sql`? Se asume que se
  crea la copia igualmente a partir del contenido vigente en la PR (que puede ser idéntico al
  de producción), para mantener un único camino de ejecución sin casos especiales (ver
  Acceptance Scenario 3 de la User Story 1).

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: El check de la PR MUST construir una copia de la semantic view a partir del
  contenido de `snowflake/004_semantic_view.sql` **tal como está en el commit de la PR**, no del
  objeto vigente en producción.
- **FR-002**: El check de la PR MUST ejecutar la suite de tests (`poetry run pytest`) contra esa
  copia, no contra la semantic view de producción, en ningún paso de su ejecución.
- **FR-003**: La copia temporal MUST estar identificada de forma única por PR (p. ej. incluyendo
  el número de PR en su nombre), de modo que PRs concurrentes no puedan colisionar ni
  sobrescribirse entre sí (User Story 2).
- **FR-004**: El check de la PR MUST seguir sin tener permisos de escritura sobre el objeto de
  producción ni sobre `DEPLOYMENTS` — el aislamiento es un objeto adicional propio de la PR, no
  un cambio de alcance de permisos existente (mantiene el espíritu de `contents: read` /
  "sin despliegue de candidato" de ADR-003, ahora acotado a "sin *modificar* producción").
- **FR-005**: El sistema MUST eliminar la copia temporal asociada a una PR cuando esa PR se
  cierra (fusionada o descartada).
- **FR-006**: El sistema MUST proveer un mecanismo que detecte y elimine copias temporales que
  queden huérfanas (p. ej. por una ejecución cancelada o fallida a mitad de limpieza), sin
  requerir intervención manual recurrente.
- **FR-007**: Si la creación de la copia temporal falla, el check MUST fallar explícitamente
  (rojo, con el motivo del fallo) en vez de continuar validando contra producción.
- **FR-008**: El mecanismo de aislamiento MUST reutilizar `snowflake/004_semantic_view.sql`
  como única fuente de la definición (Principio III de la constitución: Git es la fuente de
  verdad) — no MUST introducir una segunda copia versionada de la definición fuera de Git.
- **FR-009**: El aislamiento MUST convivir con el resto de contratos ya vigentes de
  `pr-checks.yml` (disparador, permisos base, secretos, concurrency de
  [workflows.md](../004-ci-cd-pipeline/contracts/workflows.md)) — esta feature los amplía, no
  los sustituye.

### Key Entities

- **Copia temporal de la semantic view (candidata de PR)**: objeto efímero en Snowflake que
  representa la definición de la semantic view tal como existe en una PR concreta. Vive
  mientras la PR está abierta y su check en curso; se identifica por el número de PR; no tiene
  historial propio (no es una nueva "versión" persistente, solo una instancia desechable).

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Un cambio incorrecto en la semantic view introducido en una PR se detecta en el
  check de esa PR el 100% de las veces, antes de llegar a `main`, sin depender del rollback
  post-deploy para detectarlo.
- **SC-002**: La semantic view de producción no sufre ninguna modificación observable
  (`SHOW SEMANTIC VIEWS`, definición o metadatos) como resultado de ejecutar el check de una PR,
  en el 100% de las ejecuciones.
- **SC-003**: Dos o más PRs con checks en ejecución simultánea obtienen cada una el resultado
  correcto para su propio contenido, sin falsos positivos ni falsos negativos causados por la
  otra PR.
- **SC-004**: El número de copias temporales huérfanas en Snowflake en un momento dado se
  mantiene acotado (no crece de forma indefinida a medida que se abren y cierran PRs).

## Assumptions

- Se acepta añadir infraestructura y complejidad adicional al pipeline de CI/CD para ganar
  validación temprana de cambios en la semantic view; esta feature documenta esa decisión como
  una revisión explícita de ADR-003 (a formalizar como nuevo ADR en la fase de plan), no como un
  descarte silencioso.
- El mecanismo exacto para construir y limpiar la copia temporal (nombre del objeto, momento y
  disparador de la limpieza, gestión de huérfanos) es una decisión de diseño que se resuelve en
  `speckit-plan`, no en esta especificación.
- El resto del comportamiento de `pr-checks.yml` (disparador, permisos base sobre el
  repositorio, secretos, concurrency por número de PR) no cambia; esta feature solo añade el
  aislamiento de la semantic view dentro de ese mismo workflow.
- Esta feature no reintroduce `SEMANTIC_VIEW_VERSIONS` ni un puntero persistente de "versión
  activa": la copia temporal de PR es de vida corta y no sustituye a la semantic view única de
  producción que ADR-003 estableció para releases reales.
