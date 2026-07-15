# Plan de Actualización — Módulo Ventas (Dashboard, Venta Cruzada, Cartera 360)

> **Fecha:** 2026-07-14
> **Estado:** Propuesta (requiere auditoría previa `docs/auditoria/34_actualizacion_modulo_ventas.md`)
> **Alcance:** `backend/app/api/routes/sales.py` + `cartera360.py` (prefijos `/analytics/ventas`, `/analytics/ventas/cartera360`, `/analytics/ventas/cross-selling`), `frontend/src/pages/DashboardVentas.tsx`, `VentasCrossSelling.tsx`, `VentasCartera360.tsx`. Modelos reutilizados: `churn_rf`, `segmentation` (RFM K=4), `association` (contrato v0.2.0, expone `score`, NO `lift`).

## 0. Diagnóstico preliminar (verificado en código)

| # | Hallazgo | Evidencia | Severidad |
|---|---|---|---|
| V-1 | **Selector de sucursal muerto:** `DashboardVentas.tsx` declara `const [sucursal, setSucursal] = useState(...)` (línea 53) pero `setSucursal` no se invoca en ningún punto y `sucursal` solo se interpola en el subtítulo (línea 69). Para gerencia/admin siempre muestra "Consolidado Global" y ningún hook (`useSalesGoals`, `useChurnRisk`, `useRecommendations`, `useCustomerSegment` — líneas 47-50) recibe la sucursal. UI que aparenta un filtro que no existe. | `DashboardVentas.tsx:47-69` | Alta |
| V-2 | **RLS de sucursal solo en `/goals`:** en `sales.py`, `get_sales_goals` aplica `sucursal_ventas` (Depends), pero `/churn-risk` y `/recommendations` reciben `cliente_id` libre **sin verificar que el cliente pertenezca a la cartera/sucursal del vendedor autenticado**. Un vendedor puede consultar churn y recomendaciones de clientes ajenos. Confirmar alcance en auditoría (¿es decisión de producto o fuga de RLS?). | `sales.py:41-55` | Alta (potencial) |
| V-3 | **Cobertura de filtros:** el dashboard no tiene barra de filtros global (período, sucursal) a diferencia de Bodega/Gerencia; los KPIs de `/goals` son "del período vigente" sin que el vendedor pueda ver meses anteriores. | `DashboardVentas.tsx` | Media |
| V-4 | **Puntos ya auditados a re-verificar, no rehacer:** Venta Cruzada tiene su auditoría (25) con telemetría `recomendaciones_eventos` y reglas RN-CS1/CS2; verificar que la tasa de conversión de `GET /cross-selling/kpis` divide eventos correctamente (aceptados / mostrados, no sobre total) y que el autocompletar `/productos` respeta catálogo vigente (SCD2 `es_vigente`). | auditoría 25 | A verificar |

## 1. Fase 0 — Auditoría de caza de bugs (entregable: `34_actualizacion_modulo_ventas.md`)

1. **RLS por rol (prioritario):** con un usuario `ventas` real (seed `edw/08`), intentar: consultar churn/recomendaciones/segmento de un cliente de otro vendedor, y `cartera360` de otra cartera. Documentar qué endpoints filtran por `id_vendedor_origen`/sucursal y cuáles no. Es la misma clase de control que Bodega ya tiene (`resolve_sucursal_filter(allow_override=False)`).
2. **Segmentación RFM:** verificar que `cluster_to_segment` del sidecar `.meta.json` se usa para nombrar segmentos (no un mapeo hardcodeado en frontend) y que los 4 segmentos mostrados coinciden con K=4 del modelo.
3. **Churn:** validar el umbral de `riesgo_alto` (¿configurable o hardcodeado?) y reconciliar 10 clientes contra el EDW a mano (recencia/frecuencia reales vs probabilidad mostrada, sanity check).
4. **Cartera 360:** los 4 endpoints (`lista-trabajo`, `detalle`, `gestion`, `tasa-recuperacion`) son recientes y sin auditoría propia; revisar grano de `fact_cobros_cxc`, idempotencia de `POST /gestion` (doble click = doble registro?), y RLS.
5. **Contrato `score` vs `lift`:** grep en frontend por `lift` residual (el contrato v0.2.0 lo eliminó; cualquier lectura de `lift` muestra `undefined`).

## 2. Fase 1 — Correcciones

1. **V-1:** o se implementa el selector de sucursal de verdad (solo gerencia/admin; catálogo de `/gerencia/sucursales`; propagado a los 4 hooks y sus `queryKey`) o se elimina el estado muerto y el subtítulo dice la sucursal real del RLS. No dejar UI que finge filtrar.
2. **V-2:** si la auditoría confirma la fuga: `churn-risk`, `recommendations` y `clientes/{id}/segmento` validan pertenencia del cliente a la cartera del vendedor (`CurrentUserDep` + repository); gerencia/admin sin restricción. Excepción de dominio `ForbiddenError` (no `HTTPException`).
3. **V-3:** selector de período (mes/año) en el dashboard de metas del vendedor, reutilizando `GET /gerencia/goals/periods` que ya existe.
4. **V-4:** correcciones puntuales que salgan de la re-verificación de Venta Cruzada (sin rediseño — el módulo tiene auditoría 25 reciente).

## 3. Fase 2 — Mejoras de valor

1. **Churn accionable:** lista de clientes en riesgo de la cartera propia ordenada por (probabilidad × venta histórica), no consulta uno-a-uno por ID — hoy el vendedor tiene que adivinar a quién consultar.
2. Integrar la señal de churn en la lista de trabajo de Cartera 360 (cliente moroso + riesgo de fuga = prioridad máxima) — cruce de datos que ya existen, sin ML nuevo.
3. Telemetría de venta cruzada: panel de KPIs RN-CS2 para gerencia (hoy solo lo ve ventas).

## 4. Validación

- `pytest` unit + integration; tests nuevos de RLS por rol (los 3 roles consultando cliente ajeno → 403).
- `test_inference.py` intacto (no se toca `inference.py` salvo hallazgo de contrato).
- oxlint + verificación manual con usuario seed de ventas.

**Reglas transversales:** routers thin; excepciones de dominio; degradación con gracia intacta en `prediction_service`; contrato `association` v0.2.0 (`score`) no se renegocia; actualizar auditoría 34 y `02_reglas_negocio_validadas.md`.
