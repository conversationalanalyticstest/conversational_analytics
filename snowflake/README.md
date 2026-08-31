# SQL de Snowflake

Todo el estado de Snowflake vive aquí y se versiona en Git (Principio III de la
[constitución](../.specify/memory/constitution.md): nada se aplica a mano en la consola).

## Scripts numerados

Se ejecutan en orden. Deben ser **idempotentes** y no contener datos de una cuenta concreta.

| Fichero | Qué hace |
|---|---|
| [001_bootstrap.sql](001_bootstrap.sql) | Rol, base de datos, schemas y grants base |
| [002_tables.sql](002_tables.sql) | Estructura del dataset mock: `DIM_PRODUCT`, `DIM_COUNTRY` y `FACT_SALES` |
| [003_seed.sql](003_seed.sql) | Carga del dataset mock: 12 productos, 10 países y 12.960 ventas mensuales, generadas de forma determinista |

Pendientes (aún no creados): `004_semantic_view.sql`, `005_agent.sql`.

## Scripts manuales (`manual/`)

Fuera de la secuencia numerada porque **dependen del entorno o de la persona**. No los ejecuta
el pipeline.

| Fichero | Qué hace |
|---|---|
| [manual/grant_user.sql](manual/grant_user.sql) | Da `CICD_DEMO_ROLE` a un usuario y fija su contexto por defecto |

## Orden de puesta en marcha

1. Ejecutar `001_bootstrap.sql` como `ACCOUNTADMIN`.
2. Editar `manual/grant_user.sql` con tu usuario y ejecutarlo.
3. Crear un PAT restringido al rol de la demo y rellenar `.env` a partir de `.env.example`
   (`SNOWFLAKE_PAT`, `SNOWFLAKE_ROLE=CICD_DEMO_ROLE`, `SNOWFLAKE_DATABASE=CICD_DEMO`).
4. Guardar **el mismo** PAT en `pat.txt` en la raíz del repositorio y registrar la conexión
   `cicd_demo` de la CLI apuntando a ese fichero (ver
   [quickstart.md](../specs/001-mock-sales-dataset/quickstart.md)).
5. Desplegar el dataset:
   ```powershell
   snow sql --connection cicd_demo -f snowflake/002_tables.sql
   snow sql --connection cicd_demo -f snowflake/003_seed.sql
   ```

> ⚠️ **El PAT vive en dos ficheros**: `.env` (lo lee `pytest`) y `pat.txt` (lo lee `snow`). Los
> dos están en `.gitignore` y contienen el secreto en texto plano. **Al rotarlo, actualiza los
> dos.** Es una excepción consciente al Principio V de la constitución, justificada en
> [plan.md](../specs/001-mock-sales-dataset/plan.md#complexity-tracking).

## Validar

```powershell
poetry run pytest -v
```

Los tests marcados con `writes_db` **recargan datos** en Snowflake (comprueban que el seed es
idempotente). Para dejarlos fuera:

```powershell
poetry run pytest -v -m "not writes_db"
```

Guía completa en
[specs/001-mock-sales-dataset/quickstart.md](../specs/001-mock-sales-dataset/quickstart.md).
