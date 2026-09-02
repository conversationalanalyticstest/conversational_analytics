# Quickstart: agente conversacional

**Feature**: `003-conversational-agent` | **Fecha**: 2026-09-01 | **Fase**: 1

Cómo poner en marcha y validar el agente **una vez implementado**. Este fichero es la guía de
ejecución y validación; los detalles de diseño están en [plan.md](./plan.md) y
[contracts/](./contracts/).

## 0. Prerrequisitos

| | |
|---|---|
| Features previas | 001 y 002 desplegadas: tablas cargadas y `SV_PHARMA_SALES` operativa |
| Snowflake | Cuenta con Cortex habilitado; rol `CICD_DEMO_ROLE` |
| Local | Python 3.11–3.14, Poetry, `.env` relleno |

Comprobación rápida de que las features previas siguen en pie:

```powershell
.venv\Scripts\python.exe -m pytest tests/test_semantic_view.py -q
```

## 1. Grants y despliegue de la telemetría

Dos pasos, ambos desde la raíz del repo (`pat.txt` tiene ruta relativa).

**1.1 — Grants actualizados.** `001_bootstrap.sql` añade `CREATE TABLE, CREATE VIEW` sobre el
esquema `DEVOPS`. Requiere `ACCOUNTADMIN`:

```powershell
snow sql -f snowflake/001_bootstrap.sql -c cicd_demo
```

**1.2 — Verificar el rol por defecto del usuario.** La API REST de Cortex resuelve permisos contra
el rol **por defecto** del usuario, no contra el de la sesión (ver
[research.md](./research.md), D-04). Si esto no cuadra, el conector funciona pero las llamadas REST
devuelven `403`:

```sql
SHOW USERS LIKE 'CONVERSATIONALANALYTICSTEST';
-- La columna default_role debe ser CICD_DEMO_ROLE.
-- Si no: ALTER USER CONVERSATIONALANALYTICSTEST SET DEFAULT_ROLE = CICD_DEMO_ROLE;
```

**1.3 — Tabla y vista de telemetría:**

```powershell
snow sql -f snowflake/005_telemetry.sql -c cicd_demo
```

Verificación:

```sql
SELECT COUNT(*) FROM CICD_DEMO.DEVOPS.AGENT_TELEMETRY;   -- 0 en un despliegue limpio
SELECT * FROM CICD_DEMO.DEVOPS.V_AGENT_ACTIVITY LIMIT 1; -- la vista resuelve
```

## 2. Dependencias

```powershell
# Poetry sondea el Python 3.12 roto del PATH; hay que limpiarlo antes
$clean = ($env:PATH -split ';' | Where-Object { $_ -notlike '*Python312*' }) -join ';'
$env:PATH = "C:\Program Files\Python314;C:\Users\dsanchezramos\.local\bin;$clean"

poetry install
```

Añade `openai` y `httpx`. Si alguna dependencia transitiva no trae *wheel* para Python 3.14, la
instalación falla: no hay compilador C en esta máquina. En ese caso, recrear el venv con 3.12
(`poetry env use 3.12`), que sigue dentro del rango de `requires-python`.

## 3. Variables de entorno

Al `.env` existente se añaden, según el proveedor elegido (`LLM_PROVIDER`, D-11):

```ini
# Por defecto hoy: LLM_PROVIDER=openai (la cuenta Snowflake de esta demo es trial
# y no tiene inferencia Cortex habilitada, ver research.md D-11)
LLM_PROVIDER=openai
OPENAI_API_KEY=<clave real, nunca commitear>
OPENAI_MODEL=gpt-4.1-mini

# Alternativa, si una cuenta de pago habilita Cortex:
# LLM_PROVIDER=cortex
# CORTEX_MODEL=<modelo verificado en la tarea de arranque>

# Opcional en ambos casos
SNOWFLAKE_SEMANTIC_VIEW=CICD_DEMO.DATA.SV_PHARMA_SALES
```

**Con `LLM_PROVIDER=cortex`, `OPENAI_API_KEY` no debe existir en `.env`.** Es un invariante
verificado por `test_provider_matches_config` (D-08): si aparece cuando no toca, el test falla a
propósito.

## 4. Verificar proveedor, modelo y conectividad antes de nada

Primera tarea real de la implementación (D-05, D-11): confirmar que el proveedor configurado
responde y que el modelo soporta `tools`.

```powershell
.venv\Scripts\python.exe -m conversational_analytics.cli --check
```

Debe reportar: proveedor efectivo (`openai` o `cortex`), modelo efectivo, que el endpoint de chat
completions responde y que Cortex Analyst responde. Fallos esperables y su causa:

| Error | Causa probable |
|---|---|
| `401` en el orquestador | `OPENAI_API_KEY` inválida o caducada (si `LLM_PROVIDER=openai`), o PAT caducado (si `cortex`) |
| `401` en Cortex Analyst | PAT caducado |
| `403` en Cortex Analyst | Falta `SNOWFLAKE.CORTEX_USER` en el **rol por defecto** (paso 1.2) |
| `403` en el orquestador con `LLM_PROVIDER=cortex` | Cuenta sin entitlement de inferencia Cortex (verificado en esta cuenta, D-11) — cambiar a `LLM_PROVIDER=openai` |
| `400` modelo no disponible | Con `cortex`: modelo no habilitado en la región → probar otro o activar *cross-region inference* |

## 5. Hacer una pregunta

```powershell
.venv\Scripts\python.exe -m conversational_analytics.cli "¿Cuáles fueron las ventas netas totales en 2025?"
```

Esperado: una frase con un único número positivo.

Con el detalle de lo que ha pasado por debajo — esto es lo que se enseña en la demo:

```powershell
.venv\Scripts\python.exe -m conversational_analytics.cli --verbose "¿Cuál es el top 5 de marcas por ventas netas en Europa?"
```

`--verbose` muestra el SQL generado por Cortex Analyst, si se usó una `AI_VERIFIED_QUERY`, el
estado, los tokens y la latencia.

Caso sin datos (Q-12), que **no** es un error:

```powershell
.venv\Scripts\python.exe -m conversational_analytics.cli "¿Cuánto vendimos en 2021?"
```

Esperado: mensaje explícito de ausencia de datos, sin cifra inventada, y código de salida `0`.

## 6. Suite de evaluación (Principio II)

```powershell
# Las 12 preguntas del catálogo de referencia
.venv\Scripts\python.exe -m pytest tests/test_agent_evaluation.py -v

# Contratos: stateless, anti-fuga, errores, sin acceso directo a tablas
.venv\Scripts\python.exe -m pytest tests/test_agent_contract.py -v

# Todo lo de la feature, excluyendo lo que escribe en Snowflake
.venv\Scripts\python.exe -m pytest -m "not writes_db" -q
```

Los asserts van sobre las filas devueltas por el SQL, no sobre el texto redactado (D-07). Un test
que falla aquí bloquea el despliegue; no se desactiva (Flujo de Desarrollo de la constitución).

Cada ejecución consume tokens reales del proveedor configurado (OpenAI por defecto, o Cortex si
`LLM_PROVIDER=cortex`). La suite completa son ~12 invocaciones con al menos
dos llamadas al modelo cada una.

## 7. Comprobar la telemetría (Principio IV)

Tras ejecutar la suite:

```sql
SELECT EVENT_TS, SOURCE, QUESTION, STATUS, USED_VERIFIED_QUERY, TOTAL_TOKENS, LATENCY_MS
FROM CICD_DEMO.DEVOPS.V_AGENT_ACTIVITY
ORDER BY EVENT_TS DESC
LIMIT 20;
```

Esto valida **SC-003**: el 100% de las invocaciones queda registrado, verificable por SQL directo.
Debe haber una fila por invocación, incluidas las de estado `NO_DATA`.

Coste acumulado y señal de calidad:

```sql
SELECT PROVIDER,
       COST_UNIT,
       COUNT(*) AS INVOCATIONS,
       SUM(TOTAL_TOKENS) AS TOKENS,
       ROUND(SUM(ESTIMATED_COST), 4) AS COST,
       ROUND(100.0 * SUM(IFF(USED_VERIFIED_QUERY, 1, 0)) / COUNT(*), 1) AS PCT_VERIFIED
FROM CICD_DEMO.DEVOPS.V_AGENT_ACTIVITY
GROUP BY PROVIDER, COST_UNIT;
```

`PCT_VERIFIED` será `0%` hasta que se corrijan las `AI_VERIFIED_QUERIES` de la feature 002 (defecto
conocido, no bloquea esta feature — ver research.md D-06).

Más consultas en [contracts/telemetry-table.md](./contracts/telemetry-table.md).

## 8. Guion de demo (SC-004)

Cinco minutos, un fichero por paso:

| Paso | Fichero | Qué se enseña |
|---|---|---|
| 1 | `cli.py` | Entra una pregunta |
| 2 | `llm_provider.py` | Se construye el cliente según `LLM_PROVIDER` — hoy OpenAI público |
| 3 | `agent.py` | El SDK de OpenAI decide llamar a la herramienta |
| 4 | `cortex_analyst.py` | La herramienta pide el SQL a Cortex Analyst con la semantic view |
| 5 | `db.py` | Se ejecuta el SQL — Cortex Analyst no lo ejecuta él |
| 6 | `agent.py` | El modelo redacta la respuesta con las filas |
| 7 | `V_AGENT_ACTIVITY` | Todo ha quedado registrado en Snowflake, incluido qué proveedor se usó |

Punto que suele sorprender a la audiencia: la traducción a SQL sigue pasando siempre por Cortex
Analyst, dentro de Snowflake — sólo la redacción final puede salir a OpenAI, y queda declarado en
cada fila de telemetría (`PROVIDER`). Enseñar `test_provider_matches_config` cierra la explicación.

## Resolución de problemas

| Síntoma | Causa | Solución |
|---|---|---|
| `403` en Cortex Analyst, conector OK | Rol por defecto del usuario | Paso 1.2 |
| `403` en el orquestador con `LLM_PROVIDER=cortex` | Cuenta sin entitlement de inferencia Cortex | Cambiar a `LLM_PROVIDER=openai` (D-11) |
| `401` en todo a la vez | PAT caducado | Regenerar y actualizar `.env` y `pat.txt` |
| `401` sólo en el orquestador | `OPENAI_API_KEY` inválida | Regenerar en `platform.openai.com` |
| El modelo nunca llama a la herramienta | El modelo no soporta `tools` | Cambiar `OPENAI_MODEL`/`CORTEX_MODEL` (D-05) |
| `SQL compilation error` con la vista de telemetría | Falta el grant del paso 1.1 | Reejecutar `001_bootstrap.sql` |
| `snow` se cuelga o falla intermitentemente | Terminal degradado | Abrir un terminal nuevo y reintentar |
| Tests de evaluación intermitentes | Aserciones sobre la prosa, no sobre las filas | Corregir el test: viola D-07 |
| `PCT_VERIFIED` siempre en 0% | Verified queries de la feature 002 con nombres físicos | Defecto conocido, fuera de alcance (D-06); no bloquea |
