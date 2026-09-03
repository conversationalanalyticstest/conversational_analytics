# ADR-002: Estrategia de rollback automático tras un fallo post-deploy

**Fecha**: 2026-09-03
**Feature**: [004-ci-cd-pipeline](../spec.md)
**Estado**: Aceptada
**Afecta a**: FR-009, FR-010, FR-011, FR-019 · User Story 3
**Relacionada con**: [ADR-001](001-estrategia-de-revert.md)

## Contexto

El Principio III de la [constitución](../../../.specify/memory/constitution.md) exige una cadena
de despliegue que termine en: *"Fallo post-deploy → rollback automático a la última versión buena
conocida"*, y añade que **el mecanismo de rollback MUST estar probado, no solo documentado**
("un rollback que nunca se ha ejecutado no es un rollback").

El disparador es la **evaluación post-deploy** (FR-009): tras aplicar los artefactos, el pipeline
vuelve a ejecutar la suite de evaluación del agente contra el Snowflake ya desplegado. Si falla,
significa que el entorno desplegado no se comporta como se espera y hay que volver atrás sin
intervención humana.

### Por qué esto no es el rollback "de libro"

La mayoría del material sobre CI/CD describe el rollback en servicios *stateless*: hay dos
versiones vivas a la vez y revertir es reapuntar el tráfico. Ese modelo no se traslada
directamente a Snowflake:

- No existe una operación nativa que "deshaga" un `CREATE OR REPLACE` sobre la definición de un
  objeto. El Time Travel de Snowflake protege **datos de tablas**, no el DDL histórico de vistas.
- Los dos artefactos de una release tienen coste de reversión muy distinto: el código del agente
  es trivial de revertir; el DDL no lo es (ver [ADR-001](001-estrategia-de-revert.md)).

## Opciones evaluadas

### Opción A — Forward-fix: re-aplicar la última release buena conocida

El pipeline mantiene un puntero a la última release cuya evaluación post-deploy fue exitosa. Ante
un fallo, hace `checkout` de ese commit y **re-ejecuta el mismo job de despliegue** con esos
artefactos. No se "deshace" nada: se despliega hacia adelante una versión anterior conocida.

- ✅ Reutiliza exactamente la misma lógica de despliegue del camino feliz: un solo mecanismo que
  mantener y que probar (y por tanto se ejercita en cada despliegue, no solo en incidentes).
- ✅ Funciona igual para DDL que para código, sin casos especiales.
- ✅ No escribe en el historial de Git ni genera commits automáticos.
- ✅ Es el patrón que la industria aplica cuando hay esquema/estado de por medio.
- ❌ `main` queda temporalmente por delante de lo desplegado: hace falta un *fix forward* con un
  commit nuevo para recuperar la coherencia, o el siguiente merge volvería a desplegar el commit
  problemático.
- ❌ Requiere mantener el puntero de "última buena" de forma fiable.

### Opción B — `git revert` automático + redespliegue

El pipeline hace `git revert` del commit de merge que falló, lo empuja a `main` y eso dispara de
nuevo el pipeline de CD normal.

- ✅ `main` y Snowflake quedan siempre sincronizados; el historial refleja fielmente lo desplegado.
- ❌ Escribe commits automáticos en `main`, una rama protegida (FR-001): exige una excepción en la
  protección de rama, lo que debilita justo la garantía que esta feature quiere demostrar.
- ❌ Revertir un merge con varios commits puede generar conflictos, y un conflicto **bloquea el
  propio rollback** justo cuando más falta hace.
- ❌ Más lento: repite el pipeline completo (tests + deploy + evaluación) en lugar de aplicar
  artefactos ya validados.

### Opción C — Time Travel / clonado de esquema en Snowflake

Antes de desplegar se clona el esquema (`CREATE SCHEMA ... CLONE`, *zero-copy*) y el rollback
consiste en restaurar ese clon.

- ✅ Restauración muy rápida y barata en almacenamiento (zero-copy).
- ✅ Cubre también cambios de datos, no solo de definición.
- ❌ Restaura el esquema **entero**, incluidas escrituras legítimas ocurridas después del
  despliegue: puede destruir datos buenos (p. ej. filas de telemetría de la propia evaluación).
- ❌ El estado desplegado deja de estar determinado por Git y pasa a depender de un snapshot
  opaco, en contra del Principio III ("todo artefacto desplegable MUST vivir en Git").
- ❌ Añade un concepto (clones, swap de esquemas) difícil de explicar en cinco minutos.

### Opción D — Sin rollback automático: alertar y decidir a mano

Ante un fallo post-deploy, el pipeline se detiene y notifica; una persona decide qué hacer.

- ✅ La más simple de todas; cero riesgo de que una automatización empeore un incidente.
- ❌ **Incumple el Principio III**, que exige rollback automático de forma explícita.
- ❌ Elimina precisamente la parte más demostrable del pipeline: es el momento "wow" de la demo.

## Decisión

**Opción A — forward-fix con re-despliegue de la última release buena conocida.**

### Mecánica

1. **Job `deploy`**: aplica los artefactos de la release (código del agente + semantic view
   versionada según [ADR-001](001-estrategia-de-revert.md)).
2. **Job `post-deploy-check`**: ejecuta la evaluación del agente contra el Snowflake ya
   desplegado. Es la única fuente de verdad de "release buena / release mala".
3. Si el paso 2 **pasa**: se actualiza el puntero de última release buena a este commit SHA.
4. Si el paso 2 **falla**: se dispara el job `auto-rollback`, que lee el puntero, hace `checkout`
   de ese commit y ejecuta el mismo job de despliegue del paso 1 con esos artefactos.
5. **Verificación del rollback**: una comprobación posterior confirma que el sistema quedó sano.
   Si el propio rollback falla, el pipeline se detiene, **no reintenta** y notifica como incidente
   que requiere intervención manual (FR-011).
6. En todos los casos, la acción queda registrada (release origen, release destino, motivo,
   timestamp) de forma consultable.

### Puntero de "última release buena"

Se mantiene por duplicado, con propósitos distintos:

- **Tag Git ligero** (p. ej. `deployed-good`), que el pipeline mueve tras cada evaluación
  post-deploy exitosa. Permite responder "¿qué SHA está desplegado?" desde Git, sin abrir logs
  del pipeline (SC-005).
- **Registro en Snowflake**, insert-only, con el histórico de despliegues, rollbacks y reverts.
  Da trazabilidad completa y es consultable con SQL como el resto del proyecto (Principio IV).

El tag es el puntero operativo que usa el rollback; el registro es la auditoría.

### Alcance del rollback

El rollback actúa sobre la **release completa** (agente + semantic view conjuntamente), coherente
con FR-019 y con la decisión de [ADR-001](001-estrategia-de-revert.md). En la práctica, gracias al
versionado con puntero, la parte de semantic view del rollback es un cambio de puntero y no una
re-ejecución de DDL destructivo.

## Consecuencias

**Positivas**

- El rollback usa el mismo código que el despliegue normal, así que se ejercita continuamente:
  cumple la exigencia de la constitución de que el rollback esté *probado*, no solo documentado.
- No hay commits automáticos en `main`, por lo que la protección de rama (FR-001) queda intacta
  y sin excepciones.
- El estado desplegado sigue estando determinado íntegramente por Git.

**Negativas / a gestionar**

- Tras un rollback, `main` contiene un commit que **no** está desplegado. El equipo debe corregir
  con un commit nuevo (*fix forward*); si simplemente se fusiona otra PR, se volvería a desplegar
  el código problemático. Debe quedar explícito en la documentación y en la notificación.
- El rollback re-despliega artefactos, no restaura datos: cambios DML ocurridos tras el despliegue
  fallido no se revierten.
- Si la release fallida introdujo un cambio de esquema incompatible hacia atrás, volver a la
  versión anterior puede fallar. Ese caso escala como incidente manual (FR-011); mitigarlo es
  cuestión de disciplina *expand/contract*, fuera del alcance de esta feature.
- Depende de que el puntero de última release buena sea correcto: si nunca hubo un despliegue
  exitoso previo (primer despliegue del proyecto), no hay destino de rollback y el pipeline debe
  limitarse a notificar.

## Notas

- La evaluación post-deploy no es una repetición redundante de los tests de la PR: éstos validan
  el código, mientras que aquélla valida el **entorno realmente desplegado** (grants aplicados,
  DDL efectivo, comportamiento de Cortex Analyst contra la vista ya creada).
- Opciones descartadas que conviene mencionar en la demo como escalones de madurez: clonado de
  esquema para cubrir también datos (Opción C) y despliegues canary con evaluación progresiva.
