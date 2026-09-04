# Research: Aislar el check de PR contra una copia de la semantic view

**Feature**: [005-pr-checks-semantic-isolation](./spec.md) · **Plan**: [plan.md](./plan.md)

## D-01: Cómo se construye la copia candidata

**Decision**: sustitución de texto en memoria. El paso de build lee
`snowflake/004_semantic_view.sql` del working tree (ya es el contenido de la PR, checkout
normal), reemplaza el token literal `SV_PHARMA_SALES` por `SV_PHARMA_SALES_PR<número-de-PR>` en
las 12 apariciones del fichero (la del `CREATE OR ALTER` y las de `CICD_DEMO.DATA.SV_PHARMA_SALES`
en las `AI_VERIFIED_QUERIES`), y ejecuta el resultado con `sql_runner.run_sql_string()` (ya
existe, usada hoy por `ops/deploy.py`).

**Rationale**: es la operación más simple que produce un objeto funcionalmente idéntico bajo
otro nombre, sin tocar el fichero en disco ni el repositorio.

**Alternatives considered**:
- Leer el contenido con `git show <sha>:snowflake/004_semantic_view.sql`, como hacen
  `rollback.py`/`revert.py`. Rechazada: ese truco existe para poder reconstruir un commit
  *distinto* al que está en el working tree; en `pr-checks.yml` el checkout ya es el de la PR,
  así que leer el fichero en disco es más simple y hace lo mismo.
- Templating real (Jinja2 o similar) del fichero fuente, con el nombre del objeto como
  parámetro. Rechazada: [ADR-003](../004-ci-cd-pipeline/decisions/003-simplificacion-semantic-view.md)
  fija explícitamente que `004_semantic_view.sql` no lleva templating ("nombre fijo"); introducir
  una plantilla permanente en el fichero de producción por una necesidad exclusiva de PR sería
  romper esa decisión sin necesidad, cuando una sustitución en memoria basta.
- Clonar físicamente las tablas subyacentes (zero-copy clone de `CICD_DEMO.DATA`) para aislar
  también los datos. Rechazada: los tests de evaluación son de solo lectura sobre
  `DIM_PRODUCT`/`DIM_COUNTRY`/`FACT_SALES`; ninguna PR de las contempladas cambia esas tablas, y
  clonar el esquema completo añade una pieza de infraestructura (gestión del clon, su borrado,
  su coste) para un problema que no existe hoy.

## D-02: Identificador de la copia — número de PR, no SHA de commit

**Decision**: `SV_PHARMA_SALES_PR<número-de-PR>`, usando
`github.event.pull_request.number` (estable durante toda la vida de la PR).

**Rationale**: al ser estable, cada push a la misma PR puede reusar el mismo objeto con
`CREATE OR ALTER` en vez de crear uno nuevo por commit — menos objetos que gestionar, y el
nombre es derivable de forma independiente en cualquier paso del job sin tener que pasar
`$GITHUB_OUTPUT` entre pasos (a diferencia del mecanismo retirado en ADR-003, que sufijaba por
SHA corto porque el objeto representaba una versión concreta a desplegar, no un candidato vivo
mientras la PR está abierta).

**Alternatives considered**: sufijo por SHA corto (`SV_PHARMA_SALES_V<sha>`, como en el
mecanismo eliminado). Rechazada: generaría un objeto nuevo en cada push sin recuperar el
anterior automáticamente, exigiendo lógica de limpieza adicional para los objetos de pushes
previos de la misma PR.

## D-03: Limpieza — `if: always()` + trigger `closed`, sin cron

**Decision**: dos mecanismos, ambos dentro del mismo `pr-checks.yml`:

1. Paso `if: always()` al final del job: elimina la candidata de esa ejecución tanto si los
   tests pasan como si fallan.
2. `pull_request.types` incluye `closed` además de `opened`/`synchronize`/`reopened`: cuando la
   PR se cierra (fusionada o no), el job se dispara de nuevo únicamente para ejecutar el paso de
   limpieza (los pasos de build/test se saltan con
   `if: github.event.action != 'closed'`).

**Rationale**: el mecanismo 1 cubre el caso normal. El mecanismo 2 es la red de seguridad para
una ejecución cancelada antes de llegar a su propio paso de limpieza (p. ej. por
`cancel-in-progress: true` al llegar un nuevo push): como el nombre del objeto es estable por PR
(D-02), cualquier candidata huérfana de un push cancelado se sobrescribe (`CREATE OR ALTER`) en
el siguiente push, o se elimina en el momento en que la PR se cierra. El número de candidatas
vivas en un momento dado queda acotado por el número de PRs abiertas que han ejecutado el check
al menos una vez — nunca crece de forma indefinida (SC-004).

**Alternatives considered**:
- Workflow `schedule` (cron) que liste `SHOW SEMANTIC VIEWS` y purgue las de PRs ya cerradas.
  Rechazada por Principio I: añadiría un cuarto workflow para un caso que el trigger `closed` ya
  cubre sin pasos adicionales ni programación.
- Tabla de registro en Snowflake de "candidatas vivas" (igual que
  `SEMANTIC_VIEW_VERSIONS`/`SEMANTIC_VIEW_ACTIVE` en el mecanismo que ADR-003 eliminó).
  Rechazada explícitamente: es la pieza que ADR-003 quitó por duplicar estado sin necesidad; el
  nombre determinista por PR (D-02) hace innecesario cualquier registro.

## D-04: Ámbito de la copia — solo la semantic view, no las tablas físicas

**Decision**: la candidata es únicamente el objeto `SEMANTIC VIEW`; las tablas físicas
(`DIM_PRODUCT`, `DIM_COUNTRY`, `FACT_SALES`) siguen siendo las mismas de producción, compartidas
por todas las candidatas y por `SV_PHARMA_SALES`.

**Rationale**: los tests de evaluación del agente son de solo lectura; ninguna PR contemplada en
esta feature cambia datos. Aislar solo la definición lógica es suficiente para el problema
descrito (validar la definición de la semantic view antes de fusionar).

**Alternatives considered**: clon zero-copy de todo el esquema `CICD_DEMO.DATA` por PR.
Rechazada por sobre-ingeniería (Principio I) — resolvería un problema (aislamiento de datos) que
no está planteado en la spec ni pedido por el usuario.

## D-05: `DEPLOYMENTS` no se toca

**Decision**: crear o eliminar una candidata de PR no inserta ninguna fila en `DEPLOYMENTS`.

**Rationale**: esa tabla es auditoría de despliegues reales a producción
([D-07 de 004](../004-ci-cd-pipeline/research.md)); una candidata de PR nunca despliega nada en
producción, así que registrarla ahí sería ruido, no auditoría.

**Alternatives considered**: registrar también las candidatas para trazabilidad. Rechazada: la
traza de qué candidata se creó y cuándo ya existe en el propio log del run de GitHub Actions,
visible desde la PR; duplicarla en `DEPLOYMENTS` no aporta nada que esa tabla no tenga ya para su
propósito (auditoría de producción).

## D-06: Relación formal con ADR-003 (feature 004)

**Decision**: esta feature no reescribe ADR-003. Se documenta como un ADR propio,
[decisions/001-aislar-semantic-view-candidata-en-pr.md](decisions/001-aislar-semantic-view-candidata-en-pr.md),
que supersede explícitamente **solo el punto 4** de ADR-003 ("se elimina el mecanismo de
semantic view candidata en pr-checks.yml"). El resto de ADR-003 — objeto único en producción,
sin versionado con puntero, rollback/revert vía `git show` — sigue vigente y esta feature no lo
toca.

**Rationale**: mantiene el historial de decisiones honesto (qué se decidió, cuándo, y por qué se
revirtió parcialmente) en vez de editar ADR-003 como si la decisión original nunca hubiera
existido.
