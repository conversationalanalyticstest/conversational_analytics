# ADR-001: Estrategia de revert y versionado de semantic views

**Fecha**: 2026-09-03
**Feature**: [004-ci-cd-pipeline](../spec.md)
**Estado**: ⚠️ Parcialmente superseded por [ADR-003](./003-simplificacion-semantic-view.md)
**Afecta a**: FR-010, FR-012, FR-014, FR-016 · User Stories 3, 4 y 5

> **Nota (2026-09-15)**: la "Opción 2 aplicada a la semantic view" descrita en la sección
> Decisión (versionado con puntero, `SEMANTIC_VIEW_VERSIONS`/`SEMANTIC_VIEW_ACTIVE`) fue
> revertida por [ADR-003](./003-simplificacion-semantic-view.md): resultó estar duplicando una
> fuente de verdad que ya existía en Git. El resto de este documento (Opción 1, release atómica
> como unidad de revert, forward-fix) **sigue vigente**. Se conserva sin reescribir como registro
> histórico de la decisión original.

## Contexto

El pipeline de esta feature despliega a Snowflake dos artefactos con naturaleza muy distinta:

| Artefacto | Naturaleza | Coste de revertir |
|---|---|---|
| Código del agente (prompts, orquestación) | *Stateless* | Trivial: redesplegar la versión anterior. Sin riesgo. |
| Semantic view (`SV_PHARMA_SALES`) | DDL con estado en el servidor | `CREATE OR REPLACE` sobrescribe la definición; volver atrás exige re-aplicar el DDL antiguo. |

Esto genera dos problemas que hay que resolver a la vez:

1. **Velocidad del revert**: revertir una semantic view re-ejecutando DDL funciona, pero no es
   instantáneo ni no-destructivo.
2. **Coherencia entre artefactos**: si una release cambia los dos y se revierte solo uno, el
   sistema puede quedar incoherente. Ejemplo: la release añade una métrica a la semantic view y
   el prompt del agente la menciona; revertir solo la semantic view deja al agente pidiendo una
   métrica que ya no existe.

Restricción adicional: el Principio I de la [constitución](../../../.specify/memory/constitution.md)
exige que cualquier componente sea explicable ante una audiencia en menos de cinco minutos.

### Punto de partida favorable

El nombre de la semantic view **no está hardcodeado** en el código: se lee de la variable
`SNOWFLAKE_SEMANTIC_VIEW` en [cortex_analyst.py](../../../src/conversational_analytics/cortex_analyst.py).
Esa indirección ya existente es la que hace viable la opción de "puntero" descrita más abajo.

## Cómo lo resuelven los equipos profesionales

Cuatro patrones establecidos en la industria, relevantes para este caso:

1. **Artefactos inmutables + release como unidad**. La release se construye una vez, se etiqueta
   y se guarda. Revertir nunca es reconstruir: es volver a desplegar un artefacto que ya existe.
   Es lo que hace que un revert sea rápido y predecible.

2. **Indirección / puntero de versión**. En vez de sobrescribir el objeto en producción, se
   despliegan versiones con nombre y se mueve un puntero (Kubernetes apuntando a otro ReplicaSet,
   blue/green por DNS). Convierte el revert en una operación de segundos y **no destructiva**,
   porque la versión anterior nunca dejó de existir.

3. **Feature flags / kill switch**. El revert más rápido posible: no hay despliegue. Muy potente,
   pero añade estado fuera de Git.

4. **Compatibilidad N-1 (*expand/contract*)**. Disciplina, no herramienta: la versión N del agente
   debe funcionar con la semantic view N-1 y N. Se logra no borrando nada en el mismo despliegue
   en que se añade. Es lo que permite revertir componentes de forma independiente sin miedo, y es
   el estándar de facto en equipos que despliegan varias veces al día con base de datos de por
   medio.

## Opciones evaluadas

### Opción 1 — Release atómica: revertir siempre ambos artefactos juntos

Una release = un commit SHA de `main` = agente + semantic view. El revert manual re-despliega
todo ese SHA.

- ✅ Imposible acabar en un estado incoherente.
- ✅ Trivial de explicar; encaja de lleno con el Principio I.
- ❌ Revertir un fallo menor del prompt obliga a revertir también la semantic view, aunque
  estuviera bien.
- ❌ El revert de la semantic view sigue siendo un `CREATE OR REPLACE` con el DDL antiguo:
  correcto, pero ni instantáneo ni no-destructivo.

### Opción 2 — Semantic views versionadas + puntero (indirección)

Cada despliegue crea `SV_PHARMA_SALES_<SHA_CORTO>` y actualiza un puntero que indica cuál está
activa. El agente resuelve ese puntero en tiempo de ejecución.

- ✅ Revert de la semantic view en segundos y no destructivo: todas las versiones anteriores
  siguen vivas en Snowflake.
- ✅ Resuelve con un único mecanismo el requisito de "volver atrás en una semantic view sin
  `git reset`" (User Story 5) y el de revert rápido de release (User Story 4).
- ✅ Demo visualmente potente: `SHOW SEMANTIC VIEWS` muestra el historial real y el revert se
  ejecuta en directo.
- ❌ Obliga a decidir dónde vive el puntero y a definir una política de limpieza de versiones
  antiguas.
- ❌ Añade una pieza conceptual al pipeline.

### Opción 3 — Revert independiente por componente, con contrato N-1

El workflow de revert manual pregunta qué revertir: agente, semantic view o ambos.

- ✅ Máxima granularidad; es lo que hacen los equipos que despliegan con mucha frecuencia.
- ❌ Exige una disciplina de compatibilidad N-1 que la suite de tests actual no puede verificar
  automáticamente.
- ❌ Abre la puerta a estados incoherentes en manos de alguien que no conozca la regla.
- ❌ Es, con diferencia, la más difícil de explicar en cinco minutos.

## Decisión

**Opción 1 como base, con la Opción 2 aplicada a la semantic view.**

Concretamente:

1. La **unidad de revert por defecto es la release completa**, identificada por el commit SHA de
   `main`. El revert manual (FR-012) y el rollback automático (FR-010) actúan sobre agente y
   semantic view conjuntamente. Esto elimina por construcción el riesgo de incoherencia.
2. La semantic view se despliega **versionada con puntero**: cada despliegue crea un objeto nuevo
   `SV_PHARMA_SALES_<SHA_CORTO>` y actualiza el puntero a la versión activa. Volver atrás es
   mover el puntero, no re-ejecutar DDL destructivo.
3. El **puntero vive en una tabla de configuración en Snowflake**, no en una variable de entorno
   del despliegue. Motivos:
   - Revertir es un único `UPDATE`, sin necesidad de redesplegar el agente → cumple SC-004
     ("una única acción, menos de 5 minutos").
   - Es consultable con SQL como cualquier otra tabla del proyecto, en línea con el Principio IV.
   - `SNOWFLAKE_SEMANTIC_VIEW` se conserva como *override* explícito para desarrollo local y
     tests, de modo que el comportamiento actual no se rompe.
4. La **Opción 3 se descarta para la v1**. Se menciona en la demo como el siguiente escalón de
   madurez, no se implementa.

## Consecuencias

**Positivas**

- Las User Stories 4 y 5 quedan cubiertas por el mismo mecanismo: el versionado de semantic views
  deja de ser una funcionalidad aparte y pasa a ser el propio motor del revert. Menos piezas que
  construir, mantener y explicar.
- El revert de la semantic view es no destructivo: ninguna versión anterior se pierde al
  desplegar una nueva.
- El estado desplegado es auditable con SQL (qué versión está activa, desde cuándo).

**Negativas / a gestionar**

- Se acumulan objetos `SV_PHARMA_SALES_<SHA>` en Snowflake. Requiere una política de retención
  (p. ej. conservar las N últimas), a definir en el plan.
- El agente pasa a depender de una lectura adicional (resolver el puntero) antes de consultar
  Cortex Analyst. Debe tener un comportamiento definido si el puntero no resuelve.
- La granularidad de revert es la release completa: revertir solo el prompt no es posible sin
  revertir también la semantic view. Aceptado conscientemente a cambio de seguridad y
  simplicidad.
- Git y Snowflake pueden desincronizarse temporalmente tras un revert (el revert no reescribe el
  historial de `main`). Recuperar la coherencia exige un *fix forward* con un commit nuevo.

## Notas relacionadas

- Este ADR asume la estrategia **forward-fix** ya acordada para el rollback automático: no se
  "deshace" un despliegue, se vuelve a aplicar una versión anterior conocida como buena. Es el
  patrón habitual cuando hay esquema/estado de por medio, frente al rollback instantáneo típico
  de servicios *stateless*.
- Una semantic view no almacena datos propios: sustituir su definición no afecta a las filas de
  las tablas de negocio subyacentes.
