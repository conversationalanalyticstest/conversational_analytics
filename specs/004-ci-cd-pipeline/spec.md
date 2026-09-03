# Feature Specification: Pipeline de CI/CD con protección de rama, despliegue y rollback

**Feature Branch**: `004-ci-cd-pipeline`

**Created**: 2026-09-02

**Status**: Draft

**Input**: User description: "Para el CI/CD, necesito que para pushear a main, sea necesario
hacer una PR. En la PR se ejecutarán los tests, si fallan no podremos mergear a main. Cuando se
haga el merge, se ejecutarán los tests también, si fallan, no se desplegará. Necesito también el
de despliegue. Necesito también que se pueda hacer rollback. Si se hace una release a producción
que se pueda hacer un revert rápido. Versionado de tablas semánticas (por si quieres volver
atrás), una forma rápida que no sea git reset — esto es prioridad secundaria dentro del resto de
la tarea."

> **Nota de revisión (2026-09-15)**: la petición original de "versionado de tablas semánticas"
> se implementó primero como un mecanismo propio en Snowflake (versionado + puntero) y se
> retiró después: duplicaba el historial de Git sin aportar nada que un revert de release
> completa no cubriera ya. Ver [ADR-003](decisions/003-simplificacion-semantic-view.md). Por
> eso ya no aparece la antigua User Story 5 en este documento.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Nadie puede saltarse la validación antes de main (Priority: P1)

Una persona del equipo abre una Pull Request contra `main`. El sistema ejecuta automáticamente
la suite completa de tests. Si algún test falla, la PR queda bloqueada y no se puede fusionar
hasta corregirlo. Si todos pasan, la PR queda lista para revisión y merge.

**Why this priority**: Es la garantía mínima de que `main` nunca recibe código roto. Sin esto,
ningún otro control (despliegue, rollback) tiene sentido, porque el problema ya habría entrado en
`main`.

**Independent Test**: Se puede probar abriendo una PR con un test roto a propósito y comprobando
que el check de CI falla y el botón de merge queda deshabilitado; luego corrigiendo el test y
comprobando que el check pasa y el merge se habilita.

**Acceptance Scenarios**:

1. **Given** una PR abierta contra `main`, **When** se sube un commit, **Then** se dispara
   automáticamente la ejecución de la suite completa de tests y su resultado se muestra en la PR.
2. **Given** una PR cuya suite de tests ha fallado, **When** alguien intenta fusionarla,
   **Then** el sistema lo impide y muestra qué check falló.
3. **Given** una PR cuya suite de tests ha pasado y tiene la aprobación requerida, **When** se
   fusiona, **Then** el merge se completa sin bloqueos adicionales.

---

### User Story 2 - El merge a main despliega solo si todo sigue en verde (Priority: P1)

Al fusionar una PR a `main`, el sistema vuelve a ejecutar la suite completa de tests sobre el
estado resultante de `main`. Si pasan, despliega automáticamente los artefactos versionados
(scripts de Snowflake, semantic views, código del agente) al entorno de Snowflake. Si fallan, no
se despliega nada y el equipo queda notificado.

**Why this priority**: Es la entrega de valor real del pipeline: cambios validados llegan solos a
producción, y cambios que fallan no llegan nunca, aunque hayan pasado el check de la PR (p. ej.
por un problema de entorno o una condición de carrera entre dos merges).

**Independent Test**: Se puede probar fusionando una PR válida y comprobando que Snowflake queda
actualizado con el nuevo commit SHA identificable; y, por separado, forzando un fallo tras el
merge y comprobando que Snowflake no cambia.

**Acceptance Scenarios**:

1. **Given** un merge a `main` cuya suite de tests pasa, **When** el pipeline post-merge termina,
   **Then** los artefactos quedan desplegados en Snowflake e identificados por el commit SHA del
   merge.
2. **Given** un merge a `main` cuya suite de tests falla, **When** el pipeline post-merge termina,
   **Then** Snowflake no recibe ningún cambio y el equipo es notificado del fallo.
3. **Given** un despliegue recién completado, **When** se re-ejecuta la evaluación del agente
   contra el entorno ya desplegado, **Then** el resultado confirma que el comportamiento en vivo
   coincide con lo esperado antes de dar el despliegue por bueno.

---

### User Story 3 - Un despliegue que rompe producción se deshace solo (Priority: P2)

Si la evaluación post-deploy detecta que el despliegue recién aplicado no se comporta como se
espera, el sistema revierte automáticamente Snowflake al último estado conocido como bueno, sin
que nadie tenga que intervenir a mano, y notifica al equipo qué pasó y qué se revirtió.

**Why this priority**: Limita el tiempo que un fallo real permanece visible en producción. Depende
de que exista un despliegue y una evaluación post-deploy (User Story 2), por eso es secundaria a
esa base.

**Nota de diseño**: el mecanismo elegido (re-despliegue de la última release buena, *forward-fix*)
y las alternativas descartadas están documentados en [ADR-002](decisions/002-rollback-automatico.md).

**Independent Test**: Se puede probar desplegando un cambio que se sabe que falla la evaluación
post-deploy y comprobando que, sin intervención manual, Snowflake vuelve a quedar en el estado
(commit SHA) previo al despliegue fallido.

**Acceptance Scenarios**:

1. **Given** un despliegue cuya evaluación post-deploy falla, **When** el pipeline detecta el
   fallo, **Then** revierte automáticamente Snowflake al último despliegue conocido como bueno.
2. **Given** un rollback automático en curso, **When** termina, **Then** el equipo recibe una
   notificación indicando la causa del fallo y a qué versión se ha vuelto.
3. **Given** que el propio rollback automático falla, **When** eso ocurre, **Then** el sistema no
   reintenta indefinidamente y notifica al equipo como incidente que requiere intervención manual.

---

### User Story 4 - Revertir rápido una release ya en producción (Priority: P2)

Después de que una release lleva ya un tiempo en producción, el equipo detecta un problema (no
necesariamente capturado por la evaluación automática) y decide volver a la versión anterior.
Cualquier miembro del equipo puede disparar ese revert con una única acción, sin tener que
reconstruir manualmente los pasos de despliegue.

**Why this priority**: Cubre el caso en que el problema se descubre después de que el post-deploy
ya dio el visto bueno (p. ej. un problema de negocio detectado por un usuario). Es un mecanismo
manual complementario al rollback automático de la User Story 3.

**Independent Test**: Se puede probar disparando manualmente la acción de revert sobre una release
distinta a la actual y comprobando que Snowflake queda en el estado de la release elegida, con una
única acción por parte de quien lo ejecuta.

**Acceptance Scenarios**:

1. **Given** una release identificada por su commit SHA, **When** el equipo dispara la acción de
   revert hacia esa release, **Then** Snowflake queda desplegado en el estado de esa release sin
   pasos manuales adicionales.
2. **Given** que se dispara un revert manual, **When** termina, **Then** queda registrado quién lo
   disparó, hacia qué versión y cuándo.
3. **Given** que se intenta un revert hacia una release que no existe o no tiene artefactos
   desplegables registrados, **When** se dispara, **Then** el sistema lo rechaza con un mensaje
   claro en vez de dejar Snowflake en un estado parcial.

---

### Edge Cases

- ¿Qué pasa si dos Pull Requests se fusionan casi al mismo tiempo? Los despliegues resultantes
  MUST ejecutarse de forma serializada (uno detrás de otro), nunca en paralelo sobre el mismo
  entorno de Snowflake.
- ¿Qué pasa si el rollback automático (User Story 3) también falla? El sistema MUST detenerse,
  notificar como incidente y no dejar reintentos automáticos indefinidos.
- ¿Qué pasa si, tras un rollback, alguien fusiona otra PR sin haber corregido la causa del fallo?
  El sistema MUST advertir de la situación de *drift* antes de desplegar, en vez de volver a
  aplicar en silencio la versión problemática.
- ¿Qué pasa si se pide un revert manual (User Story 4) y todavía no existe ninguna release previa
  desplegada (primer despliegue del proyecto)? El sistema MUST rechazar la acción con un mensaje
  claro.
- ¿Qué pasa si la versión objetivo de un rollback o revert es incompatible con los datos actuales
  (p. ej. una columna que ya no existe)? El sistema MUST fallar de forma visible y notificar en
  vez de dejar Snowflake en un estado parcialmente aplicado.
- ¿Qué pasa si alguien intenta hacer push directo a `main` sin pasar por una PR? El sistema MUST
  impedirlo a nivel de configuración del repositorio.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: El repositorio MUST impedir el push directo a `main`; todo cambio MUST llegar
  mediante una Pull Request.
- **FR-002**: Al abrir o actualizar una Pull Request contra `main`, el sistema MUST ejecutar
  automáticamente la suite completa de tests y mostrar el resultado en la propia PR.
- **FR-003**: Si la suite de tests de una PR falla, el sistema MUST impedir su fusión a `main`
  hasta que el fallo se resuelva.
- **FR-004**: La fusión a `main` MUST requerir, además de los tests en verde, al menos una
  aprobación de otro miembro del equipo (según la constitución vigente).
- **FR-005**: Al fusionar una PR a `main`, el sistema MUST volver a ejecutar la suite completa de
  tests sobre el estado resultante antes de desplegar nada.
- **FR-006**: Si los tests fallan tras el merge, el sistema MUST NOT desplegar los cambios a
  Snowflake, y MUST notificar al equipo del fallo.
- **FR-007**: Si los tests pasan tras el merge, el sistema MUST desplegar automáticamente a
  Snowflake los artefactos versionados en el repositorio: scripts SQL (`snowflake/`), definición
  de semantic views y código del agente conversacional.
- **FR-008**: Cada despliegue MUST quedar identificado de forma inequívoca por el commit SHA que
  lo originó.
- **FR-009**: Tras cada despliegue, el sistema MUST re-ejecutar automáticamente la evaluación del
  agente (según Principio II de la constitución) contra el entorno ya desplegado, antes de
  considerar el despliegue como exitoso.
- **FR-010**: Si la evaluación post-deploy falla, el sistema MUST revertir automáticamente
  Snowflake al último despliegue conocido como bueno, sin intervención manual, y MUST notificar
  al equipo indicando la causa y la versión a la que se ha vuelto.
- **FR-011**: Si el propio rollback automático (FR-010) falla, el sistema MUST NOT reintentar
  indefinidamente y MUST notificar al equipo como incidente que requiere intervención manual.
- **FR-012**: El equipo MUST poder disparar manualmente el revert de una release ya desplegada en
  producción mediante una única acción, indicando la release destino, sin reconstruir a mano los
  pasos de despliegue.
- **FR-013**: Todo revert manual (FR-012) MUST quedar registrado: quién lo disparó, hacia qué
  versión y cuándo.
- **FR-014**: Un revert manual hacia una release sin artefactos desplegables registrados MUST
  rechazarse con un mensaje claro, sin dejar Snowflake en un estado parcial.
- **FR-015**: Los despliegues MUST ejecutarse de forma serializada; dos despliegues concurrentes
  sobre el mismo entorno de Snowflake MUST NOT solaparse.
- **FR-019**: El rollback automático (FR-010) y el revert manual (FR-012) MUST actuar sobre la
  release completa (agente y semantic view conjuntamente), de forma que no puedan dejar ambos
  artefactos en versiones incompatibles entre sí. La recuperación de una definición anterior de
  la semantic view MUST hacerse a partir de su definición en Git en el commit objetivo (ver
  [ADR-003](decisions/003-simplificacion-semantic-view.md)), no de un historial propio en
  Snowflake.
- **FR-021**: Tras un rollback automático o un revert manual, el sistema MUST señalar de forma
  visible y proactiva que `main` contiene commits no desplegados (*drift*), sin que nadie tenga
  que consultar los logs del pipeline para descubrirlo.
- **FR-022**: Si se dispara un despliegue mientras existe una situación de *drift* sin resolver,
  el sistema MUST advertirlo explícitamente antes de aplicar los cambios, para evitar
  redesplegar en silencio la versión que causó el fallo.

### Key Entities *(include if feature involves data)*

- **Pipeline de PR (CI)**: ejecución automática de la suite de tests disparada por la apertura o
  actualización de una Pull Request contra `main`; determina si la PR puede fusionarse.
- **Pipeline de despliegue (CD)**: ejecución automática disparada por un merge a `main`; incluye
  re-ejecución de tests, despliegue a Snowflake y evaluación post-deploy.
- **Release**: conjunto de artefactos desplegados a Snowflake en un momento dado, identificado de
  forma única por el commit SHA de `main` que lo originó.
- **Última release buena**: puntero a la release más reciente cuya evaluación post-deploy fue
  exitosa; es el destino del rollback automático (ver [ADR-002](decisions/002-rollback-automatico.md)).
- **Registro de despliegues/reverts**: histórico consultable de qué release está o ha estado
  activa en Snowflake, incluyendo reverts manuales (quién, cuándo, hacia qué versión).

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: El 100% de los cambios que llegan a `main` lo hacen a través de una Pull Request con
  la suite de tests en verde; no existe ninguna vía de push directo.
- **SC-002**: El 100% de los merges a `main` terminan en uno de dos estados observables sin
  ambigüedad: "desplegado con SHA identificado" o "bloqueado, sin cambios en Snowflake".
- **SC-003**: Un despliegue cuya evaluación post-deploy falla queda revertido automáticamente a la
  última versión buena en menos de 10 minutos desde que se detecta el fallo, sin intervención
  manual.
- **SC-004**: Revertir manualmente una release en producción requiere una única acción por parte
  del equipo (no una secuencia de pasos manuales) y se completa en menos de 5 minutos.
- **SC-005**: Cualquier miembro del equipo puede identificar qué commit SHA está desplegado
  actualmente en Snowflake sin necesidad de revisar logs de ejecución del pipeline.
- **SC-008**: Tras un rollback o revert, cualquier miembro del equipo puede determinar en menos de
  un minuto qué commits están en `main` pero no desplegados.

## Assumptions

- El equipo dispone de al menos un canal de notificación accesible para el pipeline (p. ej. un
  canal de Slack/Teams o el propio sistema de notificaciones de GitHub Actions); no se especifica
  el canal exacto, se documentará como configuración en el plan.
- "Último despliegue conocido como bueno" se determina exclusivamente por el resultado de la
  evaluación post-deploy (Principio II de la constitución), no por criterio manual.
- El rollback automático y el revert manual actúan sobre artefactos desplegables (scripts SQL,
  semantic views, código del agente); no cubren la reversión de datos de negocio ya modificados
  por operaciones DML posteriores al despliegue.
- Si no existe ninguna release previa con evaluación post-deploy exitosa (primer despliegue del
  proyecto), no hay destino de rollback: el pipeline se limita a notificar el fallo.
- Un cambio de esquema incompatible entre releases (p. ej. columna eliminada) puede hacer que un
  rollback o revert falle de forma visible; resolverlo en ese caso requiere intervención manual,
  fuera del alcance de esta feature.
- La recuperación de una definición anterior de la semantic view se apoya en el historial de Git
  (el commit SHA objetivo del revert/rollback), no en un mecanismo de versionado propio en
  Snowflake (ver [ADR-003](decisions/003-simplificacion-semantic-view.md)).
- La granularidad de revert es la release completa: no es posible revertir solo el código del
  agente sin revertir también la semantic view. Es una decisión consciente ([ADR-001](decisions/001-estrategia-de-revert.md))
  a favor de la seguridad y la simplicidad, frente al revert independiente por componente.
- El revert no reescribe el historial de Git: tras un rollback, `main` puede quedar por delante
  de lo desplegado en Snowflake, y recuperar la coherencia exige un *fix forward* con un commit
  nuevo.
- La feature reutiliza la suite de tests ya existente (`pytest`) como criterio de "verde/rojo"
  tanto en PR como en post-merge y post-deploy; no se definen nuevos criterios de calidad aquí.
