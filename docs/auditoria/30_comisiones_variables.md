# Auditoría 30 — Fase 0: Sistema de Comisiones Variables

> **Fecha:** 2026-07-14
> **Alcance:** validar contra el EDW (solo `SELECT`, `bi_postgres_edw` vía `docker exec`) los supuestos de datos de `docs/features/plan_integracion_comisiones_variables.md` antes de implementar código.
> **Método:** consultas `SELECT` directas contra `edw.fact_ventas_detalle`, `edw.dim_producto`, `edw.dim_formapago`, período completo cargado (~521.766 líneas válidas, `estado_documento_sk <> -1`).

## Hallazgos

### H1 — Cobertura de margen: 100% de las líneas tienen `margen_bruto` calculable
```
total_lineas=521766, sin_margen(margen_bruto IS NULL)=0, pct_sin_margen=0.00%
```
La salvaguarda 2 (líneas sin costo → tasa mínima sobre valor) sigue siendo necesaria como código defensivo, pero **no hay backlog actual** de líneas sin costo en el EDW cargado. No bloquea ninguna fase.

### H2 — `dim_producto.nombre_clase` está 100% vacío (severidad: media)
```
total=8151, nombre_clase_vacio=8151 (100%), clases_distintas(código)=22
```
El catálogo tiene 22 códigos de `clase` distintos pero **ningún nombre descriptivo cargado** (extractor/transformer no lo puebla). **Decisión:** la matriz de categorías (`comision_matriz_categorias`) debe indexar por el código `clase`/`subclase` (ya confiable), no por `nombre_clase`. El frontend de configuración debe permitir a gerencia asignar una etiqueta legible por código al momento de clasificar (A/B/C/S/X), sin depender de que el ERP pueble el nombre.

### H3 — El ratio margen/venta por línea individual NO es usable para clasificación directa (severidad: alta, afecta diseño)
```
mediana_margen_pct = 18.03%   (razonable, coincide con el orden de magnitud esperado)
min_ratio = -20699.0          max_ratio = 1.0
líneas con |subtotal_neto| < 1 = 96.926  (18.6% del total)
```
Un ~18.6% de las líneas tiene `subtotal_neto` cercano a cero (cortesías, redondeos, ítems a precio simbólico — mismo patrón que la convención de auditoría 07 H8). Dividir `margen_bruto/subtotal_neto` en esas líneas produce ratios absurdos (hasta -20.699×) que **contaminarían un `AVG()` ingenuo** del perfil de margen por categoría.

**Decisión de diseño (corrige `propuesta_sistema_comisiones_variables.md` §3.2 y el plan §3.3):**
- `get_margin_profile_by_category` (Fase 1) debe agregar con `SUM(margen_bruto)/SUM(subtotal_neto)` por categoría (margen ponderado por volumen), **nunca** `AVG(margen_bruto/subtotal_neto)` por línea.
- La clasificación de una línea individual a grupo **X** (excluida) se activa cuando `subtotal_neto` está por debajo de un umbral configurable (`COMISION_UMBRAL_SUBTOTAL_X`, default `1.0`), no solo cuando es exactamente 0 — generaliza la convención ya usada en auditoría 07 H8.

### H4 — El plazo de crédito real solo tiene dos valores poblados: 0 y 30 días (severidad: alta, reduce alcance de la Fase 2/5)
```
dias_plazo=0  → 321.609 líneas (61.6%)
dias_plazo=30 → 200.157 líneas (38.4%)
(ningún otro valor de dias_plazo aparece en las ventas reales)
```
La matriz de crédito de la propuesta (0/15/30/45/60/90+ días, 7 tramos) **no tiene datos reales para 5 de sus 7 tramos** — `edw.dim_formapago` en este EDW solo diferencia contado (0) y crédito a 30 días. **Decisión:** se implementa la tabla `comision_factores_credito` completa (config abierta, por si el ERP usa más formas de pago en el futuro o en otras empresas), pero el **piloto en sombra solo tendrá señal real en 2 tramos** (`0` y `1-30`). Se documenta como limitación conocida, no como bloqueo — el factor de 30 días (0.85) queda como el único ajuste con datos reales en fase 1; los tramos de 45/60/90+ son configuración latente sin tráfico actual.

### H5 — Descuento: 68% de las líneas tienen descuento > 0
```
con_descuento = 355.094 / 521.766 (68.1%)
```
Confirma que la salvaguarda 1 (tope de descuento sin aprobación) es relevante y debe implementarse desde la Fase 2, no diferirse — hay volumen real de descuentos que podría interactuar con el tope del 30%.

## Decisiones que se incorporan al diseño técnico

1. Clasificación por código `clase`/`subclase` (H2), con etiqueta legible mantenida en la tabla de configuración, no en el EDW.
2. Perfil de margen por categoría usa razón agregada `SUM/SUM`, no promedio de razones por línea (H3).
3. Umbral configurable `COMISION_UMBRAL_SUBTOTAL_X` para clasificar líneas de valor casi nulo como grupo X (generaliza H8 de auditoría 07).
4. El factor de crédito, en su lanzamiento real (fase piloto), tiene cobertura de datos solo para contado y 30 días (H4) — se documenta explícitamente en el dashboard de simulación para no sobre-prometer a gerencia un ajuste fino que el ERP no soporta hoy.
5. Salvaguarda de descuento (tope 30%) se prioriza igual que margen/crédito por el volumen real encontrado (H5).

## Reglas de negocio nuevas (para `docs/auditoria/02_reglas_negocio_validadas.md` §18)

- **RN-CM1:** la comisión variable se calcula sobre `margen_bruto` de la línea (grupos A/B/C) o `subtotal_neto` (grupo S — servicios, y líneas con `subtotal_neto < COMISION_UMBRAL_SUBTOTAL_X` reclasificadas a grupo X con tasa 0).
- **RN-CM2:** la clasificación de categorías usa el código `dim_producto.clase`/`subclase`, nunca `nombre_clase` (vacío en el 100% de los productos vigentes al momento de esta auditoría).
- **RN-CM3:** el perfil de margen por categoría se calcula como `SUM(margen_bruto)/SUM(subtotal_neto)` agregado, no como promedio de la razón por línea (evita distorsión por líneas de valor casi nulo).
- **RN-CM4:** el factor de crédito se resuelve por `dim_formapago.dias_plazo` de la línea; en el EDW actual solo hay tráfico real en 0 y 30 días — los demás tramos de la matriz son configuración sin datos históricos que la validen todavía.

## Estado

Sin bloqueos para iniciar Fase 1/2 de implementación. Los hallazgos H2–H4 se incorporan como correcciones de diseño (no como impedimentos) al `plan_integracion_comisiones_variables.md`.
