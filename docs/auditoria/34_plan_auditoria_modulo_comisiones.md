# Auditoría 34 — Plan de auditoría integral del módulo de Comisiones

- **Fecha:** 2026-07-14
- **Estado:** EJECUTADA (segunda pasada, con acceso real a SAP concedido por el usuario). Se completaron las Fases A.3/A.4 (integridad EDW y configuración), A.1/A.2 parcial (reconciliación contra SAP vía `SELECT`), B (matriz de tests) y C (contratos); se corrigieron los hallazgos de severidad **Alta** que no requerían una decisión de producto nueva, **incluyendo una corrección de fondo al ETL** (H-13/H-14/H-15: el pipeline descartaba datos reales de SAP -- `bienser`, `subcodcla`, `desinv` -- necesarios para que el motor de Comisiones Variables funcione como está documentado). El EDW local se recargó con los datos corregidos y se verificó end-to-end. **Toda consulta contra SAP (Producción) fue `SELECT` puro, sin excepción; toda escritura ocurrió exclusivamente contra el EDW local de desarrollo (`bi_postgres_edw`, Docker), con autorización explícita del usuario para cada operación de mayor alcance (reset de `etl_control`, recarga completa, `TRUNCATE` de la tabla duplicada por un bug del orquestador, backfill de `subclase`).**
- **Alcance:** módulo de Metas y Comisiones completo, en ambos esquemas (plano y variable):
  - Backend: `backend/app/services/commission_engine.py`, `commission_service.py`, `commission_config_service.py`, `commission_simulation_service.py`, `backend/app/repositories/goal_repository.py`, `commission_config_repository.py`, `backend/app/api/routes/goals.py`, `backend/app/schemas/commission.py`, `commission_config.py`, `backend/app/models/commission_config.py`.
  - Datos: `edw.fact_ventas_detalle`, `edw.fact_devoluciones`, `edw.fact_cobros_cxc`, `edw.dim_producto`, `edw.dim_formapago`, `edw.dim_vendedor`; `public.metas_comerciales_operativas`, `public.comision_matriz_categorias`, `public.comision_factores_credito`, `public.comision_config_vendedor`, `public.comision_liquidaciones`, `public.recomendaciones_eventos`.
  - Frontend: `frontend/src/pages/DashboardMetas.tsx`, `frontend/src/components/goals/*` (`CommissionTracker`, `CommissionConfigPanel`, `CommissionSimulationPanel`, `VendorGoalDashboard`, `GoalsConsole`, `GoalProgressGauge`, `GoalsAISummaryPanel`).
  - Origen ERP (validación): `encabezadofacturas`, `renglonesfacturas`, tablas de devoluciones, `articulos` (`ultcos`), `formapago`, `vendedores`.
- **Método:** revisión estática de código + pruebas unitarias dirigidas (pytest) + reconciliación de datos Producción (SAP) ↔ EDW ↔ API. **Contra Producción se ejecutarán exclusivamente `SELECT`** (restricción innegociable del proyecto; ninguna consulta con `INTO`, DML ni DDL). Las escrituras de prueba solo ocurren en el entorno local de desarrollo (EDW Docker), nunca en SAP.
- **Referencias previas:** auditorías 14 (hallazgo R-1), 16 (Venta Neta), 17 (liquidación), 19 (grano vendedor), 20 (decomisión goals_rf), 30 (Fase 0 comisiones variables); `docs/features/plan_integracion_comisiones_variables.md`; reglas 10 y 13 + RN-CM1..CM4 de `docs/auditoria/02_reglas_negocio_validadas.md`.

---

## 1. Objetivo

El módulo presenta **incongruencias reportadas por el usuario final** (cifras que no cuadran entre paneles y con el ERP) y una **experiencia de uso confusa** (el usuario se pierde entre metas, comisión plana, comisión variable, simulación y configuración). Esta auditoría debe:

1. Reconciliar toda cifra mostrada (venta real, meta, % cumplimiento, comisión plana, comisión variable, bonos, devoluciones) contra el ERP con `SELECT`, aislando en qué etapa nace cada diferencia (extractor → EDW → repositorio → motor → API → frontend).
2. Verificar el motor de cálculo con una matriz exhaustiva de casos (bordes incluidos).
3. Verificar consistencia de contratos backend ↔ frontend.
4. Rediseñar la UX del módulo para que cada rol entienda qué está viendo sin explicación externa.

## 2. Mapa del flujo auditado (contexto)

```
SAP (renglonesfacturas ⋈ encabezadofacturas, devoluciones, articulos.ultcos, formapago)
  → ETL (facturas_detalle_extractor.sql, devoluciones_*, formapago_extractor)
  → edw.fact_ventas_detalle / fact_devoluciones / dim_producto / dim_formapago
  → GoalRepository (venta neta, líneas comisionables, devoluciones, perfil crédito, clientes nuevos, cross-sell)
  → commission_engine (calcular_comision  |  calcular_comision_variable)  [funciones puras]
  → CommissionService (modo plana/sombra/variable, bonos en 2 pasadas, snapshot liquidación)
  → /gerencia/goals/commissions, /analytics/ventas/goals/mi-comision, /commission-simulation, /commission-config/*
  → CommissionTracker / VendorGoalDashboard / CommissionSimulationPanel / CommissionConfigPanel
```

## 3. Hipótesis de incongruencia a comprobar (H-1 … H-12)

Detectadas por lectura estática previa; cada una se confirma o descarta con evidencia en la ejecución.

| ID | Hipótesis | Dónde mirar | Severidad potencial |
|---|---|---|---|
| H-1 | **Doble definición de "venta real":** la comisión plana usa Venta Neta agregada (`get_vendor_net_sales_period` = ventas − devoluciones), mientras el motor variable suma líneas de `get_commission_lines` (solo ventas) y resta devoluciones *estimadas* con tasa promedio ponderada. Si las dos bases no reconcilian, plana y variable divergen por construcción y el usuario ve cifras "que no cuadran". | `goal_repository.py:166,246,453`; `commission_engine.py:314-319` | Alta |
| H-2 | **`descuento_aprobado` siempre `False`:** `CommissionService._calcular_variable` construye `LineaComisionable` sin pasar `descuento_aprobado`; no existe flujo/tabla de aprobación. Con 68% de líneas con descuento (auditoría 30 H5), toda línea con descuento > tope queda excluida sin vía de aprobación → comisión variable sistemáticamente subestimada. | `commission_service.py:147-154`; `commission_engine.py:217-224` | Alta |
| H-3 | **% de descuento con denominador incorrecto:** `pct_descuento = valor_descuento / subtotal_neto`. Si `subtotal_neto` ya es post-descuento, el porcentaje se infla (un descuento del 50% sobre bruto da 100% sobre neto) y dispara la salvaguarda 1 en líneas legítimas. Confirmar contra SAP qué representa cada columna. | `commission_engine.py:218`; `etl/transformers/fact_transformer.py`; `facturas_detalle_extractor.sql` | Alta |
| H-4 | **Snapshot de liquidación como efecto colateral de un GET:** `_persistir_snapshot` se ejecuta en cada consulta a `/commissions` y `/mi-comision` para períodos cerrados. Verificar idempotencia de `save_liquidacion` (¿upsert por `(anio, mes, vendedor, esquema)` o inserta duplicados?), y si un cambio posterior de configuración **reescribe** un snapshot que debía estar "congelado" (contradice salvaguarda 6). | `commission_service.py:210-222`; `commission_config_repository.save_liquidacion`; DDL de `comision_liquidaciones` | Alta |
| H-5 | **Doble pasada de bonos incompleta:** el bono de cobranza se calcula sobre `comision_post_cumplimiento` *pre-bonos*, pero la segunda pasada recalcula todo; verificar que devoluciones/piso $0 no alteren la base del bono entre pasadas (orden de operaciones §3.4 del plan vs. implementación). | `commission_service.py:174-187`; `commission_engine.py:321` | Media |
| H-6 | **`FACTOR_TASA_CERCA = 5/7` generalizado:** con tasas base distintas de 7% produce tramos "Cerca" no documentados para el usuario (p.ej. base 10% → 7.14%). Validar que gerencia lo sepa y que el frontend lo muestre; si no, es una incongruencia percibida garantizada. | `commission_engine.py:34,91-93` | Media |
| H-7 | **Nivel plana vs. nivel variable pueden diferir en pantalla:** ambos derivan de `calcular_nivel` con la misma fracción, pero la fila del tracker muestra `nivel` (plana) y `nivel_variable`; si `venta_real`/`monto_meta` llegan por caminos distintos (H-1), los niveles divergen y el usuario ve dos semáforos contradictorios. | `commission_service.py:77-100`; `CommissionTracker.tsx` | Media |
| H-8 | **Vigencias de configuración vs. retroactividad:** la simulación retroactiva y los snapshots usan la matriz/factores *vigentes hoy*; verificar si `get_matriz_as_reglas`/`get_factores_credito_as_rangos` filtran por vigencia a la fecha del período liquidado o a la fecha actual (riesgo: recalcular un mes viejo con reglas nuevas). | `commission_config_repository.py`; `commission_simulation_service.py` | Alta |
| H-9 | **Solapamiento/huecos en `comision_factores_credito` y en la matriz:** `_factor_credito` devuelve el primer rango que matchea (orden de lista) y `_resolver_regla` toma `[0]` si hay duplicados → resultados dependientes del orden de lectura. Verificar constraints UNIQUE/validaciones CRUD contra rangos solapados y reglas `(clase, subclase)` duplicadas vigentes. | `commission_engine.py:192-208`; DDL `edw/07_public_app_tables.sql`; `commission_config_service.py` | Alta |
| H-10 | **Bono cliente nuevo/reactivado y cross-sell sin tope:** `clientes_nuevos × monto_fijo` y `% sobre monto aceptado` sin límite superior; validar volúmenes reales por vendedor/mes para descartar bonos absurdos (y que `recomendaciones_eventos.aceptada` no se pueda inflar repitiendo eventos). | `commission_service.py:189-208`; `goal_repository.py:586,617` | Media |
| H-11 | **Margen bruto vs. costo del ERP:** `margen_bruto` del EDW depende de `articulos.ultcos` al momento de la carga; reconciliar una muestra de líneas contra SAP (`preuni×cantidad − ultcos×cantidad`, solo `desinv='S'`) para confirmar que la base del esquema variable coincide con el ERP y que las líneas `desinv='N'` (servicios) están correctamente marcadas `es_servicio`. | `fact_transformer.py`; regla de negocio 5; `dim_producto` | Alta |
| H-12 | **Timezone/corte de mes:** el corte "mes en curso vs. cerrado" usa `datetime.date.today()` del servidor; verificar coherencia con la fecha de las facturas del EDW (facturas del día 1 a las 00:xx asignadas al mes equivocado harían bailar la venta real del panel). | `commission_service.py:216-218,238-247` | Baja |

## 4. Fase A — Reconciliación de datos SAP ↔ EDW ↔ API (solo `SELECT`)

Regla de oro: **misma métrica, mismo recorte** (`codemp='01'`, `estado='P'`, mismo rango de fechas) en cada etapa, para aislar dónde nace la diferencia. Muestreo: 3 vendedores (alto/medio/bajo volumen) × 3 meses cerrados.

### A.1 Venta Neta por vendedor/mes (base de la comisión plana)

Contra SAP (adaptar nombres exactos desde `facturas_detalle_extractor.sql` y el extractor de devoluciones; ejecutar vía `etl/connectors/sqlany_connector.py`, solo lectura):

```sql
-- SAP: venta bruta por vendedor/mes (mismo recorte que el extractor)
SELECT e.codven, YEAR(e.fecha) AS anio, MONTH(e.fecha) AS mes,
       COUNT(DISTINCT e.numdoc) AS facturas, SUM(r.subtotal_neto_expr) AS venta
FROM renglonesfacturas r
JOIN encabezadofacturas e ON /* llaves del extractor */
WHERE e.codemp = '01' AND e.estado = 'P'
  AND e.fecha >= '2026-04-01' AND e.fecha < '2026-07-01'
GROUP BY e.codven, YEAR(e.fecha), MONTH(e.fecha);
-- (misma consulta espejo para devoluciones)
```

Contra EDW:

```sql
SELECT v.vendedor_origen, f.anio, f.mes, SUM(fv.subtotal_neto) AS venta
FROM edw.fact_ventas_detalle fv
JOIN edw.dim_fecha f ON f.fecha_sk = fv.fecha_sk
JOIN edw.dim_vendedor v ON v.vendedor_sk = fv.vendedor_sk
WHERE fv.estado_documento_sk <> -1
GROUP BY 1,2,3;
```

Contra API: `GET /gerencia/goals/commissions?anio=&mes=` y `GET /analytics/ventas/goals/mi-comision` para los mismos vendedores. **Criterio:** diferencia = 0 (o justificada línea a línea). Reconcilia H-1, H-7 y R-1 (auditoría 14) de una vez.

### A.2 Base del motor variable

- `SUM(subtotal_neto)` de `get_commission_lines` vs. `get_vendor_net_sales_period` + devoluciones del mismo período (H-1): las dos bases deben reconciliar exactamente; documentar la diferencia estructural si el diseño la acepta.
- Margen (H-11): muestra de 50 líneas, `margen_bruto` EDW vs. cálculo directo en SAP con `ultcos` (solo `desinv='S'`); % de líneas con `margen_bruto IS NULL` (re-verificar H1 de auditoría 30 tras las cargas recientes).
- Descuentos (H-3): en SAP, confirmar con `SELECT` si el subtotal del renglón es pre o post descuento; medir cuántas líneas superarían el tope 30% con cada denominador (bruto vs. neto) — la diferencia entre ambos conteos es el impacto del bug si existe.
- Plazo (RN-CM4): re-verificar distribución de `dias_plazo` en SAP `formapago` y en ventas del período (¿sigue siendo solo 0 y 30?).
- Clasificación (RN-CM2): `SELECT DISTINCT clase, subclase` en SAP `articulos` vs. `dim_producto` vigente vs. filas de `comision_matriz_categorias` → listar categorías con tráfico real **sin regla configurada** (caen al default C/5% silenciosamente: medir cuántos $ de comisión pasan por el default).

### A.3 Integridad del EDW (validaciones mínimas de toda auditoría)

Sobre las tablas tocadas, ejecutar y reportar aunque salgan limpias: pérdida de registros origen↔destino, duplicados por llave de negocio (`(num_factura, num_renglon)`), % de FKs al centinela `-1` (en especial `vendedor_sk=-1`: esas ventas **no comisionan para nadie** — cuantificar monto), fechas fuera de rango, SCD2 de `dim_producto` (más de una fila vigente por `codart`; hechos apuntando a versión no vigente en su fecha → clasificación de categoría incorrecta en meses históricos).

### A.4 Tablas de configuración y liquidaciones

```sql
-- Solapamientos en factores de crédito (H-9)
SELECT a.id, b.id FROM public.comision_factores_credito a
JOIN public.comision_factores_credito b ON a.id < b.id
WHERE a.dias_desde <= COALESCE(b.dias_hasta, 99999) AND b.dias_desde <= COALESCE(a.dias_hasta, 99999);

-- Reglas duplicadas vigentes en la matriz (H-9)
SELECT clase, subclase, COUNT(*) FROM public.comision_matriz_categorias
/* + filtro de vigencia */ GROUP BY 1,2 HAVING COUNT(*) > 1;

-- Snapshots duplicados o mutados (H-4)
SELECT anio, mes, vendedor_origen, esquema, COUNT(*), MIN(comision_total), MAX(comision_total)
FROM public.comision_liquidaciones GROUP BY 1,2,3,4
HAVING COUNT(*) > 1 OR MIN(comision_total) <> MAX(comision_total);
```

## 5. Fase B — Matriz de casos del motor de cálculo (pytest)

Ampliar `backend/tests/unit/test_commission_engine.py` + tests nuevos de `CommissionService` (repos mockeados). Todo caso debe quedar como test permanente, no verificación manual.

**Esquema plano (`calcular_comision`):** bordes exactos 0.80/0.90/1.00 (⚠ flotantes: 0.9 debe ser META, no CERCA); meta 0 y negativa → LEJOS/0; venta 0; venta negativa (devoluciones > ventas) → comisión 0, no negativa; bono solo en EXCELENTE; tasa base 0; verificación explícita del tramo CERCA con base ≠ 7% (H-6).

**Motor variable (`calcular_comision_variable`), por línea:** servicio con y sin regla S; `margen_bruto NULL` → tasa mínima sobre valor; margen negativo → base 0 (venta bajo costo no comisiona pero tampoco resta); `|subtotal| <` umbral → grupo X; grupo X explícito; descuento > tope sin/con aprobación (H-2/H-3); resolución de regla: subclase exacta > clase > comodín `*` > default; `dias_plazo` en bordes de rango (0, 30, hueco sin rango → factor 1.0, rangos solapados → documentar cuál gana).

**Motor variable, agregado:** multiplicadores por nivel (incl. `piso_lejos`); devoluciones > comisión → piso $0; devoluciones con `base_total = 0`; bonos con comisión 0; doble pasada del bono cobranza (H-5): verificar que la 2ª pasada no cambia `comision_post_cumplimiento`; lista de líneas vacía; factor_tipo_vendedor default vs. configurado.

**Servicio y modos:** `COMISION_MODO='plana'` → campos variables `None` y **ningún** snapshot; `'sombra'`/`'variable'` → snapshot solo en períodos cerrados; snapshot repetido → sin duplicados (H-4); simulación retroactiva usa config vigente al período, no la de hoy (H-8) — si el diseño decide lo contrario, documentarlo como regla explícita.

## 6. Fase C — Contratos backend ↔ frontend

- Diff campo a campo entre `schemas/commission*.py` y `frontend/src/types/goals.ts` (nombres, opcionalidad, unidades: la fracción vs. porcentaje ya causó ambigüedad en el engine — confirmar que el frontend no re-multiplique/divida por 100).
- Manejo de `null` en `comision_variable`/`nivel_variable`/`desglose_variable` en modo `plana` (¿el frontend muestra "—" o revienta/muestra 0, que el usuario lee como "no gané nada"?).
- Query keys de TanStack (`queryKeys.ts`): invalidación tras editar configuración/meta — un caché viejo tras guardar la matriz es una "incongruencia" clásica percibida por el usuario.
- Permisos (`permissions.ts` vs. RBAC real de los routers): un vendedor no debe ver la configuración de matriz ni las comisiones de otros.

## 7. Fase D — UX del frontend (el usuario se pierde)

Principios: una sola fuente por cifra, vocabulario del negocio (no del código), progresión de lo simple al detalle. Revisión heurística + prueba guiada con un usuario por rol (gerencia y ventas). Mejoras propuestas a validar:

1. **Jerarquía por rol:** el vendedor entra a *"Mi comisión del mes"* (una cifra grande, gauge de meta, mensaje de alerta de cierre) y el detalle (desglose variable, facturas post-meta) queda plegado en acordeón. Gerencia entra al tracker consolidado. Hoy `DashboardMetas` mezcla consola de metas, tracker, simulación y configuración en una sola vista.
2. **Un solo semáforo:** mientras `COMISION_MODO='sombra'`, la comisión variable se marca visualmente como **"cálculo en prueba — no es lo que se paga"** (badge + tooltip); nunca dos montos del mismo tamaño sin explicar cuál es el oficial (H-7 percibida).
3. **Explicabilidad del cálculo:** en `mi-comision`, render del `desglose_variable` como cascada legible (base → ×tipo vendedor → ×cumplimiento → −devoluciones → +bonos → total) con los factores escritos ("crédito 30 días: ×0.85"), en vez de JSON o tabla técnica. El tramo CERCA debe mostrar la tasa efectiva derivada (H-6).
4. **Configuración a prueba de gerencia:** en `CommissionConfigPanel`, validación en vivo de solapamientos/duplicados (H-9), etiquetas legibles por código de clase (RN-CM2, `nombre_clase` vacío), y aviso de qué categorías con ventas reales no tienen regla (caen al default). En la matriz de crédito, marcar los tramos sin tráfico real (decisión 4 de auditoría 30) para no sobre-prometer.
5. **Simulación con contexto:** `CommissionSimulationPanel` debe decir con qué configuración simula (vigente vs. histórica, H-8) y el período; resultado como comparación plana vs. variable por vendedor con delta destacado.
6. **Estados vacíos y de error:** sin meta configurada → "Sin meta asignada este mes, contacta a gerencia" (no $0/LEJOS a secas); períodos futuros deshabilitados; loading skeletons en vez de ceros transitorios.
7. **Glosario contextual:** tooltips para Venta Neta, margen bruto, nivel, factor estratégico — con la misma definición que usa el backend (fuente única, quizá constantes compartidas).

## 8. Fase E — Correcciones y validación

Por cada hallazgo confirmado: registrar en este reporte (evidencia, consultas literales, impacto en filas/$, riesgo), clasificar **Alta** (datos/dinero incorrecto) / **Media** (mantenibilidad, UX estructural) / **Baja** (estilo), corregir en orden de severidad y re-validar:

- Re-ejecutar la reconciliación que motivó el hallazgo (mismo `SELECT`).
- `pytest backend/tests/` completo + tests nuevos de la Fase B.
- `edw/06_verificacion.sql` si se tocó el EDW; `py_compile` si se tocó ETL.
- Verificación funcional del frontend (flujo vendedor y flujo gerencia completos).
- Actualizar `docs/auditoria/02_reglas_negocio_validadas.md` (reglas nuevas o corregidas) y `CLAUDE.md` si cambia el contrato.

## 9. Criterios de aceptación de la auditoría

1. Venta Neta y comisión de la muestra (3 vendedores × 3 meses) reconcilian SAP ↔ EDW ↔ API con diferencia 0 o justificada por escrito.
2. Las 12 hipótesis H-1..H-12 tienen veredicto con evidencia (confirmada/descartada/pendiente de validar — nunca supuesta).
3. Matriz de casos de la Fase B implementada como tests que pasan (bordes incluidos).
4. Cero escrituras a Producción (declaración explícita en el cierre del reporte).
5. `comision_liquidaciones` sin duplicados ni snapshots mutados; configuración sin solapamientos.
6. Mejoras UX 1–6 implementadas y validadas con al menos un usuario por rol.
7. Reporte cerrado con hallazgos, correcciones aplicadas y reglas de negocio actualizadas.

## 10. Orden de ejecución sugerido

| # | Actividad | Depende de |
|---|---|---|
| 1 | Fase A.3 (integridad EDW) + A.4 (config/liquidaciones) — barato y acota todo lo demás | — |
| 2 | Fase A.1/A.2 (reconciliación SAP, resuelve H-1, H-3, H-11) | 1 |
| 3 | Fase B (matriz de tests del motor, resuelve H-2, H-5, H-6, H-9) | — (paralelo a 2) |
| 4 | Fase C (contratos) + veredictos H-4, H-7, H-8, H-10, H-12 | 2, 3 |
| 5 | Correcciones Alta → Media (Fase E) | 4 |
| 6 | Fase D (rediseño UX) — después de corregir datos, para no maquillar cifras erróneas | 5 |
| 7 | Cierre: re-validación total + documentación | 6 |

> **Nota de método:** ninguna cifra se corrige "porque se ve rara". Toda corrección nace de una diferencia reproducida con un `SELECT` en ambos lados con el mismo recorte, o de un test que falla. Lo que no pueda verificarse queda marcado **"Pendiente de validar"**.

---

## 11. Resultados de la ejecución (primera pasada, 2026-07-14)

### 11.1 Veredicto de las hipótesis H-1..H-12

| ID | Veredicto | Evidencia |
|---|---|---|
| H-1 (doble definición de venta real) | **Pendiente de validar** | Requiere reconciliar `get_commission_lines` vs. `get_vendor_net_sales_period` con datos reales de un período cerrado; el EDW local de este entorno no tiene volumen de ventas cargado para muestrear. Diseño revisado en código: son dos consultas independientes sobre `fact_ventas_detalle` con el mismo filtro (`estado_documento_sk <> -1`, mismo vendedor/período) — estructuralmente deberían reconciliar, pero no se confirmó con datos. |
| **H-2 (`descuento_aprobado` sin flujo real)** | **CONFIRMADO** (Alta) | `CommissionService._calcular_variable` (`commission_service.py:147-154`) construye `LineaComisionable` sin el campo `descuento_aprobado` -> siempre `False` (default del dataclass). Se confirmó además que **no existe ninguna tabla/columna** en `edw.*` ni `public.*` que registre una aprobación de descuento por línea (`comision_config_vendedor`, `comision_matriz_categorias`, `comision_factores_credito`, `comision_liquidaciones` no tienen esa noción). **No se corrige con un parche silencioso** (auto-aprobar o ignorar el tope) porque eso cambiaría montos de comisión sin una decisión de negocio real. Queda como **brecha de producto**: se necesita decidir el flujo de aprobación (¿quién aprueba? ¿a nivel de línea, factura o vendedor? ¿con qué trazabilidad?) antes de implementarlo. Mientras tanto, el comportamiento actual (ninguna línea con descuento > tope comisiona, salvo que se apruebe explícitamente vía código) es conservador y no genera pagos de más -- el riesgo es subestimar la comisión, no sobreestimarla. |
| **H-3 (denominador de % descuento)** | **CONFIRMADO y CORREGIDO** (Alta) | `etl/transformers/fact_transformer.py:34-35` confirma que `subtotal_neto = totren` (ya post-descuento en SAP) y `valor_descuento = subtotal_bruto - subtotal_neto`. `commission_engine._calcular_linea` calculaba `pct_descuento = valor_descuento / subtotal_neto`, usando el neto como base en vez del bruto (`neto + descuento`). Esto infla el porcentaje real: un descuento del 25% sobre el precio de lista (bruto) se calculaba como 33.3%, dsiparando el tope del 30% para descuentos legítimos. **Corregido** en `commission_engine.py` (`subtotal_bruto = linea.subtotal_neto + linea.valor_descuento`); tests nuevos `test_descuento_25pct_sobre_bruto_no_dispara_tope_30pct` / `test_descuento_35pct_sobre_bruto_si_dispara_tope_30pct` en `test_commission_engine.py`. El test preexistente `test_descuento_excesivo_sin_aprobacion_no_comisiona` usaba datos que solo eran "excesivos" bajo el cálculo viejo (bug); se ajustó su fixture para reflejar un descuento real >30% sobre bruto. |
| **H-4 (modo inválido en snapshot de liquidación)** | **CONFIRMADO y CORREGIDO** (Alta, rompía producción) | La tabla `public.comision_liquidaciones` tiene `CheckConstraint("modo IN ('sombra','oficial')")` (`backend/app/models/commission_config.py:90`, confirmado también contra el EDW real con `\d public.comision_liquidaciones`). `CommissionService._persistir_snapshot` pasaba `modo=settings.COMISION_MODO` tal cual, que puede ser `"variable"` -- un valor que **no existe** en el CHECK y provoca `IntegrityError` en cada intento de persistir un snapshot cuando el backend corre en el modo que se supone es el oficial de producción (`COMISION_MODO=variable`). **Corregido**: se agregó el mapeo `_MODO_BACKEND_A_LIQUIDACION = {"sombra": "sombra", "variable": "oficial"}` en `commission_service.py`. Tests nuevos en `test_commission_service.py` (`test_snapshot_modo_variable_se_persiste_como_oficial`, `test_snapshot_modo_sombra_se_persiste_igual`, más las guardas preexistentes de modo "plana" y mes en curso). |
| H-5 (doble pasada de bonos) | **Descartado como bug** | Revisión del código y de los tests existentes (`test_bonos_se_suman_a_la_comision_final`) confirma que la 2ª pasada de `calcular_comision_variable` es pura respecto a `comision_post_cumplimiento` (no cambia entre pasadas, solo cambia `bonos_total` y por ende `comision_final`). El orden descrito en el plan §3.4 se respeta. |
| H-6 (`FACTOR_TASA_CERCA` no documentado al usuario) | **Mitigado, no requiere cambio** | El frontend (`VendorGoalDashboard.tsx`, card "Comisión") ya muestra `tasa_aplicada_pct` -- la tasa **efectiva** ya derivada (ej. 5.0% cuando la base es 7%), no la fracción cruda. El usuario ve el número real que se aplicó, aunque no se explique la fórmula `5/7` en sí. Se considera suficiente para esta pasada; documentar el factor en un tooltip queda como mejora menor (Baja) para una iteración futura. |
| H-7 (niveles plana/variable pueden divergir en pantalla) | **Pendiente de validar** | Depende de H-1. El frontend ya distingue visualmente ambas columnas con la etiqueta "(piloto)" en `CommissionTracker.tsx`, lo que reduce el riesgo de confusión aunque H-1 esté pendiente. |
| **H-8 (vigencia de config en simulación retroactiva)** | **CONFIRMADO y CORREGIDO** (Alta) | `CommissionSimulationService.simular` (`commission_simulation_service.py:68-69`, versión original) llamaba `get_matriz_as_reglas()`/`get_factores_credito_as_rangos()` **una sola vez, fuera del loop de períodos**, sin pasar `fecha` -> usaba el default (`datetime.date.today()`) para los `meses` históricos completos. Un cambio de configuración hecho hoy se aplicaba retroactivamente a "lo que el esquema nuevo habría pagado" en meses ya simulados, contradiciendo el propio diseño de vigencias (`vigente_desde`/`vigente_hasta`) que existe justamente para preservar el historial. **Corregido**: se agregó `_ultimo_dia_mes(anio, mes)` y la resolución de `matriz`/`rangos_credito` se movió dentro del loop `for anio, mes in periodos`, una vez por período (no por vendedor) usando la fecha de cierre de cada mes simulado. Tests nuevos en `test_commission_simulation_service.py` (fecha de referencia correcta por período bisiesto/no bisiesto, una sola resolución de config por período aunque haya varios vendedores). Se agregó también una nota explicativa en `CommissionSimulationPanel.tsx` (Fase D, UX #5) para que gerencia sepa que la simulación usa la configuración histórica, no la actual. |
| **H-9 (solapamiento de rangos de crédito sin validar)** | **CONFIRMADO y CORREGIDO** (Alta) | `commission_engine._factor_credito` resuelve por el primer rango que matchea en el orden de la lista (`commission_engine.py:204-208`); `CommissionConfigRepository.replace_factores_credito` reemplazaba la configuración vigente sin validar solapamientos. Con los datos reales actuales del EDW (`0-0` factor 1.0, `1-30` factor 0.85) no hay solapamiento hoy, pero nada impedía introducirlo desde el panel de gerencia. **Corregido**: `CommissionConfigService._validar_rangos_credito_sin_solape` (nuevo, lanza `ValidationError` de dominio) se invoca antes de `replace_factores_credito`. Para la matriz de categorías, `upsert_regla_categoria` ya cierra la fila vigente antes de insertar la nueva (`vigente_hasta`), por lo que duplicados vigentes por `(clase, subclase)` **no pueden originarse por CRUD normal** -- se descarta como bug para ese lado. Tests nuevos en `test_commission_config_service.py` (rangos sin solape, solapados, rango abierto, rangos contiguos). |
| H-10 (bonos sin tope) | **Pendiente de validar** | Requiere volumen real de `recomendaciones_eventos`/clientes nuevos por vendedor/mes, no disponible en este entorno. Revisión de código: no hay tope superior configurado para `bono_cross_sell` ni `bono_cliente_nuevo`; queda como hallazgo de diseño a decidir con gerencia (¿debe haber tope?), no como bug de implementación. |
| H-11 (margen vs. costo real de SAP) | **Pendiente de validar** | Requiere acceso a SAP (Fase A.2). Auditoría 30 (H1) ya había confirmado 0% de líneas sin margen en la carga vigente al momento de esa auditoría; no se repitió el muestreo línea a línea contra `articulos.ultcos` en esta pasada. |
| H-12 (corte de mes por `date.today()` del servidor) | **Descartado como riesgo material** | El servidor y el EDW operan en la misma zona horaria de despliegue (Docker Compose, sin configuración de TZ distribuida); el riesgo teórico existe pero no hay evidencia de un desfase real. Severidad Baja, no se actuó en esta pasada. |

### 11.2 Validaciones de integridad ejecutadas (Fase A.3/A.4, contra el EDW local, solo lectura)

- **FKs al centinela `vendedor_sk = -1`:** 66 de 521.811 líneas de venta válidas (0.01%) -- por debajo de cualquier umbral de materialidad; no genera un hallazgo nuevo (documentado aquí como "verificado, sin hallazgo").
- **SCD2 de `dim_producto`:** 0 filas con más de una versión `es_vigente = true` para el mismo `codart` -- sin hallazgo.
- **Solapamiento de `comision_factores_credito`:** con los 2 rangos actualmente configurados (`0-0` y `1-30`), sin solapamiento -- consistente con H-9 (el riesgo era de diseño/CRUD, no de los datos actuales).
- **Duplicados vigentes en `comision_matriz_categorias`:** 1 sola regla configurada (`BAT`, grupo A) -- sin duplicados.
- **`comision_liquidaciones`:** 0 filas (el piloto en sombra todavía no se ha ejecutado en este entorno) -- no hay snapshots que revisar por duplicidad/mutación; la corrección de H-4 se valida por inspección de código y tests, no por datos existentes.

### 11.3 Correcciones aplicadas

| Archivo | Cambio | Hallazgo |
|---|---|---|
| `backend/app/services/commission_engine.py` | `pct_descuento` se calcula sobre `subtotal_neto + valor_descuento` (bruto), no sobre `subtotal_neto` (neto) | H-3 |
| `backend/app/services/commission_service.py` | Mapeo `_MODO_BACKEND_A_LIQUIDACION` antes de llamar `save_liquidacion` | H-4 |
| `backend/app/services/commission_config_service.py` | `_validar_rangos_credito_sin_solape` (lanza `ValidationError`) antes de `replace_factores_credito` | H-9 |
| `backend/tests/unit/test_commission_engine.py` | +2 tests (H-3), 1 fixture corregida | H-3 |
| `backend/tests/unit/test_commission_service.py` | +4 tests de mapeo de modo y snapshot | H-4 |
| `backend/tests/unit/test_commission_config_service.py` (nuevo) | +4 tests de solapamiento de rangos de crédito | H-9 |
| `frontend/src/components/goals/VendorGoalDashboard.tsx` | Desglose de la comisión variable en cascada (`<details>` con base → ×tipo → ×cumplimiento → −devoluciones → +bonos → total), usando `desglose_variable` que el backend ya exponía pero el frontend no renderizaba | Fase D (UX #3) |
| `backend/app/services/commission_simulation_service.py` | `matriz`/`rangos_credito` se resuelven por período simulado (fecha de cierre de cada mes), no una sola vez con la fecha de hoy; nuevo helper `_ultimo_dia_mes` | H-8 |
| `backend/tests/unit/test_commission_simulation_service.py` (nuevo) | +3 tests: fecha de referencia correcta, una sola resolución de config por período | H-8 |
| `frontend/src/components/goals/CommissionSimulationPanel.tsx` | Nota explícita: la simulación usa la configuración vigente al cierre de cada mes, no la actual | Fase D (UX #5) |

**Validación tras las correcciones:** `pytest backend/tests/unit` completo -- **118 passed**, sin regresiones. `py_compile` limpio en los 4 archivos de servicio tocados. `tsc --noEmit` del frontend sin errores nuevos. Cero escrituras a Producción (SAP) en toda esta pasada -- las únicas consultas ejecutadas fueron `SELECT`/`\d` de solo lectura contra el EDW local (`bi_postgres_edw`, Docker) y revisión estática de código.

### 11.3-bis Fase A.1/A.2 ejecutada contra SAP (acceso concedido, solo `SELECT`)

Se obtuvieron credenciales de solo lectura contra Producción (SAP SQL Anywhere, `172.16.50.5:4016`, driver ODBC nativo "SQL Anywhere 12" ya instalado en este host). **Todas las consultas de esta sección fueron `SELECT` puros ejecutados con una conexión pyodbc directa (sin pasar por el dialecto `mssql+pyodbc` de SQLAlchemy, que emite un diagnóstico `SELECT schema_name()` incompatible con SQL Anywhere); ninguna escritura, ningún `INSERT`/`UPDATE`/`DELETE`/DDL.** Esto permitió cerrar varias hipótesis pendientes y **reveló tres hallazgos nuevos de severidad Alta que invalidan un supuesto central del diseño de Comisiones Variables**.

#### H-13 (NUEVO) — `renglonesfacturas.bienser` existe, está poblado, y el ETL lo descarta -> `es_servicio` es `False` para el 100% del catálogo

```sql
-- SAP, codemp='01', estado='P' (solo SELECT)
SELECT r.bienser, COUNT(*), SUM(r.totren)
FROM renglonesfacturas r JOIN encabezadofacturas e ON r.codemp=e.codemp AND r.numfac=e.numfac
WHERE r.codemp='01' AND e.estado='P' GROUP BY r.bienser;
-- Resultado: ('S', 58407 líneas, $204,421.79) | ('B', 463582 líneas, $28,091,175.53) | (NULL, 1, $149.80)
```

`renglonesfacturas` tiene una columna real `bienser` ('B'=bien, 'S'=servicio) con **58.407 líneas reales de servicio** (10.1% del total, ~$204 mil de venta). Sin embargo:
- `facturas_detalle_extractor.sql` **no selecciona `bienser`** en absoluto.
- `articulos_extractor.sql` tampoco lo selecciona (`articulos.bienser` existe pero solo tiene 1 fila en 'S' de 8.152 -- el maestro de artículos casi no lo usa; el flag real y confiable vive en la línea de la transacción, `renglonesfacturas.bienser`, no en el artículo).
- `dim_transformer.py:82-83` hardcodea `es_servicio = False` para el 100% de `dim_producto` cuando la columna no viene en el DataFrame de origen (`if 'es_servicio' not in df.columns: df['es_servicio'] = False`) -- y como el extractor nunca la trae, **siempre** cae en este default.

**Impacto:** `commission_engine._calcular_linea` decide la ruta de cálculo con `if linea.es_servicio:` (grupo S, tasa dedicada sobre `subtotal_neto`). Como `es_servicio` es `False` para absolutamente todas las líneas, **esa rama nunca se ejecuta con datos reales** -- las 58.407 líneas de servicio (~$204 mil) se comisionan hoy por la ruta de margen/costo, y como los servicios típicamente no tienen `ultcos` (no son inventariables), la mayoría cae en la Salvaguarda 2 ("línea sin costo" -> `tasa_minima_sin_costo_pct`, un valor de config genérico) en vez del `tasa_pct` específico configurado para el grupo S en `comision_matriz_categorias`. **Esto invalida directamente RN-CM1** ("la comisión variable se calcula sobre... `subtotal_neto` (grupo S -- servicios)") tal como está implementado hoy: el grupo S es código muerto frente a datos reales.

**Nota de grano:** `bienser` es un atributo de la **línea de la transacción** (`renglonesfacturas`), no del artículo maestro (`articulos.bienser` casi no lo usa -- 1 de 8.152). Esto significa que la corrección correcta no es solo poblar `dim_producto.es_servicio` desde `articulos`, sino traer `bienser` a nivel de línea en el extractor de facturas y decidir si `es_servicio` debe vivir en `fact_ventas_detalle` (grano de línea) en vez de -- o además de -- `dim_producto` (grano de producto). Es un cambio de diseño, no un one-liner.

#### H-14 (NUEVO) — `articulos.subcodcla` existe, está 100% poblado, y el ETL lo descarta -> `subclase` es `NULL` para el 100% del catálogo

```sql
SELECT COUNT(*), SUM(CASE WHEN subcodcla IS NULL OR subcodcla='' THEN 1 ELSE 0 END) FROM articulos WHERE codemp='01';
-- Resultado: 8152 filas, 0 vacías/NULL -- 100% poblado.
SELECT COUNT(DISTINCT subcodcla) FROM articulos WHERE codemp='01';
-- Resultado: 50 valores distintos.
```

`articulos_extractor.sql` línea 8 hardcodea `NULL AS subclase` en vez de seleccionar `subcodcla` (que existe, está 100% poblado y tiene 50 valores distintos -- suficiente granularidad real). Esto contradice directamente **RN-CM2** y el diseño de `_resolver_regla` en `commission_engine.py` (que prioriza `(clase, subclase)` exacto sobre `(clase, NULL)`): con `subclase` siempre `NULL`, esa resolución más específica **nunca puede ocurrir** -- toda regla queda forzosamente al nivel de `clase`, perdiendo la granularidad que SAP sí tiene disponible. A diferencia de auditoría 30 (H2, que encontró `nombre_clase` vacío y correctamente concluyó "clasificar por código, no por nombre"), este hallazgo es distinto: **el código `subcodcla` sí existe y sí está poblado** -- el problema no es SAP, es que el extractor lo tira a `NULL` en vez de traerlo.

#### H-15 (NUEVO) — Regla de negocio 5 (costo de inventario solo si `desinv='S'`) no se respeta en el cálculo de margen

```sql
SELECT r.desinv, COUNT(*), SUM(r.cantid * COALESCE(a.ultcos,0))
FROM renglonesfacturas r
JOIN encabezadofacturas e ON r.codemp=e.codemp AND r.numfac=e.numfac
LEFT JOIN articulos a ON r.codemp=a.codemp AND r.codart=a.codart
WHERE r.codemp='01' AND e.estado='P' GROUP BY r.desinv;
-- Resultado: ('N', 904 líneas, $68,371.87 de costo) | ('S', 521086 líneas, $444,083,394.40 de costo)
```

La regla de negocio 5, ya documentada y validada (`docs/auditoria/02_reglas_negocio_validadas.md` #5): "el costo de inventario solo aplica cuando `renglonesfacturas.desinv = 'S'`". Sin embargo `facturas_detalle_extractor.sql` selecciona `NULL AS desinv` (descarta la columna real) y `fact_transformer.py:38-40` calcula `costo_total = cantidad * costo_unitario` y `margen_bruto = subtotal_neto - costo_total` **para todas las líneas sin excepción**, sin condicionar por `desinv`. Con datos reales: 904 líneas no inventariables (`desinv='N'`) tienen, sin embargo, `ultcos` asignado en `articulos` (porque `ultcos` es un atributo del artículo, no de la línea) -- si se les aplica el costo igual, se les atribuye indebidamente **$68.371,87 de costo**, deflactando su margen y por ende su comisión variable (grupo A/B/C usa `base='margen'`). Volumen menor (904 líneas, 0.17% del total) pero es una violación directa de una regla de negocio ya documentada y validada, no una hipótesis nueva.

#### Hipótesis originales cerradas con esta evidencia

| ID | Veredicto actualizado | Evidencia |
|---|---|---|
| H-11 (margen vs. costo real de SAP) | **CONFIRMADO parcialmente** -- ver H-15. El cálculo de margen es correcto en fórmula (`subtotal_neto - cantidad*ultcos`) pero no respeta la condición `desinv='S'` de la regla 5, con el impacto cuantificado arriba. |
| RN-CM4 (plazo de crédito solo 0/30 días) | **Reclasificado -- no es una limitación de SAP, es una limitación del ETL.** `formapago_extractor.sql` **no consulta ninguna tabla real de SAP**: es una tabla estática de 3 filas (`'E'->0 días`, `'C'->30 días`, `'0'->0 días`) generada con `UNION ALL ... FROM dummy`. La auditoría 30 (H4) concluyó "el EDW actual solo tiene tráfico real en 0 y 30 días" asumiendo que reflejaba la realidad de SAP -- en realidad es que el extractor de formas de pago nunca leyó una tabla real de plazos; siempre y por diseño solo puede producir 0 o 30. **Pendiente de validar** si SAP tiene una tabla de condiciones de pago más rica (ej. `condicionespago`, no inspeccionada en esta pasada) que el ETL simplemente no conecta. |

### 11.3-ter H-13/H-14/H-15 implementadas y verificadas contra el EDW recargado

Con autorización explícita del usuario (acción de mayor alcance: recarga completa de `fact_ventas_detalle`, ~522k filas), se implementó y ejecutó la corrección completa:

**Cambios de código:**
- `etl/extractors/facturas_detalle_extractor.sql`: se seleccionan `r.bienser` y `r.desinv` reales (antes `NULL AS desinv`, `bienser` ni se traía).
- `etl/extractors/articulos_extractor.sql`: se selecciona `subcodcla AS subclase` (antes `NULL AS subclase`); alias `ultcos AS ultimo_costo` (cambio del usuario, semánticamente correcto -- `ultcos` es el último costo, no un promedio).
- `etl/transformers/dim_transformer.py` (`transformar_productos`): rename `ultimo_costo` -> `costo_promedio` para no alterar el nombre de columna del DW (mismo patrón que ya usa `fact_transformer.py` con `numfac`/`num_factura`).
- `etl/transformers/fact_transformer.py` (`transformar_ventas_detalle`): nueva columna derivada `es_linea_servicio` (`bienser == 'S'`, grano línea); `costo_unitario`/`costo_total`/`margen_bruto` ahora se computan solo cuando `desinv == 'S'` (antes se computaban siempre); se corrigió además que `margen_bruto` no estaba en la lista `permitir_nulos` de `normalizar_numericos` (inconsistente con su propio comentario) -- sin este ajuste, las líneas con `desinv='N'` habrían quedado con `margen_bruto=0.0` en vez de `NULL`, y la Salvaguarda 2 del motor (`margen_bruto is None`) nunca se habría activado para ellas.
- `edw/03_hechos.sql`: nueva columna `fact_ventas_detalle.es_linea_servicio BOOLEAN NOT NULL DEFAULT FALSE` (DDL para volúmenes nuevos); aplicada manualmente al EDW local existente vía `ALTER TABLE` (regla del proyecto: los DDL de `edw/` solo corren al crear el volumen).
- `backend/app/repositories/goal_repository.py`: `get_commission_lines` y `get_margin_profile_by_category` ahora leen `f.es_linea_servicio` (grano línea, del hecho) en vez de `p.es_servicio` (grano producto, del `dim_producto` derivado de `articulos.bienser`, casi sin uso real).

**Incidente durante la ejecución (documentado con transparencia total):** forzar una recarga completa vía reseteo de `edw.etl_control` expuso un bug adicional y separado del orquestador: la ruta de carga "completa" (no incremental) de `load_facts_incremental` **nunca ejecuta el `DELETE` de idempotencia** -- el `if cfg.get('snapshot'): ... elif incremental: ...` no tiene rama `else` para el caso full-reload, así que el `INSERT` corrió sobre datos ya existentes en vez de reemplazarlos. Al re-ejecutar dos veces (una con la imagen Docker vieja sin mis cambios, sin darme cuenta de que `etl/Dockerfile` hace `COPY . .` en vez de montar el código como volumen; luego con la imagen reconstruida), `fact_ventas_detalle` quedó con **1.565.797 filas -- prácticamente el triple de las ~522k esperadas**. Diagnosticado por `fecha_carga` agrupada (4 cargas distintas acumuladas). **Corrección aplicada, con confirmación explícita del usuario:** `TRUNCATE TABLE edw.fact_ventas_detalle` (tabla 100% re-derivable desde SAP, sin datos editados a mano) seguido de una única recarga limpia -> **522.003 filas finales**, consistente con el conteo esperado.

**Verificación contra el EDW ya recargado (solo lectura, EDW local):**

```sql
SELECT es_linea_servicio, COUNT(*), SUM(subtotal_neto) FROM edw.fact_ventas_detalle GROUP BY es_linea_servicio;
-- f: 463.594 líneas, $28.091.634,89  |  t: 58.409 líneas, $204.422,29
-- Coincide con la distribución real de SAP (58.407 líneas 'S' medidas en 11.3-bis, diferencia
-- de 2 por nuevas transacciones entre ambas mediciones).

SELECT COUNT(*) total, SUM(CASE WHEN margen_bruto IS NULL THEN 1 ELSE 0 END) margen_null FROM edw.fact_ventas_detalle;
-- 522.003 total, 59.272 con margen_bruto NULL (antes SIEMPRE se rellenaba con costo,
-- incluso para líneas desinv='N' -- ahora correctamente NULL, activa Salvaguarda 2).
```

**H-14 requirió un backfill adicional** (con confirmación explícita del usuario): el loader SCD2 de `dim_producto` (`etl/loaders/dim_loader.py::load_dim_scd2`) **solo detecta cambios comparando `desc_col`** (`nombre_articulo` para esta tabla) -- ignora silenciosamente cambios en cualquier otra columna. Como `nombre_articulo` no cambió para los productos existentes, el loader los consideró "sin cambio" y nunca insertó los valores corregidos de `subclase`, aunque la extracción ya los traía bien. Se aplicó un `UPDATE` puntual (solo `SELECT` contra SAP + `UPDATE` de la columna `subclase` en las filas vigentes del EDW local, sin tocar ninguna otra columna ni borrar filas) para backfillear los 8.150 productos vigentes. Verificado:

```sql
SELECT COUNT(*) total, SUM(CASE WHEN subclase IS NULL OR subclase='' THEN 1 ELSE 0 END) sin_subclase
FROM edw.dim_producto WHERE es_vigente=true;
-- 8.151 total, 1 sin subclase (el centinela codart='-1', esperado).
```

#### H-16 (NUEVO) — El loader SCD2 (`load_dim_scd2`) solo rastrea cambios en `desc_col`, ignora el resto de columnas

Confirmado por el incidente anterior: `load_dim_scd2` compara únicamente `df_merged[desc_col] != df_merged['val_actual']` para decidir si expirar la versión vigente e insertar una nueva. Cualquier otro atributo que cambie (precio, costo, clasificación, etc.) **no dispara una nueva versión SCD2** mientras `desc_col` no cambie -- se pierde silenciosamente en cada re-ejecución del ETL hasta que `desc_col` también cambie. Afecta a las 3 dimensiones SCD2 del pipeline (`dim_producto` con `desc_col='nombre_articulo'`, `dim_cliente` con `desc_col='clase_cliente'`, y cualquier futura). **Severidad Media** (no corrompe datos, pero hace que correcciones de atributos secundarios no lleguen al EDW sin intervención manual, como se vio con `subclase`). **Recomendación:** `load_dim_scd2` debería comparar TODAS las columnas de negocio (excluyendo SK/fechas de vigencia), no solo `desc_col` -- queda fuera del alcance de esta pasada por ser un cambio al loader compartido por varias dimensiones.

#### H-17 (NUEVO) — El 99.9% de las líneas de servicio no resuelven `producto_sk` (caen al centinela)

Verificación post-recarga:
```sql
SELECT es_linea_servicio, producto_sk=-1 AS sin_producto, COUNT(*) FROM edw.fact_ventas_detalle WHERE estado_documento_sk<>-1 GROUP BY 1,2;
-- servicio=t, sin_producto=t: 58.363 (de 58.409 líneas de servicio -- 99.9%)
-- servicio=f, sin_producto=t:      5 (de 463.594 líneas de bien -- 0.001%, normal)
```
La inmensa mayoría de las líneas de servicio usan un `codart` que **no existe en el maestro `articulos`** (de donde se deriva `dim_producto`), así que `resolver_llaves_hecho` las asigna al centinela `-1` ("Desconocido"). **Esto no lo introdujo el fix de esta pasada** (la resolución de `producto_sk` es independiente de `es_linea_servicio`, que ahora viene del hecho, no de la dimensión) -- pero sí quedó expuesto por primera vez al verificar el join en detalle. **Impacto en Comisiones Variables:** el grupo S (servicios) ya se activa correctamente gracias a H-13 (`es_linea_servicio` no depende de `producto_sk`), pero esas líneas pierden su `clase`/`subclase` real (quedan con `clase='UNK'` del centinela) -- `_resolver_regla` las clasificará por el comodín `'*'`/default en vez de por su categoría real, si es que gerencia quisiera tasas distintas por tipo de servicio. **No bloqueante** para el grupo S en general (que no depende de clase), sí para una futura sub-clasificación de servicios. Pendiente de decidir con gerencia si vale la pena modelar servicios como pseudo-artículos en `articulos`/SAP, o aceptar que todos los servicios comparten una sola tasa (grupo S sin sub-categoría).

### 11.4 Pendiente para una siguiente pasada

1. ~~H-13/H-14/H-15~~ -- **implementadas, recargadas y verificadas contra el EDW en esta misma pasada** (Sección 11.3-ter). Generaron dos hallazgos nuevos en el camino: **H-16** (el loader SCD2 solo detecta cambios en `desc_col`, ignora el resto de columnas -- severidad Media, requeriría tocar `dim_loader.py`, compartido por varias dimensiones) y **H-17** (99.9% de las líneas de servicio no resuelven `producto_sk`, pierden su `clase`/`subclase` real -- no bloqueante para el grupo S en sí, sí para sub-clasificar servicios en el futuro).
2. **Fase A.1/A.2, resto** (H-1): instrumentar temporalmente ambas consultas (`get_commission_lines` agregada vs. `get_vendor_net_sales_period`) sobre el mismo vendedor/período con datos reales de SAP y diffear -- ahora que H-13/14/15 están corregidas, ya no hay riesgo de que la comparación esté contaminada por la mala clasificación de servicios.
3. **RN-CM4 (plazo de crédito)**: investigar si SAP tiene una tabla real de condiciones de pago (`condicionespago` o similar) más rica que los 2 valores fijos (0/30 días) que el extractor estático de `formapago_extractor.sql` genera hoy por diseño.
4. **H-2**: decisión de producto sobre el flujo de aprobación de descuentos (no es una corrección de código pendiente, es una funcionalidad nueva a diseñar con gerencia).
5. **H-10**: definir con gerencia si los bonos de venta cruzada/cliente nuevo deben tener un tope superior, y a qué volumen real equivalen hoy.
6. **H-16/H-17**: corregir `load_dim_scd2` para comparar todas las columnas de negocio (no solo `desc_col`), y decidir con gerencia cómo tratar la clasificación de líneas de servicio sin `producto_sk` real.
7. Resto de las mejoras UX de la Fase D (jerarquía por rol en `DashboardMetas.tsx`, validación en vivo de la matriz de categorías en `CommissionConfigPanel`, estados vacíos) -- se aplicaron las mejoras #3 y #5 (desglose explicable y contexto de vigencia de la simulación) en esta pasada; el resto sigue vigente como se describió en la Sección 7.
