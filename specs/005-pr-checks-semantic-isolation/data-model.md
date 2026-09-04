# Data Model: Aislar el check de PR contra una copia de la semantic view

**Feature**: [005-pr-checks-semantic-isolation](./spec.md) · **Research**: [research.md](./research.md)

## Entidad: Copia temporal de la semantic view (candidata de PR)

No es una fila en ninguna tabla: es un objeto `SEMANTIC VIEW` efímero en Snowflake, sin modelo
de datos persistente (ver D-03 y D-06 de [research.md](./research.md) — deliberadamente, para no
reintroducir la acumulación de estado que [ADR-003](../004-ci-cd-pipeline/decisions/003-simplificacion-semantic-view.md)
eliminó). Se documenta aquí como entidad conceptual porque el spec la define como "Key Entity".

| Atributo | Descripción |
|---|---|
| `object_name` | `CICD_DEMO.DATA.SV_PHARMA_SALES_PR<número>` — determinista, calculado por `candidate_object_name(pr_number)` a partir de `github.event.pull_request.number`. |
| `contenido` | Igual a `snowflake/004_semantic_view.sql` en el working tree de la PR, con el token `SV_PHARMA_SALES` sustituido por `SV_PHARMA_SALES_PR<número>` en memoria (`render_candidate_ddl`, D-01). |
| `esquema` | `CICD_DEMO.DATA` — el mismo que `SV_PHARMA_SALES` de producción; ninguna tabla física nueva ni clonada (D-04). |
| `ciclo de vida` | Creado/actualizado (`CREATE OR ALTER`) al inicio de cada ejecución del check; eliminado (`DROP SEMANTIC VIEW IF EXISTS`) al final de la misma ejecución (`if: always()`) y de nuevo cuando la PR se cierra (trigger `closed`, D-03). |
| `persistencia` | Ninguna: el nombre es derivable en cualquier momento sin consultar Snowflake ni ningún registro. |
| `relación con producción` | Ninguna: objeto físico distinto de `SV_PHARMA_SALES`; nunca se lee ni se escribe la definición de producción durante el check de una PR. |
| `relación con `DEPLOYMENTS`` | Ninguna (D-05): su creación/eliminación no genera ninguna fila. |

### Funciones que operan sobre esta entidad (`ops/pr_candidate.py`)

Ver el contrato completo en [contracts/pr-candidate-workflow.md](contracts/pr-candidate-workflow.md).

- `candidate_object_name(pr_number: str) -> str`
- `render_candidate_ddl(sql_text: str, object_name: str) -> str`
- `build_candidate(pr_number: str) -> None`
- `drop_candidate(pr_number: str) -> None`

## Sin cambios a entidades existentes

- **`Deployment`** (tabla `DEPLOYMENTS`, feature 004): sin cambios, sin filas nuevas por esta
  feature (D-05).
- **`SV_PHARMA_SALES`** (semantic view de producción, feature 002/004): sin cambios; nunca se lee
  ni se modifica durante el check de una PR.
