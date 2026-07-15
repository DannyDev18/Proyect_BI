# Propuesta: Sistema de Comisiones Variables por Producto, Categoría y Margen

> **Fecha:** 2026-07-13
> **Estado:** propuesta para presentar a la empresa (no implementado).
> **Contexto:** hoy la empresa no tiene un método formal de metas y comisiones. La plataforma BI ya calcula metas mensuales por vendedor (estadística IQR sobre Venta Neta, `docs/modulo_metas.md`) y liquida comisión con **tasa plana sobre la venta neta total** por tramos de cumplimiento (`backend/app/services/commission_engine.py`). Esta propuesta evoluciona ese esquema: **no todo lo vendido comisiona igual** — un artículo de bajo precio/margen no puede pagar lo mismo que uno de alto valor.

---

## 1. Problema del esquema plano (por qué proponer esto)

Con tasa plana sobre venta neta:

- El vendedor gana lo mismo vendiendo $1.000 de un producto con 5% de margen que $1.000 de uno con 40% de margen — **la empresa gana 8 veces menos en el primero y paga la misma comisión**.
- Incentiva vender "lo fácil" (productos baratos de alta rotación) y regalar descuentos, porque el descuento reduce poco su comisión pero destruye el margen.
- No permite alinear el incentivo con la estrategia comercial (empujar categorías nuevas, líneas con sobre-stock, productos de alto margen).

## 2. Principio rector de la propuesta

> **Se comisiona sobre lo que la empresa realmente gana (margen bruto), no sobre lo que factura (venta bruta), ponderado por categoría estratégica y condicionado al cumplimiento de la meta.**

Esto resuelve de raíz el problema "artículo barato vs. caro": la comisión es proporcional al aporte real de cada línea de venta, automáticamente. Un descuento agresivo reduce el margen → reduce la comisión → el vendedor cuida el precio solo.

## 3. Fórmula propuesta

```
Comisión del mes = [ Σ por cada línea vendida:
                       margen_bruto_línea × tasa_categoría × factor_estratégico ]
                   × multiplicador_de_cumplimiento(meta)
                   − ajuste_por_devoluciones
                   + bonos
```

### 3.1 Variables de la fórmula (todas ya existen en el EDW)

| Variable | Fuente en la plataforma | Rol |
|---|---|---|
| `margen_bruto` por línea | `edw.fact_ventas_detalle.margen_bruto` (venta − costo, por renglón de factura) | Base de la comisión. Un artículo de $2 aporta centavos; uno de $500 con buen margen aporta proporcionalmente. |
| Categoría del producto | `edw.dim_producto.clase` / `subclase` (catálogo SAP ya cargado) | Define la **tasa** de la matriz (§3.2). |
| Precio / costo | `dim_producto.precio_oficial`, `costo_promedio`, `fact_ventas_detalle.costo_unitario` | Insumo del margen; permite detectar líneas sin costo (§6, salvaguardas). |
| Descuento otorgado | `fact_ventas_detalle.valor_descuento` | Ya está dentro del margen (más descuento → menos comisión). Además, tope de descuento sin aprobación (§3.5). |
| Devoluciones | `edw.fact_devoluciones` (monto y costo por vendedor/producto) | Se restan de la base comisionable del mes en que ocurren. |
| Cumplimiento de meta | Módulo existente (meta IQR + tramos EXCELENTE/META/CERCA/LEJOS) | Multiplicador — se **conserva** el motor actual, no se bota nada. |
| Venta cruzada aceptada | `public.recomendaciones_eventos` (telemetría del asistente, auditoría 25) | Bono opcional por adopción (§3.4). |
| Servicios no inventariables | `dim_producto.es_servicio`, `desinv='N'` | Tasa propia (no tienen costo de inventario → margen artificialmente alto; §3.2). |

### 3.2 Matriz de tasas por categoría (el corazón negociable de la propuesta)

La tasa se aplica **sobre el margen bruto** de la línea, no sobre la venta. Valores de ejemplo — los definitivos salen del análisis histórico de la Fase 1 y de la negociación con gerencia:

| Grupo de categorías (`clase`) | Margen típico | Tasa sobre margen | Racional |
|---|---|---|---|
| A — Alto margen / estratégicas (lo que la empresa quiere empujar) | > 30% | 12–15% | Premiar donde más gana la empresa. |
| B — Margen medio / volumen | 15–30% | 8–10% | La base del negocio. |
| C — Bajo margen / commodities de rotación | < 15% | 4–6% | Comisionan poco por sí solos: se venden "solos". |
| S — Servicios (`es_servicio`) | sin costo de inventario | 5–8% sobre el **valor**, no el margen | El margen contable sería ~100%; sería injusto usar la fórmula general. |
| X — Excluidos (fletes, redondeos, promociones a precio 0) | — | 0% | `pct_margen = 0` en cortesías (convención auditoría 07 H8). |

**Factor estratégico** (multiplicador 1.0–1.5, temporal y por campaña): permite a gerencia empujar una subclase específica un trimestre (p. ej. sobre-stock detectado por el Dashboard de Bodega → factor 1.3 por 90 días) sin rediseñar la matriz.

### 3.3 Multiplicador por cumplimiento de meta (se reutiliza el módulo existente)

La meta mensual por vendedor ya se genera automáticamente (IQR + tendencia). La comisión variable del §3.1 se escala por el tramo alcanzado, manteniendo los umbrales ya implementados:

| Cumplimiento de meta (Venta Neta) | Nivel actual | Multiplicador propuesto |
|---|---|---|
| ≥ 100% | EXCELENTE | 1.2 × + bono fijo de sobrecumplimiento |
| 90–99% | META | 1.0 × |
| 80–89% | CERCA | 0.7 × |
| < 80% | LEJOS | 0.4 × (piso — que el esfuerzo parcial no valga cero es negociable; hoy el motor paga 0) |

Así conviven las dos dimensiones: **qué** vendiste (matriz por margen/categoría) y **cuánto** vendiste contra tu meta (tramos).

### 3.4 Bonos complementarios (opcionales, fase 2 de adopción)

- **Bono de venta cruzada:** % adicional sobre las líneas originadas en sugerencias aceptadas del asistente (`recomendaciones_eventos`, evento `aceptada`). Alinea la adopción de la herramienta con el bolsillo del vendedor.
- **Bono de cliente nuevo / reactivado:** monto fijo por cliente sin compras en N meses que vuelve a comprar (detectable con el RFM/churn ya entrenado).
- **Bono de cobranza sana:** condicionar un % de la comisión a que la factura esté cobrada (`edw.fact_cobros_cxc`) — evita comisionar ventas que luego se vuelven incobrables. Recomendado: pagar 80% al facturar, 20% al cobrar.

### 3.5 Salvaguardas anti-abuso

1. **Devoluciones descuentan** la base comisionable del mes en que ocurren (no del mes de la venta) — simple y no reabre liquidaciones cerradas.
2. **Descuento máximo sin autorización:** líneas con descuento > X% requieren aprobación de gerencia para comisionar (el dato ya está en `valor_descuento`).
3. **Líneas sin costo** (`costo_unitario IS NULL`, hallazgo auditoría 08 F2): no entran a la fórmula por margen; se comisionan con la tasa mínima sobre el valor, y se reportan a gerencia para corregir el costo en SAP.
4. **Anulaciones:** solo documentos `estado='P'` (regla de negocio 1 del EDW, ya aplicada en toda la plataforma).
5. **Transparencia total:** el vendedor ve en su dashboard el detalle línea por línea de cómo se formó su comisión (la plataforma ya tiene el panel "Mi Comisión"; se enriquece con el desglose por categoría).

## 4. Plan de trabajo para construir y proponer el sistema a la empresa

### Fase 1 — Análisis histórico con el EDW (1 semana) — *"hablar con datos, no con opiniones"*
1. Perfil de margen por `clase`/`subclase`: margen promedio, % de la venta total, № de vendedores que la venden (consulta sobre `fact_ventas_detalle` × `dim_producto`, últimos 24 meses).
2. Distribución de venta por vendedor y categoría: ¿quién vive de qué categoría? (detecta a quién beneficia/perjudica cada matriz).
3. Tasa de devoluciones y de descuento por vendedor.
4. **Entregable:** informe con la clasificación A/B/C/S/X de categorías propuesta con datos reales, no supuesta.

### Fase 2 — Diseño de la matriz y simulación retroactiva (1 semana) — *el argumento decisivo*
1. Definir 2–3 escenarios de matriz (conservador / medio / agresivo).
2. **Simular los últimos 12 meses**: para cada vendedor y mes, calcular cuánto habría ganado con cada escenario vs. un esquema plano de referencia. Todo con datos ya cargados en el EDW — es una consulta, no un desarrollo.
3. Calcular el **costo total anual para la empresa** de cada escenario y el % que representa sobre el margen bruto generado (KPI de sanidad: la comisión total no debería superar ~X% del margen bruto — lo define gerencia).
4. **Entregable:** tabla comparativa "qué habría pasado" — es la pieza que convence a gerencia porque elimina el miedo al costo desconocido, y a los vendedores porque pueden ver su número.

### Fase 3 — Presentación y negociación con la empresa (1–2 sesiones)
1. Presentar: problema del esquema plano → principio (comisionar margen) → matriz → simulación de costo → salvaguardas.
2. Puntos que la empresa debe decidir (llevarlos como preguntas cerradas): tasas finales por grupo, piso del tramo LEJOS (¿0% o 0.4×?), bono de cobranza (¿80/20?), tope de descuento comisionable, presupuesto máximo de comisiones como % del margen.
3. **Entregable:** acta con las variables acordadas → se convierten en configuración, no en código (regla del proyecto: sin hardcodes).

### Fase 4 — Piloto en sombra (2–3 meses, riesgo cero)
1. La plataforma calcula la comisión nueva **en paralelo** a lo que la empresa pague hoy, sin efecto en nómina.
2. Cada vendedor ve ambos números en su dashboard ("con el sistema nuevo habrías ganado…").
3. Ajustar la matriz con los casos reales que aparezcan (categorías mal clasificadas, costos faltantes en SAP).
4. Criterio de salida del piloto: ≤5% de líneas sin costo, costo total dentro del presupuesto, sin distorsiones por vendedor (nadie pierde >X% vs. esquema anterior sin causa justificada).

### Fase 5 — Implementación técnica en la plataforma (después de aprobado; estimación 1–2 semanas)
Cambios acotados, reutilizando lo construido:
1. Tabla nueva `public.comision_matriz_categorias` (grano: `clase`/`subclase`, `tasa_pct`, `base` = margen|valor, `factor_estrategico`, vigencias) + CRUD para gerencia. Sin tocar el EDW.
2. Extensión de `commission_engine.py`: nueva función pura `calcular_comision_variable(lineas, matriz, tramo)` que convive con la actual (el multiplicador por tramo se reutiliza tal cual). El esquema plano queda como fallback configurable — **rollback trivial**.
3. Consulta nueva en `GoalRepository`: desglose mensual de margen por vendedor × categoría desde `fact_ventas_detalle` (+ devoluciones).
4. Frontend: desglose por categoría en "Mi Comisión" y panel de simulación/configuración de la matriz para gerencia.
5. Auditoría previa en `docs/auditoria/` + reglas nuevas en `02_reglas_negocio_validadas.md` (flujo estándar del proyecto).

## 5. Ejemplo numérico para la presentación

Vendedor con meta de $50.000, vendió $52.000 (104% → EXCELENTE, ×1.2):

| Línea vendida | Venta | Margen | Grupo | Tasa s/margen | Comisión línea |
|---|---|---|---|---|---|
| 40 uds. commodity a $25 | $1.000 | $80 (8%) | C | 5% | $4,00 |
| 2 equipos a $500 | $1.000 | $350 (35%) | A | 13% | $45,50 |
| Servicio de instalación | $300 | — | S | 6% s/valor | $18,00 |

Misma venta de $1.000 en commodity vs. equipos: **$4 vs. $45,50** — el incentivo queda automáticamente alineado con el valor real de cada artículo, que es exactamente el requerimiento. Con el esquema plano actual (p. ej. 7%), ambas líneas pagarían $70 idénticos.

## 6. Riesgos y mitigaciones

| Riesgo | Mitigación |
|---|---|
| Vendedores rechazan el cambio ("me bajan la comisión") | Piloto en sombra + simulación personal de 12 meses; calibrar la matriz para que el costo total sea ≈ neutral y solo cambie la *distribución* del incentivo. |
| Costos mal cargados en SAP distorsionan el margen | Salvaguarda §3.5.3 + reporte de líneas sin costo; el piloto los aflora antes de pagar un centavo. |
| Manipulación de precios/descuentos | El margen ya castiga el descuento solo; tope de descuento comisionable como segunda barrera. |
| Complejidad percibida | El vendedor no necesita la fórmula: ve en su dashboard "cada categoría te paga X%" y el detalle línea a línea. |
| Cambio de estrategia comercial | Matriz y factores en tabla configurable con vigencias — gerencia la ajusta sin desarrollo. |
