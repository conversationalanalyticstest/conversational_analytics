# Quickstart: validar el dataset mock

**Feature**: `001-mock-sales-dataset` | **Fecha**: 2026-08-31 | **Fase**: 1

Cómo desplegar el dataset y comprobar que cumple su contrato. Es la guía que se usará en la
demo y la que replica el pipeline de CI.

## Prerrequisitos

1. `001_bootstrap.sql` ya ejecutado en la cuenta (rol, base de datos, schemas, grants).
2. Rol `CICD_DEMO_ROLE` concedido a tu usuario (`snowflake/manual/grant_user.sql`).
3. `.env` relleno a partir de `.env.example`. La autenticación va por **PAT**
   (Programmatic Access Token), no por contraseña:
   ```
   SNOWFLAKE_ACCOUNT, SNOWFLAKE_USER, SNOWFLAKE_PAT,
   SNOWFLAKE_ROLE=CICD_DEMO_ROLE, SNOWFLAKE_WAREHOUSE=COMPUTE_WH,
   SNOWFLAKE_DATABASE=CICD_DEMO, SNOWFLAKE_SCHEMA=DATA
   ```
   El token se crea en Snowsight (*Settings → Authentication → Programmatic access tokens*)
   o por SQL, restringido al rol de la demo:
   ```sql
   ALTER USER <tu_usuario> ADD PROGRAMMATIC ACCESS TOKEN cicd_demo_token
     ROLE_RESTRICTION = 'CICD_DEMO_ROLE'
     DAYS_TO_EXPIRY = 90;
   ```
   Snowflake muestra el valor **una sola vez**.
4. Conexión de Snowflake CLI registrada, también con PAT. Guarda el token en `pat.txt` en la
   raíz del repositorio (está en `.gitignore`) y regístrala apuntando a ese fichero:
   ```powershell
   snow connection add --connection-name cicd_demo `
     --authenticator PROGRAMMATIC_ACCESS_TOKEN `
     --token-file-path pat.txt `
     --account <organizacion>-<cuenta> `
     --user <tu_usuario> `
     --role CICD_DEMO_ROLE `
     --warehouse COMPUTE_WH `
     --database CICD_DEMO `
     --schema DATA
   snow connection test --connection cicd_demo
   ```
   La ruta de `pat.txt` se resuelve **relativa al directorio desde el que lanzas `snow`**, así
   que ejecuta siempre los comandos desde la raíz del repositorio.

   > ⚠️ **`pat.txt` contiene un secreto en texto plano.** Es el **mismo** token que
   > `SNOWFLAKE_PAT` en `.env`: la CLI de Snowflake no lee `.env`, de ahí la duplicación. Ambos
   > ficheros están en `.gitignore` y **nunca** deben commitearse ni compartirse por chat.
   > **Al rotar el PAT hay que actualizar los dos a la vez**, o los tests y el despliegue
   > dejarán de coincidir. La desviación respecto al Principio V está justificada en
   > [plan.md](plan.md#complexity-tracking).
5. Dependencias instaladas: `poetry install`.

## Desplegar

```powershell
snow sql --connection cicd_demo -f snowflake/002_tables.sql
snow sql --connection cicd_demo -f snowflake/003_seed.sql
```

Ambos scripts son idempotentes: ejecutarlos dos veces deja el mismo resultado.

## Validar

```powershell
poetry run pytest tests/test_dataset.py -v
```

Todos los tests deben pasar. Los que escriben en la base de datos (recarga para comprobar
idempotencia) están marcados y se excluyen así:

```powershell
poetry run pytest tests/test_dataset.py -v -m "not writes_db"
```

## Comprobación manual rápida

Tres consultas que confirman de un vistazo que el dataset está bien cargado.

```sql
-- 1. Volumen y rejilla temporal -> 12960 | 36 | 2023-01-01 | 2025-12-01
SELECT COUNT(*), COUNT(DISTINCT SALE_MONTH), MIN(SALE_MONTH), MAX(SALE_MONTH)
FROM CICD_DEMO.DATA.FACT_SALES;

-- 2. Ventas netas por region y anio -> 4 regiones x 3 anios, todas > 0
SELECT c.REGION, YEAR(f.SALE_MONTH) AS ANIO,
       SUM(f.GROSS_SALES_EUR - f.DISCOUNT_EUR) AS NET_SALES_EUR
FROM CICD_DEMO.DATA.FACT_SALES f
JOIN CICD_DEMO.DATA.DIM_COUNTRY c ON c.COUNTRY_CODE = f.COUNTRY_CODE
GROUP BY 1, 2
ORDER BY 1, 2;

-- 3. Top 5 marcas por ventas netas -> 5 filas sin empates
SELECT p.BRAND, SUM(f.GROSS_SALES_EUR - f.DISCOUNT_EUR) AS NET_SALES_EUR
FROM CICD_DEMO.DATA.FACT_SALES f
JOIN CICD_DEMO.DATA.DIM_PRODUCT p ON p.PRODUCT_ID = f.PRODUCT_ID
GROUP BY 1
ORDER BY 2 DESC
LIMIT 5;
```

## Resultados esperados

| Comprobación | Resultado |
|---|---|
| Filas en `FACT_SALES` | 12.960 |
| Meses distintos | 36, de `2023-01-01` a `2025-12-01` |
| Filas en `DIM_PRODUCT` / `DIM_COUNTRY` | 12 / 10 |
| Nulos | Ninguno |
| Ventas netas negativas o cero | Ninguna |
| Segunda ejecución del seed | Recuentos y sumas idénticos |
| Suite `pytest` | Todos los tests en verde |

## Si algo falla

| Síntoma | Causa probable |
|---|---|
| `Programmatic access token is invalid` | El PAT se está pasando en `password`. Con `authenticator=PROGRAMMATIC_ACCESS_TOKEN` el conector lo lee de `token` |
| `Object does not exist` | Falta ejecutar `002_tables.sql`, o el rol/schema del `.env` no es el correcto |
| Recuento distinto de 12.960 | El seed se ejecutó a medias; volver a lanzar `003_seed.sql` completo |
| Los tests no conectan | `.env` incompleto, o `SNOWFLAKE_ROLE` distinto de `CICD_DEMO_ROLE` |
| Cifras distintas entre dos entornos | Bug de determinismo: hay aleatoriedad o dependencia de `CURRENT_DATE` en el SQL |

## Referencias

- Esquema y fórmula: [data-model.md](data-model.md)
- Garantías y tests: [contracts/dataset-contract.md](contracts/dataset-contract.md)
- Preguntas de referencia: [contracts/reference-questions.md](contracts/reference-questions.md)
