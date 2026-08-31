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

## Estructura

```
src/conversational_analytics/   código
tests/                          tests
specs/                          artefactos Spec-Driven Development
.specify/memory/constitution.md principios vinculantes del proyecto
```

El desarrollo sigue [Spec Kit](https://github.com/github/spec-kit):
`specify → plan → tasks → implement`.
