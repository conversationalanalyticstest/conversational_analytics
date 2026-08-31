# SQL de Snowflake

Todo el estado de Snowflake vive aquí y se versiona en Git (Principio III de la
[constitución](../.specify/memory/constitution.md): nada se aplica a mano en la consola).

## Scripts numerados

Se ejecutan en orden. Deben ser **idempotentes** y no contener datos de una cuenta concreta.

| Fichero | Qué hace |
|---|---|
| [001_bootstrap.sql](001_bootstrap.sql) | Rol, base de datos, schemas y grants base |

Pendientes (aún no creados): `002_tables.sql`, `003_seed.sql`, `004_semantic_view.sql`,
`005_agent.sql`.

## Scripts manuales (`manual/`)

Fuera de la secuencia numerada porque **dependen del entorno o de la persona**. No los ejecuta
el pipeline.

| Fichero | Qué hace |
|---|---|
| [manual/grant_user.sql](manual/grant_user.sql) | Da `CICD_DEMO_ROLE` a un usuario y fija su contexto por defecto |

## Orden de puesta en marcha

1. Ejecutar `001_bootstrap.sql` como `ACCOUNTADMIN`.
2. Editar `manual/grant_user.sql` con tu usuario y ejecutarlo.
3. Rellenar `.env` a partir de `.env.example` (`SNOWFLAKE_ROLE=CICD_DEMO_ROLE`,
   `SNOWFLAKE_DATABASE=CICD_DEMO`).
