# Plan — Comisiones sobre Cobros como configuración adicional del esquema Variable

> **Auditoría previa obligatoria:** [`docs/auditoria/44_comisiones_sobre_cobros.md`](../auditoria/44_comisiones_sobre_cobros.md) (H-1 … H-10, verdad de campo feb-2026).
> **Fecha:** 2026-07-30.

## 0. Objetivo y restricciones de diseño

Incorporar al esquema de **Comisiones Variables** la regla realmente vigente en la empresa —comisión sobre **cobranza efectiva**, con tasa por **tramo de días de cobro** y fecha de devengo en la **efectivización** (`banfec`), no en la recepción del cheque— como una **configuración adicional**, sin romper el motor actual por margen/categoría ni el esquema plano.

Restricciones que gobiernan todo el plan:

- **R-1.** Producción es SOLO LECTURA. Todo dato nuevo llega por ETL al EDW; el backend nunca consulta SAP.
- **R-2.** Nada simulado. Todo campo expuesto sale de una consulta real al EDW o de configuración persistida. Sin placeholders (misma restricción que rigió el refactor de Venta Cruzada).
- **R-3.** **Aditivo y reversible.** `COMISION_MODO` sigue siendo el rollback. El componente de cobranza se activa por configuración; apagado, el sistema se comporta exactamente como hoy.
- **R-4.** **La fórmula es editable sin código** (pedido explícito del usuario), pero **no mediante evaluación de expresiones arbitrarias**: se modela como una tubería declarativa de componentes de un catálogo cerrado, con orden y operador configurables. Esto da editabilidad real sin abrir una superficie de ejecución de código en un módulo que mueve dinero.
- **R-5.** Sin hardcodes de negocio: tramos (21/60/90/120/365), tasas por perfil y estructura de la fórmula viven en `public.*`, con vigencia y bitácora, igual que la matriz de categorías.

---

## 1. Fase 1 — ETL/EDW: traer la cobranza al grano correcto

**Cierra H-1, H-2, H-3, H-4.**

### 1.1 Extractor nuevo `etl/extractors/cobros_cuotas_extractor.sql`

Sobre `fp_cxc_cuotas` (la fuente del reporte del ERP), tokenizado con `{CODEMP}` y `{FECHA_DESDE}`:

- `banfec` → fecha de devengo (**la que decide el mes que comisiona**).
- `fectra` → fecha de registro del cobro (se conserva para trazabilidad y para auditar el desfase de postfechados).
- `fecemi`, `fecven` → factura origen (verificado en la auditoría: `fecemi` coincide con la fecha real de la factura, así que **no se replican las 4 subconsultas correlacionadas** del reporte PowerBuilder).
- `tiptra`, `valfor`, `codven`, `codcli`, `numtra`, `ncuota`, `numcco`, `numche`, `bannum`, `codban`, `depositado`.
- Filtro `substring(numcco,1,2) <> 'ND'` **no se aplica en el extractor**: el EDW guarda el hecho completo y la exclusión de notas de débito se decide en la capa de negocio (así el dato queda disponible para análisis y la regla sigue siendo configurable).

### 1.2 Tabla de hechos nueva `edw.fact_cobros_cuotas`

Grano: **un cobro de una cuota de una factura con un instrumento**.

| Columna | Origen / cálculo |
|---|---|
| `fecha_sk` | `banfec` — **devengo** |
| `fecha_registro_sk` | `fectra` |
| `fecha_emision_sk` | `fecemi` |
| `cliente_sk`, `vendedor_sk`, `sucursal_sk` | dims |
| `tipo_instrumento` | `tiptra` — **degenerada (varchar) en el hecho, no FK** |
| `es_postfechado` | `tiptra = 'CP'` |
| `dias_cobro` | `banfec − fecemi`, con piso en 0 (H-9: 12 filas negativas) |
| `valor_cobrado` | `valfor` |
| `num_transaccion`, `num_cuota`, `num_comprobante`, `num_cheque` | trazabilidad |
| `es_nota_debito` | `substring(numcco,1,2) = 'ND'` |

**Decisión de diseño (deliberada):** `tipo_instrumento` se modela como **dimensión degenerada en el hecho**, no como FK a `dim_formapago`. Motivo con evidencia: `dim_formapago` proviene de un extractor estático de 3 filas y hoy deja el **100 % de `fact_cobros_cxc` en el centinela `-1`** (H-2). Repetir ese patrón reintroduciría exactamente el defecto que esta fase corrige. El vocabulario es cerrado y de 7 valores.

`dias_cobro` se **materializa en el ETL** en vez de calcularse en cada consulta: es el discriminante de toda la comisión y así el tramo es auditable sobre el dato cargado.

### 1.3 Registro en el pipeline

Entrada en `PIPELINE_CONFIG` (`loader: fact_inc`, `delta_col: banfec`, `pg_date_col: fecha_sk`, `depende_de: [dim_cliente, dim_vendedor, dim_sucursal]`), después de las dimensiones. `edw/02_dimensiones.sql`/`03_hechos.sql` reciben el DDL; se aplica también manualmente al volumen existente (los DDL de `edw/` solo corren en volumen nuevo).

**Nota de carga (H-9):** `banfec` puede estar en el **futuro** (cheques postfechados; `MAX(banfec)` = 2026-10-01). La carga incremental por `delta_col` debe tolerarlo y el cierre de un período debe filtrar por **rango cerrado**, nunca por `>= inicio`.

### 1.4 `fact_cobros_cxc` no se toca

Se conserva tal cual (la consumen `analytics`/Cartera 360). H-4 queda **documentado, no corregido**: renombrarla o cambiar su semántica está fuera del alcance de este plan y rompería consumidores actuales. La comisión sobre cobros usa exclusivamente la tabla nueva.

---

## 2. Fase 2 — Configuración persistida y editable

**Cierra H-6, H-8, R-4, R-5.** Migración Alembic `0007_comisiones_cobranza`.

### 2.1 `public.comision_tramos_cobranza`

Los tramos y tasas del cuadro de negocio, por **perfil**, con vigencia:

| Columna | |
|---|---|
| `perfil` | `externo` \| `interno` \| `jefe_agencia` |
| `dias_hasta` | `21`, `60`, `90`, `120`, `365`, `NULL` (= sin tope) |
| `tasa_pct` | `2.00`, `1.75`, `0.75`, `0.50`, `0.00` |
| `vigente_desde` / `vigente_hasta` | misma mecánica que la matriz de categorías |

Semilla exacta del documento de negocio: externo 2 / 1.75 / 0.75 / 0.50 / 0.00; jefe de agencia 1 / 1.75 / 0.75 / 0.50 / 0.00. `interno` se siembra igual que `externo` (gerencia lo ajusta; no se inventa una tabla que el negocio no declaró).

### 2.2 `public.comision_formula` + `comision_formula_componente`

La **estructura** de la fórmula deja de estar en código. Una fórmula vigente es una lista **ordenada** de componentes; cada uno declara qué aporta y cómo se combina:

| Campo | |
|---|---|
| `orden` | posición en la tubería |
| `componente` | clave de un **catálogo cerrado** (validado en backend) |
| `operador` | `sumar` \| `restar` \| `multiplicar` |
| `activo` | permite apagar un componente sin borrarlo |
| `parametros` | `jsonb` (p. ej. `{"pct": 1.0}` para el 1 % de contado) |

Catálogo cerrado de componentes:

| Clave | Qué aporta | Operador natural |
|---|---|---|
| `base_lineas_venta` | Σ líneas (margen/valor × tasa × f. estratégico × f. crédito) — **motor actual** | sumar |
| `base_cobranza` | Σ cobros × tasa del tramo de `dias_cobro` — **nuevo** | sumar |
| `contado_agencia` | % sobre ventas de contado (`conpag='E'`) del vendedor en su agencia — **nuevo** | sumar |
| `factor_tipo_vendedor` | `factor_tipo` del vendedor | multiplicar |
| `multiplicador_cumplimiento` | tramo Excelente/Meta/Cerca/Lejos | multiplicar |
| `devoluciones` | devoluciones estimadas del período | restar |
| `bonos` | bonos complementarios (cross-sell, cliente nuevo, cobranza sana) | sumar |

Se siembran **dos fórmulas**: la **actual** (reproduce `calcular_comision_variable` byte a byte, para que la Fase 2 sea un no-op de comportamiento) y la **de cobranza** (`base_cobranza` + `contado_agencia`, sin `base_lineas_venta`), que replica el esquema real de la empresa. Gerencia elige cuál está vigente.

### 2.3 Perfil `jefe_agencia`

`comision_config_vendedor`: se amplía el `CHECK` de `tipo` a `('externo','interno','jefe_agencia')` y se agrega `agencia` (`establ`) para el componente `contado_agencia`.

---

## 3. Fase 3 — Motor de cálculo

**Cierra H-5.** Funciones **puras** en `commission_engine.py`, sin acceso a BD (misma disciplina que el resto del motor):

- `resolver_tramo_cobranza(dias_cobro, tramos) -> tasa_pct` — primer tramo cuyo `dias_hasta` cubre los días; días negativos → tramo mínimo (H-9); sin tramo → 0 %.
- `calcular_comision_cobranza(cobros, tramos) -> ComisionCobranzaCalculada` — con desglose por tramo (montos y comisión por tramo, para que el vendedor vea exactamente lo mismo que el reporte del ERP).
- `evaluar_formula(componentes, aportes) -> ResultadoFormula` — ejecuta la tubería declarativa: acumula `sumar`/`restar`, aplica `multiplicar` sobre lo acumulado, con **piso $0** y traza por paso.

`calcular_comision_variable` se **refactoriza para delegar en `evaluar_formula`** con la fórmula "actual" — mismo resultado, ahora dirigido por configuración. Se conserva su firma para no romper llamadores.

Repositorio: `get_cobros_periodo(vendedor, anio, mes)` sobre `fact_cobros_cuotas` filtrando por `fecha_sk` (= `banfec`) en **rango cerrado** del mes y excluyendo notas de débito; `get_ventas_contado_agencia(vendedor, agencia, anio, mes)` sobre `fact_ventas_detalle` con la condición de contado verificada (**`conpag='E'`**, H-7 — requiere exponer la condición de pago en el hecho de ventas o resolverla vía `dim_formapago`; se resuelve en la fase con el dato real disponible).

---

## 4. Fase 4 — API y frontend

- `GET/PUT /gerencia/goals/commission-config/tramos-cobranza` — CRUD de tramos por perfil.
- `GET/PUT /gerencia/goals/commission-config/formula` — lectura y reemplazo de la fórmula vigente, con validación del catálogo de componentes y de que exista al menos un componente de base activo.
- `GET /analytics/ventas/goals/mi-comision` gana `desglose_cobranza` (por tramo).
- Bitácora: todo cambio pasa por `log_cambio_config` (tabla `comision_config_auditoria` ya existente).
- `CommissionConfigPanel.tsx`: pestañas nuevas **"Tramos de cobranza"** y **"Fórmula"** (editor de la tubería: orden, operador, activo, parámetros), junto a las 4 actuales.

---

## 5. Fase 5 — Validación

- **Caso de aceptación duro:** reproducir la tabla de la auditoría §3 (feb-2026, 11 vendedores) desde el EDW y contra el motor, con tolerancia de centavos. VEN13 = **$963,00**, VEN02 = **$781,78**, total ≈ **$3.717,88**.
- Tests unitarios: tramos (incluidos días negativos y > 365), `evaluar_formula` (orden, operadores, piso $0), fórmula "actual" ≡ `calcular_comision_variable` previa.
- Tests de integración contra el EDW real; `pytest backend/tests/unit`; `tsc`/`oxlint`; reconstrucción de `bi_backend`.

---

## 6. Riesgos

| Riesgo | Mitigación |
|---|---|
| La carga inicial de `fp_cxc_cuotas` requiere una corrida de ETL contra SAP en vivo | Fase 1 se valida con una corrida acotada a esa sola tabla |
| Doble conteo si se activan `base_lineas_venta` y `base_cobranza` a la vez | La fórmula de cobranza sembrada desactiva `base_lineas_venta`; el editor advierte al activar ambas |
| `conpag` no está hoy en `fact_ventas_detalle` | Se resuelve en Fase 3 con el dato real; si no está disponible, `contado_agencia` se entrega desactivado y documentado, nunca con un valor inventado (R-2) |
| Cheques postfechados con `banfec` futuro | Cierre por rango cerrado; documentado en RN nueva |

## 7. Reglas de negocio a documentar (`02_reglas_negocio_validadas.md` §18)

- **RN-CM8** — Devengo de la comisión sobre cobros: `banfec` (efectivización), nunca `fectra`. 47,4 % de los postfechados cruzan de mes.
- **RN-CM9** — Días de cobro = `banfec − fecemi`, piso 0; tramo por primer `dias_hasta` que cubre.
- **RN-CM10** — Instrumento de pago como dimensión degenerada; `dim_formapago` no es utilizable para cobranza.
- **RN-CM11** — Contado = `conpag='E'`; crédito = `conpag='C'` (contraintuitivo, verificado 786/786 vs 0/1493).
- **RN-CM12** — Notas de débito (`numcco` prefijo `ND`) excluidas de la base comisionable.
- **RN-CM13** — La estructura de la fórmula es configuración persistida, no código; catálogo de componentes cerrado.

## 8. Corrección de diseño aplicada (2026-07-30, migración `0009_formula_unica_unificada`)

El diseño original de §2.2 sembraba **dos fórmulas alternativas** (`actual` / `cobranza`) entre las que gerencia "activaba" una u otra. El usuario corrigió esto tras revisar la Fase 4: **las Comisiones Variables son un solo total por vendedor** — margen/categoría, cobranza y contado de agencia se SUMAN, nunca se elige entre un esquema u otro.

Aplicado:

- **Una sola fórmula** (`clave='variable'`), con los 7 componentes combinados en el orden correcto: las 3 bases (`base_lineas_venta`, `base_cobranza`, `contado_agencia`) se suman primero; el total se multiplica por `factor_tipo_vendedor` y `multiplicador_cumplimiento`; al final se resta `devoluciones` y se suma `bonos`. Se retiró por completo el concepto de "activar" (endpoint, servicio, repositorio, hook y UI de selección) — no hay nada que elegir.
- **Motor compartido** (`app/services/commission_variable_engine.py::calcular_comision_variable_completa`): tanto `CommissionService` (cálculo real) como las 3 rutas de `CommissionSimulationService` (`simular`, `reconstruir_mes_especifico`, `proyectar_comision_variable`) delegan en la misma función. Antes el simulador llamaba directo al motor legacy (solo líneas de venta) y nunca reflejaba cobranza ni contado de agencia — el "argumento decisivo" que gerencia ve en el simulador estaba sistemáticamente subestimado.
- **Referencia del bono de cobranza sana, generalizada correctamente:** el acumulado de la tubería justo ANTES del paso `devoluciones` (no antes de `bonos`) — preserva el comportamiento legacy (`comision_post_cumplimiento`) para cualquier combinación de componentes.
- **Optimización:** `matriz`/`rangos_credito`/`formula_componentes` pre-resueltos una vez por período (no una vez por vendedor) en el simulador, evitando N consultas redundantes por vendedor.

Validado en vivo contra el EDW real: VEN13/feb-2026 pasa de `comision_base=$200,82` (solo líneas, diseño anterior con `cobranza` sin activar) a `comision_base=$1.163,42` (líneas + cobranza sumadas, diseño corregido).
