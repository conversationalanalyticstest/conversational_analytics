# Fase 0 — Research: Pipeline de CI/CD

**Feature**: [004-ci-cd-pipeline](./spec.md) · **Plan**: [plan.md](./plan.md)

Formato por decisión: **Decision** / **Rationale** / **Alternatives considered**.

---

## D-01: Cómo se aplican los scripts SQL desde CI (sin el CLI `snow`)

**Decision**: `ops/sql_runner.py` reutiliza `db.get_connection()` y ejecuta cada fichero `.sql`
con `conn.execute_string(texto_del_fichero)`, que el conector de Snowflake ya soporta para
scripts con varias sentencias separadas por `;`.

**Rationale**: `db.py` ya está preparado para esto — su propio docstring dice literalmente "en
CI desde GitHub Secrets. El código es el mismo en ambos casos". Añadir el CLI `snow` a CI
implicaría instalarlo en el runner, configurar una conexión con nombre y mantener dos caminos de
autenticación (el conector Python para tests, `snow` para despliegue) cuando uno solo ya vale.

**Alternatives considered**: Instalar y configurar `snow` en el workflow, replicando
`snowflake/README.md` §"Orden de puesta en marcha". Descartado por duplicar lo que
`snowflake-connector-python` ya hace, y por añadir una herramienta más a explicar en la demo
(Principio I).

---

## D-02: Estructura de workflows — tres ficheros, no uno

**Decision**: `pr-checks.yml`, `deploy.yml` y `revert.yml` como workflows separados.

**Rationale**: cada uno tiene un disparador distinto (`pull_request`, `push` a `main`,
`workflow_dispatch`) y una audiencia distinta (quien abre PR, el propio pipeline, quien ejecuta
un revert). Un solo fichero con `if: github.event_name == ...` anidados sería más corto pero
oscurecería justo la parte que la demo quiere enseñar: "esto pasa cuando abres una PR" frente a
"esto pasa cuando mergeas".

**Alternatives considered**: Un único `ci-cd.yml` con jobs condicionados por evento. Descartado
por legibilidad y porque los permisos de GitHub Actions (`permissions:`) difieren: `pr-checks`
solo necesita leer el repo, `deploy` necesita escribir el tag `deployed-good`, `revert` necesita
`workflow_dispatch` con input y también escribir el tag. Separarlos permite dar a cada uno el
mínimo permiso necesario (OWASP: principio de menor privilegio).

---

## D-03: Coste de correr la suite completa en cada PR y cada merge

**Decision**: se acepta correr la suite completa (`pytest`, sin `-m "not writes_db"` salvo que
una tarea puntual lo justifique) tanto en `pr-checks.yml` como en el primer job de `deploy.yml`,
tal como exige el Principio II literalmente ("ningún cambio... puede fusionarse ni desplegarse
sin pasar la suite de evaluación completa").

**Rationale**: es un mandato explícito y no negociable de la constitución, no una elección de
diseño de esta feature. El coste real (llamadas a Cortex Analyst y, según `LLM_PROVIDER`, a la
API de OpenAI) ya se paga hoy cada vez que alguien ejecuta `pytest` en local; CI simplemente lo
hace también de forma automática. Se documenta aquí para que quede explícito en el plan, no para
proponer una excepción.

**Alternatives considered**: correr solo un subconjunto rápido en PR y la suite completa solo en
`deploy.yml`. Descartado porque contradice al pie de la letra la regla de gate de la constitución
("Pull Request → suite completa de tests contra Snowflake").

---

## D-04: Cómo se testea un cambio de semantic view en una PR sin tocar la versión activa

**Decision**: `pr-checks.yml` despliega una versión **candidata** de la semantic view, nombrada
con el SHA de la cabeza de la PR (`SV_PHARMA_SALES_V<sha_corto>`), usando el mismo mecanismo de
`ops/semantic_view_registry.py` que usa `deploy.yml` — pero **sin** actualizar
`SEMANTIC_VIEW_ACTIVE`. La suite de tests se ejecuta con `SNOWFLAKE_SEMANTIC_VIEW` apuntando
explícitamente a ese objeto candidato (el override que `cortex_analyst.py` **ya soporta** desde
la feature 003, sin ningún cambio de código adicional). Al terminar el job, se hace
`DROP SEMANTIC VIEW IF EXISTS` del objeto candidato, pase o falle la suite.

**Rationale**: la constitución exige que la evaluación se ejecute contra Cortex Analyst real
sobre la semantic view real, no contra un mock; sin desplegar algo, no hay nada que evaluar. Al
no tocar el puntero activo, la producción no se entera de que hay una PR en marcha. Al limpiar el
objeto al final, no se acumulan candidatos de PRs abandonadas.

**Alternatives considered**: ejecutar los tests contra la versión ya activa en producción, sin
desplegar nada nuevo. Descartado: no validaría el cambio real propuesto por la PR, solo el
estado actual — exactamente el escenario que Principio II quiere impedir.

---

## D-05: Esquema de `SEMANTIC_VIEW_VERSIONS` y `SEMANTIC_VIEW_ACTIVE`

**Decision**: dos tablas con responsabilidades distintas (ver [data-model.md](./data-model.md)
y [contracts/semantic-view-versioning.md](contracts/semantic-view-versioning.md) para el DDL
completo):

- `SEMANTIC_VIEW_VERSIONS` — **insert-only**. Una fila por versión desplegada (incluidas las
  candidatas de PR), con el DDL completo (`DDL_TEXT`), para poder recrear cualquier versión
  aunque el objeto físico ya no exista.
- `SEMANTIC_VIEW_ACTIVE` — **mutable**, una fila por semantic view base. Es el puntero que
  `cortex_analyst.py` consulta en tiempo de ejecución.

**Rationale**: mezclar histórico y puntero en una tabla (p. ej. con una columna `IS_ACTIVE`)
obligaría a hacer `UPDATE` sobre un histórico, perdiendo la garantía de auditoría insert-only.
Separarlas es coherente con la misma razón que llevó a separar `DEPLOYMENTS` (log) del propio
estado desplegado.

**Alternatives considered**: una sola tabla con `IS_ACTIVE BOOLEAN`. Descartada por lo anterior;
además, complica la consulta "qué versiones existen" (habría que filtrar candidatas, y una fila
"activa" residual de una versión ya borrada físicamente sería ambigua).

---

## D-06: Convención de nombres y retención de versiones de semantic view

**Decision**: `SV_PHARMA_SALES_V<sha_corto>`, con `sha_corto` = 7 caracteres hexadecimales del
commit SHA. Se conservan como **objetos físicos** las últimas 5 versiones desplegadas a
producción (no las candidatas de PR, que se borran al final del job de PR — D-04). Versiones más
antiguas se **borran físicamente** pero su fila en `SEMANTIC_VIEW_VERSIONS` permanece, con el
`DDL_TEXT` completo: reactivarlas sigue siendo posible, solo que en vez de un cambio de puntero
instantáneo requiere recrear el objeto con `CREATE OR ALTER SEMANTIC VIEW` a partir de ese
`DDL_TEXT` (el mismo mecanismo *forward-fix* del ADR-002, aplicado a un solo objeto).

**Rationale**: un identificador de Snowflake no puede empezar por un dígito sin comillas; el
prefijo `V` lo evita sin necesidad de citar el identificador. La retención acotada cumple FR-020
sin perder la capacidad de auditoría ni la posibilidad de volver, aunque más lenta, a cualquier
versión histórica.

**Alternatives considered**: conservar todas las versiones indefinidamente. Descartado: crecer
sin límite es exactamente lo que FR-020 pide evitar, y en una demo de datos ficticios no aporta
valor pedagógico conservar cientos de objetos.

---

## D-07: Esquema de `DEPLOYMENTS`

**Decision**: tabla insert-only con `ACTION` (`DEPLOY` | `AUTO_ROLLBACK` | `MANUAL_REVERT`),
`TARGET_COMMIT_SHA`, `PREVIOUS_COMMIT_SHA`, `STATUS` (`SUCCESS` | `FAILED`), `REASON`,
`TRIGGERED_BY`, `WORKFLOW_RUN_URL`, `DEPLOYED_AT`. Ver DDL completo en
[contracts/deployments-table.md](contracts/deployments-table.md).

**Rationale**: es la fuente de auditoría que responde a FR-013 (quién, cuándo, hacia qué
versión) y a SC-005. `WORKFLOW_RUN_URL` conecta cada fila con los logs del run de GitHub Actions
que la generó, sin duplicar esos logs en Snowflake.

**Alternatives considered**: derivar todo esto de los logs de GitHub Actions únicamente.
Descartado: los logs no son consultables con SQL (Principio IV exige que se pueda "consultar con
SQL como cualquier otra tabla del proyecto") y expiran según la política de retención de Actions.

---

## D-08: Puntero de "última release buena" — tag Git + registro en Snowflake

**Decision**: se mantienen los dos, con roles distintos (ya acordado en el ADR-002):

- **Tag Git ligero `deployed-good`**, movido por `deploy.yml` tras un post-deploy exitoso, y
  usado por `ops/rollback.py` para saber a qué commit volver.
- **`DEPLOYMENTS`** en Snowflake, como auditoría consultable con SQL.

**Rationale**: el tag es lo que permite a `ops/rollback.py` hacer `git checkout` del commit
correcto sin depender de una consulta a Snowflake (útil incluso si el fallo post-deploy fue un
problema de Snowflake). `DEPLOYMENTS` es lo que permite auditar sin acceso al repositorio.

**Alternatives considered**: solo el tag Git (sin tabla). Descartado: no sería consultable con
SQL como el resto del proyecto, incumpliendo el estilo de observabilidad ya establecido en
`AGENT_TELEMETRY` / `V_AGENT_ACTIVITY`. Solo la tabla (sin tag): obligaría a que `rollback.py`
autentique contra Snowflake antes de saber qué commit descargar, añadiendo una dependencia de
orden entre pasos que el tag evita.

---

## D-09: Cómo se detecta y comunica el *drift* (FR-021, FR-022)

**Decision**: al final de `deploy.yml` (bloque `if: always()`), un paso compara
`deployed-good` con el SHA de `main` en ese momento:

- Si coinciden → no hay drift; si existía un GitHub Issue abierto con la etiqueta `drift`, se
  cierra automáticamente.
- Si no coinciden → se crea o actualiza un GitHub Issue con la etiqueta `drift`, indicando el SHA
  desplegado, el SHA de `main` y el motivo (tomado de `DEPLOYMENTS.REASON`).

Al principio de `deploy.yml`, un paso comprueba si existe un Issue `drift` abierto y, si lo hay,
añade una anotación de advertencia visible en el resumen del run (FR-022) — no bloquea el
despliegue, solo lo hace explícito.

**Rationale**: reutiliza GitHub (ya usado por el equipo) en vez de añadir un canal de
notificación nuevo (Slack, email), que la spec ya marcó como no especificado y de configuración
libre. Un Issue con etiqueta es visible, consultable y no requiere un workflow adicional
(`drift-check.yml` separado se descartó por redundante: la única vez que puede aparecer drift es
tras un rollback o revert, y ambos ya ocurren dentro de `deploy.yml`/`revert.yml`).

**Alternatives considered**: workflow `drift-check.yml` con `schedule` (cron) independiente.
Descartado por Principio I: añade un cuarto workflow para cubrir un caso que ya se puede detectar
en el mismo momento en que se produce, dentro de los workflows existentes.

---

## D-10: Validación de un revert manual hacia un SHA sin despliegue previo (FR-014)

**Decision**: `revert.yml` recibe `target_commit_sha` como input de texto libre;
`ops/revert.py` consulta `DEPLOYMENTS WHERE TARGET_COMMIT_SHA = :input AND STATUS = 'SUCCESS'`.
Si no hay ninguna fila, el job falla explícitamente con un mensaje ("no existe un despliegue
exitoso previo para ese SHA") antes de tocar Snowflake.

**Rationale**: cumple FR-014 literalmente ("rechazarse con un mensaje claro, sin dejar Snowflake
en un estado parcial") reutilizando la misma tabla de auditoría, sin necesitar acceso a Git para
validar.

**Alternatives considered**: validar solo que el SHA exista en el historial de Git (`git cat-file
-e`). Descartado: un commit puede existir en Git sin haber sido nunca desplegado (p. ej. un commit
en una rama que nunca llegó a `main`), lo que dejaría a `revert.py` intentando desplegar algo que
nunca se validó.

---

## D-11: Permisos y protección de rama

**Decision**: `main` se protege con: PR obligatoria (sin push directo), status check
`pr-checks` obligatorio, y **1 aprobación** de otra persona antes de mergear (ya exigido por el
Principio III/Flujo de Desarrollo de la constitución, no nuevo aquí). Cada workflow declara
`permissions:` mínimos explícitos: `pr-checks.yml` solo `contents: read`; `deploy.yml` y
`revert.yml` añaden `contents: write` (necesario para mover el tag `deployed-good`) e
`issues: write` (para el Issue de drift). Los secretos de Snowflake/OpenAI viven en un
**Environment** de GitHub llamado `production`, referenciado solo desde `deploy.yml` y
`revert.yml` — `pr-checks.yml` usa secretos de repositorio normales (de menor sensibilidad, sin
capacidad de desplegar).

**Rationale**: principio de menor privilegio (OWASP): el workflow que solo valida una PR no
necesita permiso de escritura sobre el repositorio ni acceso al Environment de producción.

**Alternatives considered**: un único conjunto de secretos a nivel de repositorio, sin
Environment. Descartado: cualquier PR (incluida una de un colaborador externo, si el repo lo
permitiera) podría en teoría acceder a los mismos secretos que el despliegue real.

---

## D-12: Fuera de alcance de esta feature (documentado para no reabrirlo en `tasks.md`)

- **pre-commit local**: no existe en el repo hoy; añadirlo es una mejora independiente.
- **Revert independiente por componente** (agente vs. semantic view por separado): descartado en
  el ADR-001; el revert siempre actúa sobre la release completa.
- **Blue/green o feature flags** para el código del agente: mencionado en el ADR-001 como
  siguiente escalón de madurez, no se implementa.
- **Notificaciones fuera de GitHub** (Slack, email): la spec lo deja como configuración libre;
  esta feature usa Issues de GitHub como mecanismo suficiente para una demo de 2-5 personas.
