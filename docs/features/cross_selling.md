# Especificación de Dominio: Motor de Recomendación (Cross-Selling)

## 1. Problema que Resuelve

Maximizar el ticket promedio de compra por cliente durante la operación de ventas en sucursales, otorgando a los vendedores una herramienta proactiva que les sugiera "qué más" debería comprar el cliente basándose en su carrito actual y la inteligencia colectiva del negocio.

## 2. Definición del Modelo y Objetivos

- **Objetivo Predictivo:** Sugerir `N` artículos relacionados que un cliente tiene altas probabilidades de adquirir, dado un conjunto de `Y` artículos ya seleccionados en su pre-factura o en su historial de compras.
- **Consumidores del Modelo:** Operadores de Ventas (Pantalla de Facturación).
- **Algoritmo Base:** Algoritmos de Asociación Comercial (Apriori o FP-Growth para Market Basket Analysis).

## 3. Arquitectura del Flujo de Datos

### 3.1 Entrada (Fuentes de Datos)

La información base proviene del EDW PostgreSQL:

- **`Fact_Ventas_Detalle` / `Kardex`**: Agrupación de tickets y números de factura con sus respectivos ítems comprados.
- **`Dim_Producto`**: Metadatos de catálogo (Clase, Familia) para filtrar recomendaciones semánticas absurdas o artículos inactivos.

### 3.2 Proceso ETL y Transformación (`ml/src/data/make_dataset.py`)

Variables (Features) a construir para las Reglas de Asociación:

- **Transaccionalización de Canastas**: Construcción de arrays (o agrupaciones) del tipo `transaction_id = Num_Factura + Sucursal` -> `Items: [A, B, C]`.
- **Filtro de Ruido**: Eliminación de tickets con 1 solo ítem o tickets institucionales atípicos (empresas comprando 1000 items variados).

### 3.3 Entrenamiento y Salida (Output)

- **Frecuencia de Entrenamiento**: Retraining automatizado semanalmente (a captura de más asociaciones).
- **Output (Reglas de Asociación)**:
  - Generación del DataFrame asociativo mediante las métricas:
  - _Soporte_ (Support): Popularidad de la combinación.
  - _Confianza_ (Confidence): Fiabilidad condicional.
  - _Levantamiento_ (Lift): Ratio de sorpresa/influencia (Debe ser > 1 para que tenga impacto).
- **Artefactos Resultantes**: Tabla de reglas procesada, exportada al EDW o archivada en un dataset optimizado (`recommendation_rules.pkl` o volcada a Postgres).

## 4. Dependencias del Backend e Integración (API FastAPI)

El servicio requerirá exponer una inferencia muy reactiva.

| Flujo Funcional           | Detalle                                                                                                                                                    |
| ------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Petición del Vendedor** | El vendedor carga el Artículo "X" en su consola web de caja/facturador.                                                                                    |
| **API Inferencia**        | Frontend solicita asíncronamente: `GET /api/v1/recommendations/cross-sell?cart=ArtX`.                                                                      |
| **Búsqueda Backend**      | El backend escanea el ruleset (Market Basket rules) pre-entrenado filtrando `antecedents = ArtX`, ordenado por el métrico Lift descendente. Retorna Top 3. |
| **Respuesta UI**          | Interfaz muestra una tarjeta emergente _"Los clientes que llevan X, también compran Y y Z"_.                                                               |

## 5. Prioridad y Consideraciones Extras

- **Prioridad Funcional**: ALTA (Incremento de Ventas).
- **Control de Inventario**: El backend **debe** verificar mediante un JOIN dinámico a la bodega del vendedor que los artículos sugeridos TENGAN stock antes de mostrar la recomendación (cruce con `Fact_Inventario_Snapshot`). No recomendar lo que no existe en tienda.
