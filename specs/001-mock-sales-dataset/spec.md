# Feature Specification: Dataset mock de ventas farma para el agente conversacional

**Feature Branch**: `001-mock-sales-dataset`

**Created**: 2026-08-31

**Status**: Draft

**Input**: User description: "Crear unas tablas muy simples con datos mock para consultar, ambientadas en una compañía farmacéutica tipo Boehringer Ingelheim. Debe ser muy simple pero con histórico suficiente y variables para poder hacer varios filtros, de cara a construir ejemplos de consulta con un agente conversacional."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Preguntar por cifras filtradas por dimensión (Priority: P1)

Quien presenta la demo escribe una pregunta en lenguaje natural del tipo "¿cuánto vendimos de
Respiratory en España en 2025?" y obtiene una cifra concreta. Para que esto funcione debe existir
un conjunto de datos de negocio con métricas agregables y suficientes atributos descriptivos como
para acotar la pregunta por producto, área terapéutica, unidad de negocio, país, región y canal.

**Why this priority**: sin este dataset no hay nada que preguntar. Es el cimiento de toda la demo;
cualquier otra funcionalidad (semantic view, agente, telemetría) depende de él.

**Independent Test**: se puede validar de forma aislada ejecutando consultas de agregación
directamente sobre los datos y comprobando que devuelven un único valor numérico no nulo para
cada combinación de filtros del catálogo de preguntas de referencia.

**Acceptance Scenarios**:

1. **Given** el dataset cargado, **When** se agrega la métrica de ventas netas filtrando por un
   país y un año concretos, **Then** el resultado es un número positivo, no nulo y no cero.
2. **Given** el dataset cargado, **When** se agrupa por área terapéutica sin filtros, **Then** se
   obtiene una fila por cada área terapéutica del catálogo y ninguna categoría vacía o nula.
3. **Given** el dataset cargado, **When** se filtra por una combinación válida de unidad de
   negocio y canal, **Then** existe al menos una fila de resultado.
4. **Given** el dataset cargado, **When** se suman las ventas netas de todas las filas, **Then**
   el total coincide con la suma de ventas brutas menos la suma de descuentos.

---

### User Story 2 - Comparar evolución temporal (Priority: P2)

Quien presenta la demo pregunta por tendencias: "compara 2024 con 2025", "evolución mensual de la
marca X", "¿qué área terapéutica creció más el último año?". Esto exige que el dataset tenga
profundidad histórica suficiente y grano mensual continuo.

**Why this priority**: las preguntas temporales son las que mejor lucen en una demostración en
directo y las que más estresan el modelo semántico, pero la demo ya aporta valor con US1.

**Independent Test**: se valida comprobando que existen exactamente 36 meses consecutivos sin
huecos y que una comparativa interanual sobre cualquier dimensión devuelve dos valores comparables.

**Acceptance Scenarios**:

1. **Given** el dataset cargado, **When** se listan los meses distintos presentes, **Then** hay 36
   meses consecutivos sin huecos.
2. **Given** el dataset cargado, **When** se agrega por año, **Then** los tres años tienen datos y
   ninguno está vacío.
3. **Given** el dataset cargado, **When** se calcula la variación interanual de una marca concreta,
   **Then** el cálculo es posible porque esa marca tiene datos en ambos años.

---

### User Story 3 - Regenerar el dataset de forma reproducible (Priority: P3)

Una persona del equipo clona el repositorio, o el pipeline despliega en un entorno limpio, y
obtiene exactamente el mismo dataset que el resto: mismas filas y mismas cifras.

**Why this priority**: es requisito del Principio V de la constitución y condición necesaria para
que los tests del agente tengan resultados esperados estables. No bloquea la construcción inicial,
pero sí el despliegue automatizado.

**Independent Test**: se valida ejecutando la carga dos veces seguidas y comprobando que el número
de filas y los agregados totales son idénticos.

**Acceptance Scenarios**:

1. **Given** un entorno sin datos, **When** se ejecuta la carga del dataset, **Then** se obtiene el
   volumen de filas esperado.
2. **Given** un entorno con el dataset ya cargado, **When** se vuelve a ejecutar la carga, **Then**
   el resultado es idéntico al anterior y no se duplican filas.

---

### Edge Cases

- **Combinaciones sin datos**: si el agente filtra por una combinación inexistente (p. ej. una marca
  en un país donde no se vende), la consulta devuelve cero filas. La respuesta esperada es "no hay
  datos", nunca un error ni un número inventado.
- **Categorías no aplicables entre unidades de negocio**: los valores de canal son comunes a Human
  Pharma y Animal Health, con una lectura equivalente en cada una (el canal hospitalario representa
  la clínica veterinaria en Animal Health). No existen canales exclusivos de una unidad.
- **Descuento superior a ventas brutas**: no puede darse; el descuento siempre es una fracción
  acotada de las ventas brutas, de forma que las ventas netas nunca son negativas.
- **Valores nulos**: ninguna columna del dataset admite nulos.
- **Preguntas fuera del rango histórico**: preguntas sobre años anteriores a 2023 o posteriores a
  2025 devuelven cero filas, no un error.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: El dataset MUST estar compuesto por exactamente tres entidades: un catálogo de
  productos, un catálogo de países y un registro de ventas. No se añaden más entidades.
- **FR-002**: El catálogo de productos MUST contener 12 productos ficticios, cada uno con marca,
  área terapéutica, unidad de negocio y año de lanzamiento.
- **FR-003**: Las áreas terapéuticas MUST ser un conjunto cerrado de cinco valores representativos
  del sector (incluyendo al menos una propia de salud animal).
- **FR-004**: La unidad de negocio MUST tener exactamente dos valores: Human Pharma y Animal Health,
  con al menos dos productos en cada una.
- **FR-005**: El año de lanzamiento de todo producto MUST ser anterior al inicio del histórico, de
  modo que todos los productos tengan datos en todos los meses.
- **FR-006**: El catálogo de países MUST contener 10 países ficticiamente atribuidos, cada uno con
  nombre y región.
- **FR-007**: Las regiones MUST ser un conjunto cerrado de cuatro valores, con al menos dos países
  en cada una.
- **FR-008**: El registro de ventas MUST tener grano mensual por producto, país y canal.
- **FR-009**: El canal MUST ser un conjunto cerrado de tres valores.
- **FR-010**: El histórico MUST cubrir 36 meses consecutivos completos, de enero de 2023 a
  diciembre de 2025, sin huecos.
- **FR-011**: El registro de ventas MUST contener una fila por cada combinación de mes, producto,
  país y canal, resultando en 12.960 filas.
- **FR-012**: Cada fila de ventas MUST incluir unidades vendidas, ventas brutas y descuento, todos
  ellos valores positivos o cero.
- **FR-013**: Las ventas netas MUST ser derivables como ventas brutas menos descuento y MUST ser
  siempre mayores que cero.
- **FR-014**: El descuento MUST representar entre el 0% y el 40% de las ventas brutas de la fila.
- **FR-015**: Los importes MUST expresarse en una única moneda (euros) en todo el dataset.
- **FR-016**: Las cifras MUST presentar variación mes a mes y diferencias apreciables entre
  productos, países y canales, de forma que las preguntas de ranking y tendencia produzcan
  resultados distinguibles y no empates.
- **FR-017**: Los datos MUST ser deterministas: dos cargas independientes producen exactamente los
  mismos valores.
- **FR-018**: La carga del dataset MUST ser idempotente: repetirla no duplica ni altera filas.
- **FR-019**: Todo el contenido MUST ser ficticio. El dataset MUST NOT contener cifras reales de
  ninguna compañía, ni datos personales, ni información de pacientes.
- **FR-020**: Toda fila de ventas MUST referenciar un producto y un país existentes en sus
  respectivos catálogos; no puede haber referencias huérfanas.
- **FR-021**: La definición del dataset y su carga MUST residir en el repositorio y versionarse en
  Git, sin pasos manuales.

### Key Entities

- **Producto**: cada uno de los medicamentos ficticios comercializados. Atributos: identificador,
  marca, área terapéutica, unidad de negocio, año de lanzamiento. 12 instancias.
- **País**: mercado donde se vende. Atributos: código, nombre, región. 10 instancias.
- **Venta mensual**: hecho de negocio con grano mes × producto × país × canal. Atributos: mes,
  referencia a producto, referencia a país, canal, unidades vendidas, ventas brutas, descuento.
  12.960 instancias. Se relaciona con Producto y con País.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: El dataset ofrece al menos 6 atributos distintos utilizables como filtro (marca, área
  terapéutica, unidad de negocio, país, región, canal) más el eje temporal.
- **SC-002**: El registro de ventas contiene exactamente 12.960 filas y 36 meses distintos.
- **SC-003**: Un catálogo de al menos 10 preguntas de referencia en lenguaje natural, que cubra
  agregación simple, filtrado multidimensional, ranking, comparativa interanual y evolución
  temporal, se puede responder íntegramente con este dataset.
- **SC-004**: Dos cargas consecutivas del dataset producen idéntico número de filas e idénticos
  totales agregados.
- **SC-005**: El modelo de datos completo se explica a una audiencia en menos de 2 minutos: tres
  entidades y siete atributos de filtro.
- **SC-006**: Ninguna columna contiene valores nulos y ninguna venta neta es negativa.

## Assumptions

- La compañía y sus productos son **ficticios**; se usa el sector farmacéutico y la estructura
  Human Pharma / Animal Health como ambientación temática inspirada en el caso de uso mencionado,
  sin emplear datos ni cifras reales de ninguna organización.
- El histórico es un rango **fijo** (2023-01 a 2025-12), no relativo a la fecha actual, para que los
  resultados esperados de los tests del agente permanezcan estables en el tiempo.
- Se descarta una entidad de calendario dedicada: el eje temporal se deriva del propio mes de la
  venta.
- Se descartan entidades de cliente, paciente o prescriptor, para evitar cualquier apariencia de
  dato sensible y porque no aportan filtros adicionales relevantes a la demo.
- Se usa moneda única para no introducir conversiones de divisa, que distraerían del objetivo
  pedagógico.
- Los valores de canal se interpretan de forma equivalente en ambas unidades de negocio; no se
  modela un catálogo de canales por unidad.
- Queda **fuera de alcance** de esta feature: cualquier entidad adicional de negocio (inventario,
  campañas, ensayos clínicos), la definición del modelo semántico expuesto al agente, el propio
  agente conversacional y la telemetría. Esta feature entrega únicamente los datos.
- Se asume que la infraestructura de base de datos, esquemas y permisos ya existe (creada
  previamente fuera de esta feature) y que el dataset se aloja en el esquema de datos de negocio
  ya provisto.
