# Auditoría 32 — Validación de datos para el módulo Ventas: Cartera de Clientes 360

- **Fecha:** 2026-07-14
- **Alcance:** `edw.fact_ventas_detalle`, `edw.dim_vendedor`, `edw.dim_cliente`, `public.cliente_lookup`,
  y el código existente que ya sirve churn/RFM/cross-selling por cliente
  (`backend/app/services/prediction_service.py`, `backend/app/repositories/prediction_repository.py`,
  `backend/app/repositories/goal_repository.py`, `backend/app/repositories/recommendation_event_repository.py`).
  Validación previa al diseño del módulo propuesto en
  `docs/features/propuesta_nuevos_modulos_roi.md` §4 (Cartera de Clientes 360, Ventas).
- **Método:** `SELECT` puro contra el EDW y revisión estática del backend. **No se ejecutó
  ninguna escritura contra Producción ni contra el EDW.**

## Hallazgos

### 🔴 Alta — H1: la cartera de un `codven` puede tener decenas de miles de clientes — inviable enriquecer con los 3 modelos ML por cliente en cada request

- **Evidencia:**
  ```sql
  SELECT v.codven, COUNT(DISTINCT f.cliente_sk) AS num_clientes
  FROM edw.fact_ventas_detalle f
  JOIN edw.dim_vendedor v ON f.vendedor_sk = v.vendedor_sk
  JOIN edw.dim_estado_documento ed ON f.estado_documento_sk = ed.estado_documento_sk
  WHERE ed.estado_documento_sk <> -1 AND v.codven <> '-1'
  GROUP BY v.codven ORDER BY num_clientes DESC;
  -- VEN01 (ALMACEN EL REY): 30,977 clientes; VEN13: 10,787; VEN03: 10,084
  -- 20 códigos de vendedor con cartera; promedio 3,062 clientes, máximo 30,977
  ```
  `edw.dim_vendedor.nombre_vendedor` confirma que los `codven` con carteras más grandes son
  códigos de **sucursal/almacén** ("ALMACEN EL REY", "ALMACEN LOS CHASQUIS", "ALMACEN ATAHUALPA"),
  no vendedores individuales — consistente con la limitación ya documentada en la regla de
  negocio 10 (`dim_vendedor` no tiene sucursal propia y mezcla grano vendedor con grano sucursal
  en algunos códigos, auditoría 19).
- **Impacto:** `PredictionService.get_churn_risk`/`get_customer_segment`/`get_product_recommendations`
  hacen ≥1 consulta SQL (algunas con inferencia de modelo `.pkl`) por cliente. Recorrer una
  cartera de 30,977 clientes en cada carga de la "lista de trabajo diaria" es inviable en tiempo
  de respuesta HTTP (N+1 sobre miles de clientes, sin ningún cacheo hoy).
- **Riesgos:** implementar la lista enriqueciendo el 100% de la cartera con los 3 modelos
  produciría timeouts o un endpoint inutilizable para los vendedores con cartera grande.
- **Recomendación:** two-stage, mismo patrón ya usado en Bodega (`BODEGA_TOP_ARTICULOS_PREDICCION`,
  auditoría 24): (1) una sola consulta SQL agregada calcula recency/frequency/valor histórico
  para **toda** la cartera y prioriza con estadística pura (barato, sin modelos); (2) solo el
  **Top N** (`VENTAS360_TOP_N_ENRIQUECER`, ej. 30) de esa lista se enriquece con
  churn/RFM/cross-sell vía los servicios existentes. El resto de la cartera queda visible sin
  enriquecimiento ML o paginada aparte, nunca recorrida entera con inferencia de modelo.

### 🟢 Informativo — H2: no existe una consulta previa de "clientes de un vendedor"; se construye siguiendo el patrón ya validado

- **Evidencia:** `goal_repository.py` ya usa el join `edw.dim_vendedor v ON f.vendedor_sk = v.vendedor_sk`
  filtrado por `v.codven = :vendedor` (grano vendedor validado en auditoría 19). No hay una
  consulta existente de "distinct clientes por vendedor" — se construye con el mismo patrón:
  `JOIN dim_vendedor ON codven = :vendedor`, excluyendo `estado_documento_sk = -1` (documentos
  anulados, regla de negocio 1).
- **Recomendación:** ninguna acción bloqueante; usar el patrón ya validado.

### 🟢 Informativo — H3: reutilización directa de los 3 modelos ya servidos, sin duplicar SQL

- **Evidencia:** `PredictionService.get_churn_risk(cliente_id)`, `get_customer_segment(cliente_id)`,
  `get_product_recommendations(cliente_id)` ya existen y devuelven exactamente lo que pide la
  propuesta §4.2 (riesgo de fuga, segmento RFM, productos recomendados). Cada uno degrada
  gracefully (try/except, log + default) si un cliente no tiene suficiente historial.
- **Recomendación:** el nuevo servicio del módulo 360 debe **llamar** estos métodos (inyectando
  `PredictionService`), nunca reimplementar sus queries — evita duplicar lógica y mantiene un
  solo punto de verdad si los modelos se reentrenan.

### 🟡 Media — H4: `public.cliente_lookup` para el rol `ventas` es una extensión de un precedente existente, no un mecanismo nuevo

- **Evidencia:** `catalog_repository.search_clientes()` (usado por
  `GET /analytics/ventas/cross-selling/clientes`, ya accesible a `ventas`) ya une
  `public.cliente_lookup` y devuelve `nombre_cliente` real a un usuario con rol `ventas`. La
  "lista de trabajo diaria" mostrará nombres reales de **toda la cartera propia** del vendedor
  (no solo de una búsqueda puntual) — mismo canal autorizado (regla de negocio 8), pero un
  consumo más amplio que el precedente actual.
- **Riesgos:** ninguno adicional a los ya aceptados para `ventas` en el módulo de búsqueda,
  siempre que el filtro `WHERE codven = :vendedor_propio` (nunca `sucursal` ni "todos") limite
  estrictamente los nombres devueltos a los clientes de la cartera del vendedor autenticado.
- **Recomendación:** documentar explícitamente en el código (comentario con referencia a la
  regla 8) el mismo criterio que ya usa `cartera_repository.get_ranking_cobranza`.

### 🟢 Informativo — H5: detección de caída de frecuencia es 100% estadística, sin datos nuevos

- **Evidencia:** `fact_ventas_detalle.fecha_sk` + `dim_fecha.fecha_completa` permiten calcular,
  por cliente, el intervalo promedio histórico entre compras y los días transcurridos desde la
  última — sin necesitar ningún dato adicional al ya cargado. Mismo criterio declarado en la
  propuesta §4.2 ("deriva de `fact_ventas_detalle`, sin ML nuevo").
- **Recomendación:** ninguna acción bloqueante.

## Resumen de recomendaciones por prioridad

| Prioridad | Hallazgo | Acción |
|---|---|---|
| 🔴 Alta | H1 | Diseño two-stage: triage estadístico sobre toda la cartera + enriquecimiento ML solo en el Top N (`VENTAS360_TOP_N_ENRIQUECER`) |
| 🟡 Media | H4 | Documentar en código el uso de `cliente_lookup` para `ventas` (regla de negocio 8), filtro estricto por `codven` propio |
| 🟢 Info | H2, H3, H5 | Sin acción bloqueante — reutilizar patrones/servicios ya validados |

**Veredicto de viabilidad:** 🟢 viable, sin datos nuevos ni modelos nuevos, siempre que el
enriquecimiento ML se limite al Top N priorizado por estadística (H1) en vez de recorrer carteras
de hasta 31,000 clientes.
