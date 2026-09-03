# Contrato: versionado de semantic views (`SEMANTIC_VIEW_VERSIONS` / `SEMANTIC_VIEW_ACTIVE`)

**Feature**: [004-ci-cd-pipeline](../spec.md) · **Data model**: [../data-model.md](../data-model.md) ·
**Decisión**: [../decisions/001-estrategia-de-revert.md](../decisions/001-estrategia-de-revert.md)

## DDL

```sql
USE ROLE CICD_DEMO_ROLE;
USE WAREHOUSE COMPUTE_WH;
USE SCHEMA CICD_DEMO.DEVOPS;

CREATE TABLE IF NOT EXISTS SEMANTIC_VIEW_VERSIONS (
    VERSION_ID   NUMBER AUTOINCREMENT,
    BASE_NAME    STRING NOT NULL,
    OBJECT_NAME  STRING NOT NULL,
    COMMIT_SHA   STRING NOT NULL,
    DDL_TEXT     STRING NOT NULL,
    IS_CANDIDATE BOOLEAN NOT NULL DEFAULT FALSE,
    DEPLOYED_AT  TIMESTAMP_NTZ NOT NULL DEFAULT CURRENT_TIMESTAMP()
);

-- Puntero mutable: una fila por semantic view base. A diferencia de la tabla anterior, esta SI
-- se actualiza in place (MERGE/UPDATE), porque representa el estado actual, no un historico.
CREATE TABLE IF NOT EXISTS SEMANTIC_VIEW_ACTIVE (
    BASE_NAME          STRING NOT NULL,
    ACTIVE_OBJECT_NAME STRING NOT NULL,
    ACTIVE_COMMIT_SHA  STRING NOT NULL,
    UPDATED_AT         TIMESTAMP_NTZ NOT NULL,
    UPDATED_BY         STRING NOT NULL,
    PRIMARY KEY (BASE_NAME)
);
```

## Convención de nombres (D-06)

`<BASE_NAME>_V<sha_corto>`, con `sha_corto` = 7 caracteres hexadecimales del commit. Ejemplo:
`SV_PHARMA_SALES_V1A2B3C4`. El prefijo `V` evita que el identificador empiece por un dígito.

## Contrato de `ops/semantic_view_registry.py`

```python
def deploy_version(
    *, base_name: str, ddl_template: str, commit_sha: str, is_candidate: bool
) -> str:
    """Crea el objeto <base_name>_V<sha_corto> con CREATE OR ALTER SEMANTIC VIEW,
    inserta una fila en SEMANTIC_VIEW_VERSIONS y devuelve el OBJECT_NAME creado.
    No toca SEMANTIC_VIEW_ACTIVE."""

def activate_version(*, base_name: str, commit_sha: str, updated_by: str) -> None:
    """Busca en SEMANTIC_VIEW_VERSIONS la fila (base_name, commit_sha) mas reciente
    con IS_CANDIDATE = FALSE. Si el objeto fisico (OBJECT_NAME) ya no existe (purgado
    por retencion), lo recrea con su DDL_TEXT. Actualiza SEMANTIC_VIEW_ACTIVE
    (MERGE por BASE_NAME)."""

def resolve_active(*, base_name: str) -> str:
    """Devuelve ACTIVE_OBJECT_NAME para base_name. Usada por cortex_analyst.py
    cuando no hay override explicito de SNOWFLAKE_SEMANTIC_VIEW."""

def cleanup_old_versions(*, base_name: str, keep_last: int = 5) -> list[str]:
    """Hace DROP SEMANTIC VIEW de las versiones de produccion (IS_CANDIDATE = FALSE)
    mas antiguas que las `keep_last` mas recientes. Nunca borra la version activa.
    Devuelve los OBJECT_NAME eliminados. Las filas de SEMANTIC_VIEW_VERSIONS NO se
    borran (el DDL_TEXT se conserva para poder recrear la version si hace falta)."""
```

## Cambio de contrato en `cortex_analyst.py`

`generate_sql()` resuelve la semantic view a consultar con esta precedencia (ninguna rompe el
comportamiento actual en desarrollo/tests):

1. `SNOWFLAKE_SEMANTIC_VIEW` en el entorno, si está definida (comportamiento actual, sin cambios;
   lo usan `pr-checks.yml` para apuntar al objeto candidato y los tests locales).
2. Si no está definida: `ops.semantic_view_registry.resolve_active(base_name="SV_PHARMA_SALES")`.
3. Si la consulta anterior no devuelve fila (tabla vacía, p. ej. entorno recién creado):
   `DEFAULT_SEMANTIC_VIEW` (constante ya existente, sin cambios).

## Ejemplos de consulta (sin Git, FR-016)

**Versiones disponibles de una semantic view:**

```sql
SELECT VERSION_ID, OBJECT_NAME, COMMIT_SHA, IS_CANDIDATE, DEPLOYED_AT
FROM SEMANTIC_VIEW_VERSIONS
WHERE BASE_NAME = 'SV_PHARMA_SALES' AND IS_CANDIDATE = FALSE
ORDER BY DEPLOYED_AT DESC;
```

**Cuál está activa ahora:**

```sql
SELECT ACTIVE_OBJECT_NAME, ACTIVE_COMMIT_SHA, UPDATED_AT, UPDATED_BY
FROM SEMANTIC_VIEW_ACTIVE
WHERE BASE_NAME = 'SV_PHARMA_SALES';
```

**Objetos físicos realmente existentes (para saber si hace falta recrear al reactivar):**

```sql
SHOW SEMANTIC VIEWS LIKE 'SV_PHARMA_SALES_V%' IN SCHEMA CICD_DEMO.DATA;
```
