# Plan de Integración: Módulo de Metas y Comisiones Variables

> **Fecha:** 2026-07-14
> **Estado:** plan de implementación aprobable (consolida `nueva_propuesta_comision.md` y `propuesta_sistema_comisiones_variables.md`).
> **Alcance:** evolución del módulo Metas y Comisiones existente hacia comisión sobre **margen bruto** por categoría, ajustada por crédito y tipo de vendedor, con piloto en sombra y rollback garantizado.
> **Prerequisito de flujo:** antes de tocar código se crea el reporte `docs/auditoria/30_comisiones_variables.md` (flujo estándar del CLAUDE.md).

---

## 1. Objetivo

Reemplazar (de forma gradual y reversible) la comisión de **tasa plana sobre Venta Neta por tramos** (`backend/app/services/commission_engine.py`) por la fórmula:

```
Comisión mes = [ Σ líneas: base_comisionable × tasa_categoría × factor_estratégico × factor_crédito ]
               × factor_tipo_vendedor
               × multiplicador_cumplimiento(meta)          ← se REUTILIZA el motor de tramos actual
               − devoluciones_del_mes (comisión asociada)
               + bonos (venta cruzada, cliente nuevo/reactivado, cobranza sana)
               , con piso 0 (nunca negativa)
```

donde `base_comisionable` = `margen_bruto` de la línea (categorías A/B/C) o `subtotal_neto` (categorías S y líneas sin costo).

## 2. Estado actual (qué existe y se reutiliza)

| Componente | Archivo | Se reutiliza |
|---|---|---|
| Motor de tramos (EXCELENTE/META/CERCA/LEJOS) | `backend/app/services/commission_engine.py` — `calcular_nivel`, `calcular_comision` | **Sí, intacto.** `calcular_nivel` pasa a ser el multiplicador de cumplimiento del nuevo motor; `calcular_comision` (plano) queda como fallback de rollback. |
| Servicio de liquidación | `backend/app/services/commission_service.py` (`get_commission_tracking`, `get_my_commission`, `get_post_goal_invoices`) | Sí — se extiende para calcular ambos esquemas (plano + variable) según el modo configurado. |
| Acceso a datos de metas/ventas | `backend/app/repositories/goal_repository.py` (Venta Neta = ventas − devoluciones, patrón de CTEs separados) | Sí — se agregan consultas nuevas de desglose por línea/categoría/crédito con el mismo patrón. |
| Generación de metas (IQR + tendencia) | `GoalMLService.generate_proposals` + `IQRGoalCalculationEngine` | Sí — solo se agrega el ajuste por tipo de vendedor (×1.1 externo / ×0.95 interno / 60% promedio equipo para nuevos). |
| Endpoints | `backend/app/api/routes/goals.py` (`/gerencia/goals/*`), rutas del vendedor en `/analytics/ventas` | Sí — se agregan endpoints, no se cambia contrato de los existentes. |
| Frontend | `DashboardMetas.tsx` (gerencia), `DashboardMetasVendedor.tsx` ("Mi Comisión") | Sí — se enriquecen con desglose y modo dual (sombra). |
| Telemetría de venta cruzada | `public.recomendaciones_eventos` (auditoría 25, evento `aceptada`) | Sí — insumo del Bono 1. |
| RFM/churn | `kmeans_rfm_model` / `churn_classifier` (vía `PredictionService`) | Sí — insumo del Bono 2 (cliente reactivado). |

### Datos disponibles en el EDW (verificado contra los DDL)

| Necesidad de la propuesta | Fuente verificada | Estado |
|---|---|---|
| Margen bruto por línea | `edw.fact_ventas_detalle.margen_bruto` (NULL cuando `costo_total` es NULL — salvaguarda 2) | ✅ |
| Descuento por línea | `fact_ventas_detalle.valor_descuento` | ✅ |
| Categoría del producto | `edw.dim_producto.clase`/`nombre_clase`, `subclase`, `es_servicio` | ✅ |
| Plazo de crédito de la venta | `fact_ventas_detalle.formapago_sk` → `edw.dim_formapago.dias_plazo` | ✅ (plazo teórico) |
| Pago real / mora | `edw.fact_cobros_cxc` (`valor_cobrado`, `saldo_documento`, `dias_vencimiento`, `esta_vencido`) | ✅ parcial — ver brecha B4 |
| Devoluciones por vendedor/mes | `edw.fact_devoluciones` | ✅ |
| Solo documentos válidos | `dim_estado_documento` (`estado_documento_sk <> -1`, patrón ya usado en `GoalRepository`) | ✅ |
| Venta cruzada aceptada | `public.recomendaciones_eventos` | ✅ |

### Brechas de datos (condicionan el alcance)

| # | Brecha | Impacto | Decisión del plan |
|---|---|---|---|
| B1 | `edw.dim_vendedor` **no tiene tipo externo/interno** ni fecha de ingreso | Factor 0.70 interno y metas diferenciadas no son calculables desde el EDW | Tabla de configuración `public.comision_config_vendedor` mantenida por gerencia (no se toca el EDW ni el ETL en fase 1). |
| B2 | No existen **cotizaciones/CRM** en el EDW | Ventas compartidas Opción A (80/20 con cotización previa) no es implementable hoy | Se **difiere** (fase futura). Se deja el hook: campo `regla_reparto` en la config, default `100% quien factura`. |
| B3 | No hay **geolocalización/plan de visitas** | Bono 4 (visitas de externos) no medible | Se **excluye** del alcance; documentado como dependencia de un CRM futuro. |
| B4 | `fact_cobros_cxc` no enlaza cobro → `num_factura` de venta de forma garantizada, y no hay hecho de **incobrables/castigos** | El split "X% al facturar / Y% al cobrar" y la reversión por incobrable no pueden liquidarse por factura exacta | Fase 1–2: el factor crédito usa el **plazo teórico** (`dim_formapago.dias_plazo`). El recálculo por pago real y la reversión por incobrable se implementan en fase 2 con una aproximación por vendedor (días promedio de cobro del mes desde `fact_cobros_cxc`) y se valida en el piloto. |
| B5 | Líneas sin costo (`costo_unitario IS NULL`, auditoría 08 F2) | Sin margen calculable | Salvaguarda 2: tasa mínima sobre el valor + reporte a gerencia (endpoint `/lineas-sin-costo`). |

## 3. Diseño técnico

### 3.1 Nuevas tablas de configuración (`public.*`, NO se toca el esquema `edw`)

Se crean vía modelos SQLAlchemy (`Base.metadata.create_all`, mismo mecanismo que `metas_comerciales_operativas`) + DDL espejo en `edw/07_tablas_public.sql` para volúmenes nuevos.

```sql
-- Matriz de categorías y tasas (el corazón negociable). Vigencias para historial.
CREATE TABLE public.comision_matriz_categorias (
    id                 SERIAL PRIMARY KEY,
    clase              VARCHAR(5)  NOT NULL,      -- edw.dim_producto.clase; '*' = default
    subclase           VARCHAR(5),                -- NULL = toda la clase
    grupo              VARCHAR(1)  NOT NULL,      -- 'A'|'B'|'C'|'S'|'X'
    tasa_pct           NUMERIC(6,3) NOT NULL,     -- sobre la base
    base               VARCHAR(10) NOT NULL DEFAULT 'margen',  -- 'margen'|'valor'
    factor_estrategico NUMERIC(4,2) NOT NULL DEFAULT 1.0,      -- 1.0–1.5, temporal
    vigente_desde      DATE NOT NULL,
    vigente_hasta      DATE,                      -- NULL = vigente
    creado_por         INT REFERENCES public.usuarios(id),
    fecha_creacion     TIMESTAMP DEFAULT NOW()
);

-- Factores por plazo de crédito (matriz negociable §4 de la propuesta).
CREATE TABLE public.comision_factores_credito (
    id             SERIAL PRIMARY KEY,
    dias_desde     INT NOT NULL,                  -- 0, 1, 16, 31, 46, 61, 91
    dias_hasta     INT,                           -- NULL = sin tope
    factor         NUMERIC(4,2) NOT NULL,         -- 1.00 … 0.50
    pct_al_facturar NUMERIC(5,2) NOT NULL,        -- 100, 80, 70, … (fase 2)
    vigente_desde  DATE NOT NULL,
    vigente_hasta  DATE
);

-- Tipo y parámetros por vendedor (cubre brecha B1).
CREATE TABLE public.comision_config_vendedor (
    id                 SERIAL PRIMARY KEY,
    id_vendedor_origen VARCHAR(10) NOT NULL UNIQUE,  -- = dim_vendedor.codven
    tipo               VARCHAR(10) NOT NULL DEFAULT 'externo',  -- 'externo'|'interno'
    factor_tipo        NUMERIC(4,2) NOT NULL DEFAULT 1.0,       -- externo 1.0 / interno 0.70
    fecha_ingreso      DATE,                       -- para regla "vendedor nuevo" (3 meses, 60% promedio)
    activo             BOOLEAN DEFAULT TRUE
);

-- Snapshot de liquidación (piloto en sombra y cierre mensual): congela el cálculo.
CREATE TABLE public.comision_liquidaciones (
    id                 SERIAL PRIMARY KEY,
    anio               INT NOT NULL,
    mes                INT NOT NULL,
    id_vendedor_origen VARCHAR(10) NOT NULL,
    esquema            VARCHAR(10) NOT NULL,       -- 'plana'|'variable'
    modo               VARCHAR(10) NOT NULL,       -- 'sombra'|'oficial'
    comision_total     NUMERIC(15,4) NOT NULL,
    detalle_json       JSONB NOT NULL,             -- desglose línea/categoría/crédito/bonos (transparencia total)
    fecha_calculo      TIMESTAMP DEFAULT NOW(),
    UNIQUE (anio, mes, id_vendedor_origen, esquema, modo)
);
```

Parámetros globales en `backend/app/core/config.py` (env vars, sin hardcodes):

| Setting | Default | Uso |
|---|---|---|
| `COMISION_MODO` | `"plana"` | `plana` \| `sombra` (calcula ambas, paga plana) \| `variable`. **Este flag ES el rollback.** |
| `COMISION_TOPE_DESCUENTO_PCT` | `30.0` | Salvaguarda 1: línea con descuento mayor no comisiona sin aprobación. |
| `COMISION_TASA_MINIMA_SIN_COSTO_PCT` | `5.0` | Salvaguarda 2: líneas sin costo comisionan sobre valor. |
| `COMISION_BONO_CLIENTE_NUEVO` | `50.0` | Bono 2 (monto fijo). |
| `COMISION_BONO_CROSS_SELL_PCT` | `5.0` | Bono 1 (% sobre la línea aceptada). |
| `COMISION_BONO_COBRANZA_PCT` / `COMISION_BONO_COBRANZA_DIAS` | `5.0` / `30` | Bono 3. |
| `COMISION_MESES_CLIENTE_REACTIVADO` | `6` | Ventana de inactividad del Bono 2. |
| `COMISION_PISO_LEJOS` | `0.0` | Multiplicador del tramo LEJOS (negociable: 0.0 hoy, 0.3–0.4 propuesto). |

Los umbrales de tramos ya existentes (`UMBRAL_EXCELENTE/META/CERCA`, 1.2/1.0/0.7) se promueven de constantes del engine a settings `COMISION_MULT_*` para que la negociación con gerencia no requiera código.

### 3.2 Motor de cálculo (`commission_engine.py`, extensión pura)

Nueva función **pura** que convive con `calcular_comision` (patrón del engine actual: sin BD, testeable en unitarios):

```python
@dataclass(frozen=True)
class LineaComisionable:      # una fila del repo, ya resuelta
    codart: str; clase: str; subclase: str | None; es_servicio: bool
    subtotal_neto: float; margen_bruto: float | None; valor_descuento: float
    dias_plazo: int; descuento_aprobado: bool

def calcular_comision_variable(
    lineas: list[LineaComisionable],
    matriz: MatrizCategorias,            # resuelta por vigencia
    factores_credito: FactoresCredito,
    factor_tipo_vendedor: float,
    venta_real: float, monto_meta: float,   # para el tramo (reutiliza calcular_nivel)
    devoluciones_mes: float,
    bonos: BonosCalculados,
    config: ComisionConfig,              # topes/tasas mínimas/multiplicadores
) -> ComisionVariableCalculada:          # incluye desglose línea a línea (transparencia total)
```

Reglas internas (cada una con test unitario):
1. Clasificación de línea: `es_servicio` o `desinv='N'` → grupo S (base = valor); `pct_margen = 0`/precio 0 → grupo X (tasa 0); `margen_bruto IS NULL` → salvaguarda 2 (tasa mínima sobre valor, se marca `sin_costo=True` en el desglose); resto → grupo por matriz (`clase`/`subclase`, match más específico gana).
2. Descuento > tope y no aprobado → comisión de línea = 0, marcada `pendiente_aprobacion`.
3. `factor_credito` por `dias_plazo` (búsqueda en rangos vigentes).
4. Multiplicador de cumplimiento: reutiliza `calcular_nivel`; LEJOS usa `COMISION_PISO_LEJOS`.
5. Devoluciones: se resta la comisión estimada de las devoluciones del mes (monto devuelto × tasa promedio ponderada del vendedor) — simple, del mes en que ocurren, no reabre liquidaciones.
6. `max(0.0, resultado)` — nunca negativa.

### 3.3 Repositorio (`GoalRepository` + `CommissionConfigRepository` nuevo)

- `get_commission_lines(vendedor_origen, anio, mes)`: líneas de `fact_ventas_detalle` (solo `estado_documento_sk <> -1`, patrón existente) JOIN `dim_producto` (clase/subclase/es_servicio) JOIN `dim_formapago` (dias_plazo), con `margen_bruto`, `subtotal_neto`, `valor_descuento`. Grano línea — es la consulta central del módulo.
- `get_margin_profile_by_category(meses=24)`: perfil margen/volumen/№ vendedores por clase/subclase (Fase 1 de análisis, y el clasificador automático A/B/C).
- `get_vendor_credit_profile(anio, mes)`: % ventas a crédito, plazo promedio, días de cobro promedio (`fact_cobros_cxc`) por vendedor (Bono 3 + análisis).
- `get_new_or_reactivated_clients(vendedor, anio, mes, meses_inactividad)`: clientes del mes sin compras en N meses previos (Bono 2).
- `get_cross_sell_accepted_amount(vendedor, anio, mes)`: desde `public.recomendaciones_eventos` `aceptada` (Bono 1).
- `get_lines_without_cost(anio, mes)`: reporte salvaguarda 2.
- `CommissionConfigRepository`: CRUD de matriz, factores de crédito y config de vendedor (con cierre de vigencias, nunca UPDATE destructivo de una fila vigente).

### 3.4 Servicios

- **`CommissionService` (extendido):** `get_commission_tracking` y `get_my_commission` calculan según `COMISION_MODO`: en `sombra` devuelven **ambos** números (`comision_actual`, `comision_variable`, con desglose); en `variable`, el nuevo como oficial y el plano como referencia. Persisten snapshot en `comision_liquidaciones` al consultarse un período cerrado.
- **`CommissionSimulationService` (nuevo):** simulación retroactiva de N meses × escenarios de matriz (conservador/medio/agresivo) — Fase 2 de la propuesta. Devuelve por vendedor/mes: comisión plana vs. variable, costo total anual, % comisiones/margen bruto (KPI de sanidad). Es solo lectura del EDW: no persiste.
- **`GoalMLService` (ajuste menor):** `generate_proposals` aplica el factor por tipo (×1.1 externo, ×0.95 interno, regla de vendedor nuevo con `fecha_ingreso`) leyendo `comision_config_vendedor`; sin tocar `IQRGoalCalculationEngine`.
- Bonos 1/2 se calculan en `CommissionService` con los repos anteriores; el Bono 2 puede cruzar con la segmentación RFM existente (`PredictionService`) solo como enriquecimiento visual, no como dependencia dura (si el modelo cae, el bono se calcula igual por recencia SQL — patrón de degradación del proyecto).

### 3.5 Endpoints (prefijo `/api/v1`, RBAC con `PermissionChecker` existente)

| Endpoint | Método | Rol | Propósito |
|---|---|---|---|
| `/gerencia/goals/commissions` | GET | gerencia/admin | **Existente** — se extiende la respuesta con los campos del esquema variable (aditivo, no rompe contrato). |
| `/gerencia/goals/commission-config/matriz` | GET/POST/PUT | gerencia/admin | CRUD de `comision_matriz_categorias` (con vigencias). |
| `/gerencia/goals/commission-config/credito` | GET/PUT | gerencia/admin | Matriz de factores por plazo. |
| `/gerencia/goals/commission-config/vendedores` | GET/PUT | gerencia/admin | Tipo externo/interno y `fecha_ingreso` por vendedor. |
| `/gerencia/goals/commission-simulation` | POST | gerencia/admin | Simulación retroactiva (meses, escenarios) — Fase 2. |
| `/gerencia/goals/commission-analysis/categorias` | GET | gerencia/admin | Perfil de margen 24 meses + clasificación A/B/C/S/X propuesta — Fase 1. |
| `/gerencia/goals/lineas-sin-costo` | GET | gerencia/admin | Reporte salvaguarda 2 (corregir costo en SAP). |
| `/gerencia/goals/{goal_id}/aprobar-descuento` | PUT | gerencia/admin | Aprobación de líneas con descuento > tope (salvaguarda 1). |
| `/analytics/ventas/mi-comision` | GET | ventas | **Existente** — se extiende con desglose por categoría/crédito y modo dual sombra. |

Los servicios lanzan excepciones de dominio (`app/core/exceptions.py`), nunca `HTTPException`; inyección vía `app/api/dependencies.py` (convención del proyecto).

### 3.6 Frontend

- **`DashboardMetasVendedor.tsx` ("Mi Comisión"):** tarjeta dual en modo sombra ("Hoy: $X — Con el sistema nuevo habrías ganado: $Y"), desglose por categoría (tabla A/B/C/S/X con tasa y comisión), detalle línea a línea expandible (producto, margen, tasa, factor crédito, marcas `sin_costo`/`pendiente_aprobacion`), bonos y devoluciones (salvaguarda 6: transparencia total).
- **`DashboardMetas.tsx` (gerencia):** columnas nuevas en la tabla de liquidación (comisión variable, % comisión/margen), pestaña de **configuración de la matriz** (editable sin programar) y pestaña de **simulación** (escenarios, costo anual, impacto por vendedor).
- Nuevos: `src/services/commissionConfigService.ts`, tipos en `src/types/commission.ts`, hooks TanStack Query. Sin páginas nuevas: se extienden las dos existentes (el patrón de página propia tipo `/ventas/cross-selling` no aplica porque el módulo ya tiene sus páginas).

## 4. Fases de ejecución

### Fase 0 — Auditoría previa (0.5 día) — obligatoria por flujo del proyecto
- Crear `docs/auditoria/30_comisiones_variables.md`: alcance, brechas B1–B5, decisiones, y validación por SELECT contra el EDW de los supuestos de datos (distribución de `margen_bruto` NULL, cobertura de `dias_plazo` en `dim_formapago`, % líneas `es_servicio`).
- Registrar reglas nuevas en `docs/auditoria/02_reglas_negocio_validadas.md` §18 (RN-CM1..CMn) al cierre de cada fase.

### Fase 1 — Análisis histórico con el EDW (1 semana)
- Implementar `get_margin_profile_by_category` + endpoint `/commission-analysis/categorias`.
- Entregable: informe con clasificación A/B/C/S/X real (margen promedio, % de la venta, № vendedores, descuento promedio por categoría; perfil de crédito por vendedor). Los datos alimentan la matriz por defecto que se siembra en `comision_matriz_categorias`.

### Fase 2 — Motor + simulación retroactiva (1–1.5 semanas)
- Tablas de configuración + seeds (matriz por defecto de la Fase 1, factores de crédito de la propuesta §4, todos los vendedores como `externo` factor 1.0 hasta que gerencia clasifique).
- `calcular_comision_variable` (puro) + tests unitarios exhaustivos (los 3 casos numéricos de la propuesta §4 y el ejemplo completo §9 como casos de test).
- `CommissionSimulationService` + endpoint de simulación.
- Entregable: tabla comparativa 12 meses "qué habría pasado" por escenario — el argumento para gerencia.

### Fase 3 — Presentación y negociación (1–2 sesiones, sin desarrollo)
- Insumos: salidas de Fases 1–2. Preguntas cerradas (tasas finales, piso LEJOS, factor interno, split cobranza, tope descuento, presupuesto % margen).
- Entregable: acta → los valores acordados se cargan como **configuración** (matriz + settings), no como código.

### Fase 4 — Piloto en sombra (2–3 meses calendario; desarrollo 1 semana)
- `COMISION_MODO=sombra`: `CommissionService` calcula ambos esquemas; snapshots en `comision_liquidaciones`; frontend dual en ambos dashboards.
- Bonos 1–3 y salvaguardas 1–6 activos en el cálculo sombra.
- Monitoreo de criterios de salida: <5% líneas sin costo, costo total dentro de presupuesto, ningún vendedor pierde >15% sin causa, feedback ≥70%.

### Fase 5 — Activación (1 semana, tras aprobación)
- `COMISION_MODO=variable`. El esquema plano sigue calculándose como referencia y **el rollback es cambiar una env var** (minutos, sin migración).
- Fase 2 del crédito (si gerencia lo aprueba): split al facturar/cobrar y recálculo por pago real usando `fact_cobros_cxc` (aproximación por vendedor documentada en B4); reversión por incobrable queda condicionada a que el ERP exponga castigos de cartera (validar con SELECT en la auditoría).

### Diferido explícitamente (fuera de alcance)
- Ventas compartidas Opción A (requiere cotizaciones/CRM — B2).
- Bono de visitas para externos (requiere geolocalización — B3).
- Salvaguarda 5 (ajuste por churn de clientes del vendedor): se evalúa en el piloto; el dato es derivable del EDW pero la regla es sensible y necesita validación de gerencia.

## 5. Mapeo de salvaguardas → implementación

| Salvaguarda | Implementación | Fase |
|---|---|---|
| 1. Descuento > tope | `valor_descuento`/`subtotal_neto` por línea; marca `pendiente_aprobacion`; endpoint de aprobación | 2 |
| 2. Líneas sin costo | `margen_bruto IS NULL` → tasa mínima sobre valor + endpoint `/lineas-sin-costo` | 2 |
| 3. Devoluciones | `fact_devoluciones` del mes descuenta; piso $0 | 2 |
| 4. Anulaciones | Ya cubierto: filtro `dim_estado_documento` en todas las consultas del repo | — |
| 5. Churn del vendedor | Diferido al piloto | 4+ |
| 6. Transparencia total | `detalle_json` del snapshot + desglose línea a línea en "Mi Comisión" | 2/4 |

## 6. Testing y validación

1. **Unitarios** (`backend/tests/unit/test_commission_engine.py`, extendido): clasificación de líneas, factores de crédito por rango, tope de descuento, línea sin costo, piso $0, y los ejemplos numéricos de las propuestas como golden tests (ej. §9: comisión final $166.90).
2. **Integración** (`backend/tests/integration/`): endpoints nuevos con RBAC (gerencia sí / ventas no en config; vendedor solo ve su comisión).
3. **Validación de datos** (auditoría 30, solo SELECT): reconciliar `SUM(margen_bruto)` del EDW vs. venta−costo de SAP en un mes de muestra; verificar que `dias_plazo` de `dim_formapago` refleja los plazos reales del ERP.
4. **KPI de sanidad del piloto:** % comisiones/margen bruto mensual (objetivo 15–20%) expuesto en la simulación y el tracking gerencial.

## 7. Riesgos y mitigaciones

| Riesgo | Mitigación |
|---|---|
| Costos mal cargados en SAP distorsionan el margen | Salvaguarda 2 + reporte; criterio de salida del piloto (<5% líneas sin costo). |
| Rechazo de vendedores | Piloto en sombra + simulación personal de 12 meses + dashboard dual. |
| `dias_plazo` de `dim_formapago` no refleje el plazo real pactado | Validar por SELECT en auditoría 30; si es débil, el factor crédito arranca informativo en sombra. |
| Config incorrecta de la matriz rompe la liquidación | Vigencias (nunca se edita historia), snapshots congelados en `comision_liquidaciones`, validación Pydantic de rangos (tasa 0–20%, factores 0.5–1.5). |
| Regresión del esquema actual | El motor plano no se toca; `COMISION_MODO=plana` es el default y el rollback. |

## 8. Decisiones pendientes de gerencia (se llevan como opciones cerradas — Fase 3)

| Parámetro | Opciones | Default del piloto |
|---|---|---|
| Tasas A/B/C | 10/7/4 · 13/9/5 · 15/11/6 | 13/9/5 (medio) |
| Tasa S (sobre valor) | 5% · 6% · 8% | 6% |
| Piso tramo LEJOS | 0 · 0.3 · 0.4 | 0 (comportamiento actual) |
| Factor interno | 0.70 · 0.75 · 0.80 | 0.70 |
| Split cobranza | 80/20 · 70/30 · sin split | Sin split en fase 1 (solo factor) |
| Tope descuento comisionable | 20% · 25% · 30% | 30% |
| Presupuesto comisiones (% margen) | lo define gerencia con la simulación | 15–20% |
