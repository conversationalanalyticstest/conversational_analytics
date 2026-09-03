# conversational_analytics

Demo pedagógica de **CI/CD sobre Snowflake con Git**: un agente conversacional que responde
preguntas consultando datos en Snowflake a través de *semantic views*.

## Requisitos

- **Python 3.11–3.14** (`<3.15`)
- **Poetry 2.x**

## Puesta en marcha

```bash
git clone <url-del-repo>
cd conversational_analytics
poetry install
cp .env.example .env    # Windows: copy .env.example .env
```

Rellena `.env` con tus credenciales de Snowflake. **Nunca se commitea.**

Ejecutar comandos dentro del entorno:

```bash
poetry run pytest
```

## Cómo garantiza Poetry que a todos les funcione igual

| Fichero | Se commitea | Qué hace |
|---|---|---|
| `pyproject.toml` | Sí | Declara las dependencias como **rangos** (`pytest = "^8.3"`) y la versión de Python admitida |
| `poetry.lock` | **Sí, obligatorio** | Fija la versión **exacta** de cada paquete y de sus transitivas, con hash de integridad |
| `poetry.toml` | Sí | Fuerza que el venv se cree en `.venv/` dentro del proyecto |
| `.env.example` | Sí | Plantilla de variables, sin valores |
| `.env`, `.venv/` | No | Locales de cada persona |

`poetry install` **lee el lock, no resuelve de nuevo**. Por eso todo el mundo obtiene exactamente
las mismas versiones, en cualquier sistema operativo, hasta que alguien cambie el lock a propósito.

Comandos útiles:

```bash
poetry check          # ¿pyproject y poetry.lock están sincronizados?
poetry sync           # deja el venv EXACTO al lock (borra lo que sobre)
poetry add <paquete>  # añade dependencia y actualiza el lock (commitea el lock)
```

> Si cambias `pyproject.toml` a mano, ejecuta `poetry lock` y commitea el `poetry.lock`
> resultante. Una PR que toque dependencias sin actualizar el lock debe rechazarse.

### Lo que el lock NO cubre

El lock fija los paquetes, **no el intérprete de Python**. Cada persona necesita un Python
3.11–3.14 propio. Si no tienes uno:

```bash
poetry python install 3.14   # experimental, descarga un Python standalone
```

En CI se fija con `actions/setup-python`.

## Agente conversacional

Traduce preguntas en lenguaje natural a SQL sobre `SV_PHARMA_SALES` con **Cortex Analyst**
(obligatorio, Principio del proyecto) y orquesta la conversación con el **SDK de OpenAI**,
apuntando a la API pública de OpenAI o al endpoint de Cortex según `LLM_PROVIDER`. Detalle de
diseño en [specs/003-conversational-agent](specs/003-conversational-agent/plan.md).

```bash
poetry run python -m conversational_analytics.cli "¿Cuáles fueron las ventas netas totales en 2025?"
poetry run python -m conversational_analytics.cli --verbose "¿Qué producto vendió más en Francia?"
poetry run python -m conversational_analytics.cli --check   # comprueba proveedor y conectividad
```

Variables relevantes en `.env` (ver `.env.example`):

| Variable | Obligatoria si | Qué hace |
|---|---|---|
| `LLM_PROVIDER` | — | `openai` (por defecto) o `cortex`; decide qué credencial y `base_url` usa el SDK |
| `OPENAI_API_KEY` | `LLM_PROVIDER=openai` | Clave de la API pública de OpenAI |
| `OPENAI_MODEL` / `CORTEX_MODEL` | — | Modelo a usar; hay valores por defecto razonables |
| `SNOWFLAKE_SEMANTIC_VIEW` | — | Semantic view a consultar (`CICD_DEMO.DATA.SV_PHARMA_SALES` por defecto) |

Cada invocación queda registrada en `CICD_DEMO.DEVOPS.AGENT_TELEMETRY` (pregunta, SQL generado,
proveedor/modelo, tokens, coste estimado, latencia y estado) — ver
[snowflake/005_telemetry.sql](snowflake/005_telemetry.sql) y
[snowflake/README.md](snowflake/README.md).

## CI/CD

Cada cambio a `main` pasa por una pipeline de GitHub Actions con protección de rama, despliegue
versionado a Snowflake y rollback automático. Detalle completo (arquitectura, ADRs, pasos
manuales de configuración y guion de validación) en
[specs/004-ci-cd-pipeline/quickstart.md](specs/004-ci-cd-pipeline/quickstart.md).

| Workflow | Se dispara | Qué hace |
|---|---|---|
| `.github/workflows/pr-checks.yml` | PR contra `main` | Despliega una semantic view candidata desechable y corre la suite contra ella; check requerido por la protección de rama |
| `.github/workflows/deploy.yml` | push a `main` | Corre la suite, despliega una release versionada (`SV_..._V<sha_corto>`), evalúa post-deploy y hace rollback automático (forward-fix) si falla |
| `.github/workflows/revert.yml` | manual (`workflow_dispatch`) | Revierte a demanda a cualquier commit con un despliegue `SUCCESS` previo |

Toda la lógica de despliegue/rollback/revert vive en `src/conversational_analytics/ops/`
(módulos testeados con `pytest`); los workflows son orquestación fina que invoca
`poetry run python -m conversational_analytics.ops.<módulo>`.

## Estructura

```
src/conversational_analytics/   código
tests/                          tests
specs/                          artefactos Spec-Driven Development
.specify/memory/constitution.md principios vinculantes del proyecto
```

El desarrollo sigue [Spec Kit](https://github.com/github/spec-kit):
`specify → plan → tasks → implement`.
