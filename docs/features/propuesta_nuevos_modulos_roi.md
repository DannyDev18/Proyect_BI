# Propuesta de Nuevos Módulos por Rol — Enfoque ROI

> **Fecha:** 2026-07-13
> **Base del análisis:** data realmente cargada en el EDW (11 hechos, 11 dimensiones) y qué
> consume hoy cada dashboard. Las propuestas priorizan hechos **ya cargados y hoy sin explotar**:
> máximo retorno con mínimo esfuerzo de datos (sin ETL nuevo).
> **Estado:** PROPUESTA — cada módulo aprobado seguiría el flujo estándar (auditoría en
> `docs/auditoria/` antes de codificar, validación SELECT, contrato-primero si lleva ML).

---

## 1. Punto de partida: la data que ya se paga y no se usa

| Tabla de hechos del EDW | Volumen | ¿Algún dashboard la consume hoy? |
|---|---|---|
| `fact_ventas_detalle` | ~539k | ✅ Intensivamente (todos los roles) |
| `fact_movimientos_inventario` | ~948k | ✅ Bodega |
| `fact_inventario_snapshot` | parcial (<1% histórico pre-2026) | ✅ Bodega |
| `fact_devoluciones` | — | ✅ Venta neta (Gerencia/Metas) |
| `fact_compras` | — | ⚠️ Marginal (solo para inferir proveedor de un artículo) |
| **`fact_cobros_cxc`** | — | ❌ **Sin uso** |
| **`fact_pagos_cxp`** | — | ❌ **Sin uso** |
| **`fact_movimientos_caja`** | — | ❌ **Sin uso** |
| `fact_nomina` | — | ❌ Sin uso (sensible, ver §6) |
| `fact_logs_auditoria` | — | ✅ Admin (anomalías) |
| `fact_metas_comerciales` | vacía | ❌ (hallazgo abierto aud. 05) |

**Lectura ejecutiva:** el ETL ya extrae, transforma y carga el ciclo financiero completo
(vender → cobrar → comprar → pagar → caja), pero la plataforma solo muestra el primer eslabón.
Los tres módulos propuestos cierran ese ciclo, uno por rol.

---

## 2. MÓDULO GERENCIA — Cartera y Flujo de Caja (CxC / CxP)

### 2.1 Problema de negocio

Hoy Gerencia ve *cuánto se vende*, pero no *cuándo entra el dinero*. En una empresa
multisucursal que vende a crédito, la utilidad contable puede coexistir con problemas de
liquidez: cartera envejecida, clientes que compran pero no pagan, y pagos a proveedores
desincronizados de los cobros. Ninguna pantalla actual responde: *"¿cuánta caja tendré en 30
días y quién me debe qué?"*.

### 2.2 Qué entregaría

- **KPIs:** DSO (días promedio de cobro), DPO (días promedio de pago), brecha de capital de
  trabajo (DSO − DPO), % de cartera vencida, índice de morosidad por sucursal.
- **Aging de cartera:** cascada 0-30 / 31-60 / 61-90 / +90 días, drill-down a cliente
  (anonimizado en EDW; nombre real vía el mecanismo `cliente_lookup` existente, solo para
  roles autorizados).
- **Proyección de cobros a 30/60 días:** estadística (patrón de pago histórico por cliente:
  días promedio entre factura y cobro) — sin ML en fase 1; un modelo de probabilidad de pago
  es extensión natural en fase 2.
- **Ranking de cobranza priorizada:** clientes ordenados por (monto vencido × probabilidad de
  deterioro), la lista que Gerencia baja a Ventas cada semana.
- **Vista de caja consolidada:** entradas/salidas de `fact_movimientos_caja` por sucursal y
  mes, cruzada con la proyección de cobros.

### 2.3 Casos de uso

| Actor | Caso de uso | Decisión que habilita |
|---|---|---|
| Gerente | Revisa DSO mensual por sucursal | Detectar la sucursal que vende bien pero cobra mal |
| Gerente | Consulta aging antes del comité semanal | Priorizar gestión de cobranza; frenar crédito a clientes +90 días |
| Gerente | Proyección de cobros vs pagos CxP del mes | Decidir si diferir compras o negociar plazos con proveedores |
| Gerente | Cruza churn (módulo existente) con cartera | Distinguir cliente en fuga vs cliente moroso — acciones distintas |

### 2.4 Justificación ROI

- **Mecanismo principal — liberar capital de trabajo:** cada día de reducción del DSO libera
  caja ≈ `venta a crédito diaria promedio × 1 día`. Con la venta anual del EDW se calcula el
  valor exacto; la literatura de cobranza gestionada sitúa reducciones alcanzables de 5–10 días
  de DSO solo por visibilidad y priorización (sin cambiar políticas de crédito).
  `ROI ≈ (venta_credito_diaria × dias_DSO_reducidos × costo_capital_anual)` — solo el costo
  financiero; el beneficio de liquidez operativa es adicional.
- **Mecanismo secundario — reducir incobrables:** la probabilidad de cobrar cae con la edad de
  la deuda; detectar a los 30 días en vez de a los 90 mueve cuentas de "dudosa" a "cobrada".
- **Costo:** bajo — la data ya está cargada; es SQL de agregación + un dashboard (sin ETL
  nuevo, sin ML en fase 1). Estimación: 2–3 semanas de desarrollo.

### 2.5 Viabilidad

| Dimensión | Evaluación |
|---|---|
| Datos | 🟢 `fact_cobros_cxc`, `fact_pagos_cxp`, `fact_movimientos_caja`, `fact_ventas_detalle` ya en el EDW. **Validar primero con SELECT:** cobertura temporal de cobros, % de cobros que enlazan a factura (¿existe la llave documento?), y si el saldo de cartera es derivable (facturado − cobrado) o requiere el saldo del ERP como snapshot. Esta es la validación crítica del módulo. |
| Backend | 🟢 Patrón existente: repository → service → router `/analytics/...` con RBAC `gerencia`. |
| Frontend | 🟢 Reutiliza `KpiCard`, `ChartCard`, paginación genérica ya construida. |
| ML | 🟢 No requiere en fase 1 (estadística pura, mismo criterio que Metas). |
| Riesgo principal | 🟡 Que la conciliación factura↔cobro no sea 1:1 en el ERP (pagos parciales, anticipos). Mitigación: el aging se calcula igual a nivel cliente aunque no enlace documento a documento; documentar la regla en auditoría. |

**Veredicto: 🟢 ALTA viabilidad, el mejor ratio ROI/esfuerzo de las tres propuestas.**

---

## 3. MÓDULO BODEGA — Inteligencia de Compras y Proveedores

### 3.1 Problema de negocio

El módulo Bodega actual (auditorías 23/24) ya dice *qué* y *cuánto* comprar (necesidad de
compra, predicción por categoría, transferencias). Pero no dice **a quién comprarle ni valida
si el proveedor cumple**: el punto de reorden usa un lead time configurado
(`BODEGA_*`), no el lead time real observado, y no hay visibilidad de la variación de costos
de compra. La decisión de compra está optimizada a medias: cantidad sí, proveedor y momento no.

### 3.2 Qué entregaría

- **Lead time real por proveedor y artículo:** días entre la compra (`fact_compras`) y la
  entrada al kardex (`fact_movimientos_inventario`, `tipdoc IN ('EN','AC')` — regla de negocio
  3), con promedio y variabilidad. Alimenta el punto de reorden con datos en vez de un default.
- **Scorecard de proveedores:** cumplimiento (lead time prometido vs real), variación de precio
  de compra en el tiempo, concentración (% del gasto en top proveedores → riesgo de dependencia).
- **Inflación de costos por categoría:** evolución del costo unitario de compra vs precio de
  venta → alerta temprana de erosión de margen (insumo que hoy nadie ve).
- **Integración con lo existente:** la pantalla de "necesidad de compra" actual se enriquece
  con columna de proveedor sugerido, lead time esperado y última condición de compra.

### 3.3 Casos de uso

| Actor | Caso de uso | Decisión que habilita |
|---|---|---|
| Encargado de bodega | Consulta lead time real antes de fijar punto de reorden | Stock de seguridad ajustado a la evidencia, no al default |
| Encargado de bodega | Ve que el proveedor A tarda 12 días vs 5 prometidos | Cambiar de proveedor o adelantar pedidos |
| Gerente + Bodega | Scorecard trimestral de proveedores | Renegociar precios/plazos con datos en la mesa |
| Encargado de bodega | Alerta de costo de compra subiendo 3 meses seguidos | Compra anticipada o traslado a precio de venta |

### 3.4 Justificación ROI

- **Mecanismo principal — menos stock de seguridad sin más quiebres:** el stock de seguridad
  crece con la incertidumbre del lead time. Medir el lead time real por proveedor permite
  reducir el colchón donde el proveedor es confiable (capital liberado = valor de inventario
  reducido × costo de capital) y aumentarlo solo donde hace falta (menos ventas perdidas por
  quiebre).
- **Mecanismo secundario — poder de negociación:** el scorecard convierte la renegociación
  anual con proveedores en una conversación con evidencia; un 1–2% de mejora en precio de
  compra sobre el gasto anual de `fact_compras` suele superar el costo del módulo por sí solo.
- **Costo:** medio-bajo. La parte delicada es metodológica: parear compra↔entrada de kardex
  respetando la regla de granularidad (agregar cada hecho por separado, nunca JOIN directo
  entre hechos — patrón documentado en la skill ETL/ML del proyecto). Estimación: 3–4 semanas.

### 3.5 Viabilidad

| Dimensión | Evaluación |
|---|---|
| Datos | 🟡 `fact_compras` y kardex ya cargados. **Validar primero con SELECT:** ¿`fact_compras` tiene número de documento/orden que enlace con la entrada de kardex? Si el pareo documento a documento no existe, el lead time se estima por (proveedor, artículo, fecha más cercana) — menos preciso pero útil; decidir con evidencia en la auditoría. |
| Backend/Frontend | 🟢 Extiende el módulo Bodega existente (router `/analytics/bodega`, mismos permisos y paginación). |
| ML | 🟢 No requiere; el forecast de demanda existente (`demand_rf`) ya aporta el otro insumo de la ecuación de reorden. |
| Riesgo principal | 🟡 Calidad del pareo compra↔entrada (el ERP no expone estado de la orden, limitación conocida — misma clase de límite que en transferencias, regla de negocio 4). |

**Veredicto: 🟢 viabilidad ALTA-MEDIA; ROI alto si el gasto en compras es significativo (lo es: alimenta ~948k movimientos de inventario).**

---

## 4. MÓDULO VENTAS — Cartera de Clientes 360 (retención accionable)

### 4.1 Problema de negocio

El vendedor hoy tiene piezas sueltas: churn de un cliente si lo consulta, segmento RFM si lo
consulta, recomendaciones si las consulta, metas en su dashboard. No existe la vista que
responde su pregunta diaria: **"¿a qué clientes debo llamar hoy y con qué oferta?"**. La
plataforma tiene los 3 modelos ML de ventas (churn, RFM, asociación) y no los compone en una
acción.

### 4.2 Qué entregaría

- **Lista de trabajo diaria priorizada** (el corazón del módulo): clientes de la cartera del
  vendedor ordenados por `valor histórico × riesgo de fuga`, cada uno con: segmento RFM, días
  sin comprar vs su frecuencia habitual, productos recomendados (módulo cross-selling en
  curso), y — si el módulo de Gerencia §2 se construye — su saldo vencido (un cliente moroso
  recibe gestión de cobro, no oferta).
- **Detección de caída de frecuencia:** cliente que compraba cada 15 días y lleva 45 → alerta
  antes de que el churn sea irreversible (deriva de `fact_ventas_detalle`, sin ML nuevo:
  comparación contra su propio patrón).
- **Registro de gestión:** el vendedor marca el resultado de cada contacto (contactado /
  recompró / perdido) — tabla `public.*` nueva, misma filosofía que la telemetría del módulo
  cross-selling. Esto crea el dato de efectividad que hoy no existe y alimenta mejoras futuras.
- **Panel del supervisor (Gerencia):** tasa de recuperación por vendedor, valor recuperado.

### 4.3 Casos de uso

| Actor | Caso de uso | Decisión que habilita |
|---|---|---|
| Vendedor | Abre su lista al iniciar el día | A quién llamar primero y con qué producto |
| Vendedor | Alerta de cliente AAA con caída de frecuencia | Contacto proactivo antes de perderlo |
| Vendedor | Ve recomendaciones al preparar visita | Aumentar ticket con venta cruzada dirigida |
| Gerencia | Tasa de recuperación mensual por vendedor | Coaching, redistribución de cartera |

### 4.4 Justificación ROI

- **Mecanismo principal — retención:** retener es más barato que adquirir (5–7× en la
  literatura comercial). El valor en riesgo se calcula directo del EDW:
  `Σ(venta anual de clientes con churn alto)`. Si la gestión proactiva recupera 10–20% de ese
  valor, el retorno se mide en ventas reales — y queda medido por el registro de gestión.
- **Mecanismo secundario — productividad del vendedor:** sustituye la selección intuitiva de a
  quién visitar por priorización con datos; el mismo tiempo de vendedor produce más contactos
  de alto valor.
- **Costo:** bajo-medio — **no requiere ningún modelo ML nuevo**; es composición de los tres
  existentes + estadística de frecuencia + una tabla de gestión. Estimación: 2–3 semanas
  (después del módulo cross-selling, que le aporta las sugerencias).

### 4.5 Viabilidad

| Dimensión | Evaluación |
|---|---|
| Datos | 🟢 Todo en el EDW; cartera del vendedor derivable de `fact_ventas_detalle` × `dim_vendedor` (mismo criterio de grano vendedor validado en Metas, auditoría 19). |
| ML | 🟢 Reutiliza `churn`, `segmentation`, `association` ya servidos por `ModelLoader`. |
| Backend/Frontend | 🟢 Router `/analytics/ventas` existente; RBAC `vendedor_checker` con filtro por vendedor ya resuelto (patrón de Metas). |
| PII | 🟡 La lista muestra nombres reales → usar exclusivamente el mecanismo `cliente_lookup` existente (regla de negocio 8); nunca exponer `dim_cliente` sin des-anonimizar por el canal autorizado. |
| Riesgo principal | 🟡 Adopción: si el vendedor no registra la gestión, no se mide el ROI. Mitigación: registro de 1 clic y KPI visible para el supervisor. |

**Veredicto: 🟢 ALTA viabilidad; es el módulo que convierte los modelos ML ya pagados en acción comercial medible. Secuenciar después del cross-selling.**

---

## 5. Comparativa y hoja de ruta sugerida

| Módulo | Rol | Data nueva requerida | ML nuevo | Esfuerzo | Mecanismo ROI dominante | Prioridad sugerida |
|---|---|---|---|---|---|---|
| Cartera y Flujo de Caja | Gerencia | Ninguna (hechos ya cargados) | No | 2–3 sem | Capital de trabajo liberado (DSO) | **1º** |
| Cartera de Clientes 360 | Ventas | Tabla de gestión en `public.*` | No (compone 3 existentes) | 2–3 sem | Retención de venta en riesgo | **2º** (tras cross-selling) |
| Compras y Proveedores | Bodega | Ninguna (validar pareo compra↔kardex) | No | 3–4 sem | Menos stock de seguridad + negociación | **3º** |

Secuencia razonada: (1) Gerencia primero porque no depende de nada y su validación de datos es
la más simple; (2) Ventas 360 después del módulo cross-selling en curso, al que compone; (3)
Bodega al final porque su validación de pareo documental es la más incierta. Los tres comparten
el mismo esqueleto técnico (repository → service → router → hooks → dashboard) ya probado en el
módulo Bodega actual, lo que reduce el riesgo de estimación.

## 6. Ideas evaluadas y NO propuestas (con razón)

| Idea | Por qué se descarta hoy |
|---|---|
| Análisis geográfico de ventas | `dim_geografia` está **vacía** (hallazgo abierto aud. 05); requiere primero trabajo de ETL/calidad de datos, no de módulo. |
| Productividad de personal (nómina) | `fact_nomina` existe, pero cruza dato sensible de remuneraciones con desempeño; requiere decisión explícita de la empresa sobre privacidad antes de cualquier diseño. |
| Evolución histórica de inventario | `fact_inventario_snapshot` tiene <1% de histórico pre-2026; el módulo sería honesto recién con 12+ meses de snapshots acumulados. Reevaluar en 2027. |
| Metas por sucursal | Contradice la regla de negocio 10 (grano vendedor, sin sucursal propia en `dim_vendedor`, aud. 19). |
| Más modelos ML por sí mismos | El mayor ROI pendiente no es entrenar modelos nuevos sino **accionar** los existentes (churn/RFM/asociación) y explotar hechos financieros sin uso. |

## 7. Condiciones comunes de arranque (cualquier módulo aprobado)

1. Auditoría previa en `docs/auditoria/` (numeración siguiente libre) con las validaciones
   SELECT de la sección "Datos" de cada módulo — **antes de codificar**.
2. Reglas de negocio nuevas (aging, lead time, prioridad de gestión) documentadas en
   `docs/auditoria/02_reglas_negocio_validadas.md`.
3. Umbrales parametrizados por env vars (patrón `BODEGA_*`), nunca hardcodes.
4. Producción SAP solo lectura; toda métrica se calcula del EDW.
5. Medición de ROI incorporada desde el día 1 (línea base del KPI antes de encender el módulo:
   DSO actual, valor en riesgo actual, días de inventario actuales) — sin línea base no hay
   ROI demostrable en la tesis.
