# Implementation Plan: Dataset mock de ventas farma

**Branch**: `001-mock-sales-dataset` | **Date**: 2026-08-31 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/001-mock-sales-dataset/spec.md`

## Summary

Crear en `CICD_DEMO.DATA` tres tablas —`DIM_PRODUCT` (12), `DIM_COUNTRY` (10) y `FACT_SALES`
(12.960)— con 36 meses de ventas ficticias de una farmacéutica, listas para que el agente
conversacional las consulte.

Enfoque técnico: **SQL puro y determinista**. Las cifras no se generan con números aleatorios
ni con un script de Python, sino con una fórmula aritmética sobre los índices de cada fila
(producto, país, canal, mes). Eso hace la carga reproducible bit a bit en cualquier cuenta,
sin depender de `RANDOM()` ni de `HASH()`, y permite explicar el dataset entero en una
transparencia. Dos scripts idempotentes (`002_tables.sql` para la estructura, `003_seed.sql`
para los datos) desplegados con `snow sql -f`, y una suite de `pytest` que verifica las doce
invariantes del contrato antes de que exista el SQL.

Los ordinales que alimentan la fórmula son **fijos**, no derivados del orden de la dimensión:
añadir un producto o un país más adelante no altera las cifras históricas de los ya existentes.

## Technical Context

**Language/Version**: Python 3.14.6 en `.venv` (`requires-python = ">=3.11,<3.15"`).
SQL de Snowflake para todo el artefacto desplegable.

**Primary Dependencies**:

- `pytest ^8.3` (ya presente, grupo dev)
- `snowflake-connector-python ^4.7` — **nueva**, runtime
- `python-dotenv ^1.2` — **nueva**, runtime
- Snowflake CLI (`snow`) — herramienta externa, ya instalada, **no** es dependencia de Poetry

**Storage**: Snowflake. Base `CICD_DEMO`, schema `DATA`. Warehouse `COMPUTE_WH`.
Rol `CICD_DEMO_ROLE`, propietario de las tablas que crea.

**Testing**: `pytest` contra la instancia real de Snowflake. Sin mocks: lo que se valida es que
los datos desplegados cumplen el contrato, y eso no se puede simular.

**Target Platform**: Snowflake como destino; los scripts y tests se ejecutan desde Windows
(local) y Linux (GitHub Actions, en una feature posterior).

**Project Type**: proyecto único — scripts SQL versionados + una librería Python mínima.

**Performance Goals**: cualquier consulta de agregación del catálogo de preguntas de referencia
responde en menos de 5 s sobre `COMPUTE_WH` (XS). Con 12.960 filas (~1 MB) el margen es amplio.

**Constraints**:

- Determinismo estricto: mismo commit → mismas cifras en cualquier cuenta (FR-017).
- Idempotencia: reejecutar la carga no duplica ni altera nada (FR-018).
- Cero nulos, cero ventas netas negativas (SC-006).
- Rango histórico fijo, no relativo a `CURRENT_DATE` (FR-010).
- Sin datos reales ni personales (FR-019).

**Scale/Scope**: 3 tablas, 12.982 filas en total, ~1 MB. 2 scripts SQL, 1 módulo Python,
1 fichero de tests.

## Constitution Check

*GATE: revisado antes de la Fase 0 y de nuevo tras el diseño de la Fase 1. Ambas veces pasa.*

| Principio | Veredicto | Justificación |
|---|---|---|
| **I. Simplicidad orientada a la demo** | ✅ PASA | Tres tablas, dos scripts SQL, una fórmula. Sin ORM, sin framework de generación de datos, sin tabla de calendario, sin entidades accesorias. El modelo se explica en menos de 2 minutos (SC-005). Se rechazó explícitamente la cuarta tabla que se había sugerido (inventario). |
| **II. Evaluación del agente como test** | ✅ PASA | Todavía no hay agente, pero esta feature ya deja el [catálogo de 12 preguntas de referencia](contracts/reference-questions.md) versionado, con la aserción esperada de cada una, incluida una pregunta insatisfacible para validar el "no hay datos". Los tests de datos se escriben **antes** del SQL. |
| **III. CI/CD es el producto** | ✅ PASA | El 100 % del artefacto desplegable es SQL en Git. Nada se aplica a mano en la consola. Los scripts son idempotentes, luego reejecutables por el pipeline y reversibles volviendo a un commit anterior. |
| **IV. Observabilidad y control de coste** | ➖ N/A | Esta feature no invoca ningún modelo. Delta de tokens: **cero**. Se deja constancia expresa para que la PR no tenga que justificar coste. |
| **V. Reproducibilidad y gestión de secretos** | ✅ PASA | Dependencias por Poetry y `poetry.lock`. Credenciales sólo por variables de entorno; `.env` ignorado y `.env.example` ya documenta las 7 variables. Puesta en marcha: clonar, `poetry install`, rellenar `.env`, dos `snow sql -f`. |

**Restricciones tecnológicas**: se respetan (Python + Poetry, Snowflake, `pytest`). Se
introducen dos dependencias nuevas, justificadas abajo en Complexity Tracking.

## Project Structure

### Documentation (this feature)

```text
specs/001-mock-sales-dataset/
├── plan.md                            # Este fichero
├── spec.md                            # Fase 1 (speckit-specify)
├── research.md                        # Fase 0 — 8 decisiones tecnicas
├── data-model.md                      # Fase 1 — esquema, datos y formula
├── quickstart.md                      # Fase 1 — desplegar y validar
├── contracts/
│   ├── dataset-contract.md            # Garantias a los consumidores + mapa de tests
│   └── reference-questions.md         # 12 preguntas de referencia (SC-003)
├── checklists/
│   └── requirements.md                # Calidad de la spec
└── tasks.md                           # Fase 3 — NO lo crea speckit-plan
```

### Source Code (repository root)

```text
snowflake/
├── 001_bootstrap.sql                  # Ya existe — no se toca
├── 002_tables.sql                     # NUEVO — DDL de las 3 tablas
├── 003_seed.sql                       # NUEVO — carga determinista
└── manual/
    └── grant_user.sql                 # Ya existe — no se toca

src/conversational_analytics/
├── __init__.py                        # Ya existe
└── db.py                              # NUEVO — get_connection() desde variables de entorno

tests/
├── conftest.py                        # NUEVO — fixture de conexion, helpers de consulta
├── test_connection.py                 # NUEVO — smoke test de conectividad
├── test_dataset.py                    # NUEVO — 13 tests de las 12 invariantes
└── test_reference_questions.py        # NUEVO — las 12 preguntas de referencia (SC-003)
```

**Structure Decision**: proyecto único. El artefacto que se despliega es SQL bajo `snowflake/`,
siguiendo la numeración ya establecida en [snowflake/README.md](../../snowflake/README.md)
(`002_tables.sql` y `003_seed.sql` ya estaban previstos ahí como pendientes). El código Python
se limita a lo imprescindible para que `pytest` pueda conectarse: un único helper en
`src/conversational_analytics/db.py`, que reutilizarán después el agente y la telemetría. No se
crean carpetas `models/`, `services/` ni `cli/`: no hay lógica de negocio en Python en esta
feature y crearlas vacías contradiría el Principio I.

## Complexity Tracking

> Ninguna violación de la constitución. Se documentan aquí las dos dependencias nuevas porque
> las Restricciones Tecnológicas exigen justificar por escrito cualquier añadido.

| Añadido | Por qué es necesario | Alternativa más simple, y por qué se rechaza |
|---|---|---|
| `snowflake-connector-python` | La constitución fija `pytest` como runner y exige tests contra Snowflake. Sin cliente Python no hay forma de ejecutar ni una sola aserción. | *Validar sólo con `snow sql` y comparar salidas a ojo*: no es automatizable ni integrable en CI, y deja los tests fuera del gate de PR. Se descarta también `snowflake-snowpark-python`: arrastra un stack mucho mayor para ejecutar cuatro `SELECT COUNT(*)`. |
| `python-dotenv` | Carga `.env` en local. En CI no encuentra fichero y no hace nada, así que el código de conexión es **uno solo** para local y para CI. | *Leer sólo `os.environ` y exigir que cada dev exporte 7 variables a mano en cada sesión*: fricción diaria y una fuente segura de errores; además rompe el "clonar, `poetry install`, rellenar `.env`" del Principio V. |
| Módulo `db.py` | Centraliza la lectura de 7 variables de entorno y la apertura de conexión. | *Repetir el bloque de conexión en cada test*: duplicación que habría que tocar en cada feature futura. No es abstracción especulativa: el agente y la telemetría lo consumirán. |

## Riesgo abierto

**Wheel del conector para Python 3.14.** El venv corre 3.14.6 y la máquina no tiene compilador
C. La resolución en seco de `snowflake-connector-python 4.7.2` para 3.14 se completó sin
errores, pero **la instalación real no está verificada**. Mitigación si falla: recrear el venv
con Python 3.12 (`requires-python` ya lo admite). Debe ser la **primera tarea** de la fase de
implementación, antes de escribir ningún test. Detalle en [research.md](research.md) (D-06).

## Artefactos de la Fase 1

| Artefacto | Contenido |
|---|---|
| [research.md](research.md) | 8 decisiones: generación determinista, `SEQ4`, idempotencia, neto derivado, despliegue, acceso desde tests, rango fijo, ordinales estables |
| [data-model.md](data-model.md) | Esquema de las 3 tablas, las 22 filas de dimensión literales, la fórmula completa y 12 invariantes |
| [contracts/dataset-contract.md](contracts/dataset-contract.md) | 8 garantías al consumidor, 4 no-garantías, y el mapa invariante → test |
| [contracts/reference-questions.md](contracts/reference-questions.md) | 12 preguntas de referencia con su aserción esperada |
| [quickstart.md](quickstart.md) | Prerrequisitos, despliegue, validación y guía de fallos |
