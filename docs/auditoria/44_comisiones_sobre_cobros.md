# Auditoría 44 — Comisiones sobre Cobros (integración al esquema de Comisiones Variables)

- **Fecha:** 2026-07-30
- **Alcance:** reglas de comisión sobre cobranza vigentes en la empresa (documento "COMISIONES 01/02/2026 FEBRERO" + consulta PowerBuilder del ERP aportada por el usuario), tablas de Producción que las sustentan (`fp_cxc_cuotas`, `cuentasporcobrar`, `movimientos_caja`, `encabezadofacturas`), su representación actual en el EDW (`edw.fact_cobros_cxc`, `edw.dim_formapago`, `edw.fact_movimientos_caja`) y la capacidad del motor de Comisiones Variables (`backend/app/services/commission_engine.py`) de expresarlas.
- **Método:** `SELECT` de solo lectura contra SAP SQL Anywhere 17 (`codemp='01'`, host `172.16.50.5:4016`, driver FreeTDS vía la imagen `proyect_bi-etl`) mediante un arnés temporal con guarda que bloquea cualquier verbo de escritura; `psql` contra `bi_postgres_edw`; lectura del código de `backend/`, `etl/` y `frontend/`.
- **Restricción respetada:** Producción es SOLO LECTURA. No se ejecutó ningún `INSERT`/`UPDATE`/`DELETE`/`ALTER`/`DROP`/`CREATE`/`MERGE`.

---

## 1. Regla de negocio real (fuente: usuario + reporte del ERP)

La empresa hoy **no comisiona sobre venta facturada**, sino **sobre cobranza efectivamente realizada**, con la tasa determinada por los **días transcurridos entre la emisión de la factura y la fecha en que el dinero se hace efectivo**:

| Tramo (días) | Vendedor externo | Jefe de agencia |
|---|---|---|
| ≤ 21 | 2.00 % | 1.00 % |
| ≤ 60 | 1.75 % | 1.75 % |
| ≤ 90 | 0.75 % | 0.75 % |
| ≤ 120 | 0.50 % | 0.50 % |
| ≤ 365 | 0.00 % | 0.00 % |

Reglas adicionales declaradas:

- **Jefes de agencia** ganan además **1 % de las ventas de CONTADO de su agencia** que correspondan a ese vendedor.
- **Cheques postfechados:** la factura queda saldada al recibir el cheque, pero **el dinero aún no ingresa**. La comisión se devenga según **la fecha en que el cheque se cobra**, no la fecha en que se recibió — "hay el caso de que varían los meses".
- El reporte del ERP filtra por `fp_cxc_cuotas.banfec BETWEEN :d_fecini AND :d_fecfin` y excluye `substring(numcco,1,2) = 'ND'` (notas de débito).

---

## 2. Hallazgos

### H-1 (CRÍTICO) — La tabla que sustenta toda la regla de cobranza no se extrae al EDW

`fp_cxc_cuotas` es la tabla de **formas de pago por cuota cobrada**: es el grano exacto sobre el que el ERP calcula la comisión sobre cobros. **No existe ningún extractor** para ella en `etl/extractors/` (los 22 archivos verificados) ni ninguna entrada en `PIPELINE_CONFIG` (`etl/orchestrator.py:253-294`).

Estructura real (28 columnas, verificada contra `sys.syscolumns`):

| Columna | Rol en la regla de negocio |
|---|---|
| `banfec` | **Fecha de efectivización** — la que determina el mes que comisiona |
| `fectra` | Fecha en que se registró el cobro (para CP, la fecha de recepción del cheque) |
| `fecemi` | Fecha de emisión de la factura origen |
| `fecven` | Fecha de vencimiento |
| `tiptra` | **Instrumento de pago** (EF/CP/DP/CH/TA/ND/NC) |
| `valfor` | Monto cobrado |
| `codven` | Vendedor al que se acredita el cobro |
| `numtra`, `ncuota` | Factura origen y número de cuota |
| `numche`, `bannum`, `codban`, `depositado` | Datos de cheque/banco |

**Consecuencia:** la regla de negocio real de comisiones es hoy **inexpresable** en la plataforma. No es una limitación del motor de cálculo: el dato nunca llega al EDW.

### H-2 (CRÍTICO) — El instrumento de pago se pierde por completo en `edw.fact_cobros_cxc`

```
SELECT fp.codforpag, COUNT(*), SUM(c.valor_cobrado)
  FROM edw.fact_cobros_cxc c JOIN edw.dim_formapago fp USING (formapago_sk) GROUP BY 1;

 codforpag |   n    |     total
-----------+--------+---------------
 -1        | 214108 | 42155546.6200      <-- 100 % en el centinela "desconocido"
```

**El 100 % de las 214.108 filas** tiene `formapago_sk = -1`. Es imposible distinguir efectivo de cheque, de cheque postfechado o de depósito en el EDW actual.

Causa raíz: `edw.dim_formapago` solo contiene 3 valores, provenientes de un extractor **estático y hardcodeado** (`etl/extractors/formapago_extractor.sql`, que se declara a sí mismo "Extracción estática … ya que tipo_formapago_cxc está vacía en este origen"):

```
 formapago_sk | codforpag | nombre_forma_pago | dias_plazo
            1 | E         | EFECTIVO          |          0
            2 | 0         | OTRO/VARIOS       |          0
            3 | C         | CREDITO           |         30
```

El vocabulario **real** de instrumentos en Producción es otro (`fp_cxc_cuotas.tiptra`, histórico completo):

| `tiptra` | Significado | Filas | Monto |
|---|---|---:|---:|
| `EF` | Efectivo | 63.159 | 7.263.873,53 |
| `CP` | **Cheque postfechado** | 26.371 | 6.959.244,78 |
| `DP` | Depósito / transferencia | 25.282 | 7.320.462,04 |
| `CH` | Cheque | 22.322 | 3.971.192,06 |
| `TA` | Tarjeta | 1.886 | 200.660,90 |
| `ND` | Nota de débito | 1.266 | 383.477,58 |
| `NC` | Nota de crédito | 29 | 10.820,12 |

### H-3 (CRÍTICO) — Confirmado con datos reales: usar la fecha equivocada mueve de mes casi la mitad del dinero de cheques postfechados

El punto que el usuario señaló ("varían los meses") es **cuantitativamente grande**, no un caso de borde. Contraste `fectra` (recepción) vs `banfec` (efectivización), ene-2025 → jul-2026:

| Instrumento | Mismo mes | Cruza de mes | Monto que cruza |
|---|---:|---:|---:|
| `CP` (postfechado) | 1.739 | **1.566 (47,4 %)** | **$366.688,27 de $839.412,46 (43,7 %)** |
| `CH` (cheque) | 2.476 | 10 (0,4 %) | $3.482,89 |
| `DP` (depósito) | 9.467 | 1 | $128,00 |
| `EF` (efectivo) | 10.644 | 0 | — |

Desfase promedio de los `CP` que cruzan: **35,5 días**. Ejemplo real (feb-2026): cheque recibido el `2026-01-10` (`fectra`) y cobrado el `2026-02-22` (`banfec`), $1.674,67 — comisiona en **febrero**, no en enero.

**Conclusión validada:** `banfec` es la fecha correcta de devengo, y **solo el instrumento `CP` la necesita realmente** — para EF/CH/DP/TA `banfec ≈ fectra`. Esto simplifica la implementación: usar `banfec` uniformemente es correcto para todos los instrumentos y a la vez resuelve el caso postfechado.

### H-4 (ALTO) — `edw.fact_cobros_cxc` no es una tabla de cobros

`etl/extractors/cobros_cxc_extractor.sql` extrae `cuentasporcobrar` **sin filtrar por `tiporg`/`tipdoc`**, con `fecemi` como fecha. Pero `cuentasporcobrar` es un libro mayor mixto:

| `tiporg` | `tipdoc` | Filas | Naturaleza |
|---|---|---:|---|
| CXC | AB | 95.237 | Abono (cobro real) |
| FAC | FC | 70.928 | **Factura emitida (no es un cobro)** |
| CXC | RT | 40.427 | Retención |
| DEV | NC | 5.529 | Nota de crédito |
| CXC | CA | **45** | Cancelación |

La tabla mezcla facturas emitidas con cobros y retenciones bajo el nombre "cobros". Además usa `fecemi` (emisión) como `fecha_sk`, no la fecha del cobro.

**Nota sobre AB/CA:** el usuario indicó "ab - abono, ca - cancelación". En los datos, `CA` tiene solo **45 filas históricas** frente a 95.237 de `AB` — en la práctica las cancelaciones también se registran como `AB`. La lógica no debe depender de `CA` para detectar cancelaciones.

### H-5 (ALTO) — El motor variable actual no puede expresar la regla: comisiona sobre factura, no sobre cobro

`CommissionService._calcular_variable` → `GoalRepository.get_commission_lines` (`goal_repository.py:472-497`) lee **exclusivamente `edw.fact_ventas_detalle`**: el grano es la línea de factura, la base es margen o valor de venta, y el período es el mes de **facturación**. No existe ninguna ruta de datos hacia cobranza.

Además, el `dias_plazo` que alimenta `_factor_credito` (el único punto del motor que se aproxima a la idea de "plazo") proviene de `dim_formapago.dias_plazo`, es decir del catálogo hardcodeado de 3 filas de H-2: en la práctica solo puede valer **0 o 30**. El factor de crédito del esquema variable es hoy un binario sin sustento real, no una escala de plazos.

### H-6 (MEDIO) — No existe el tipo de vendedor "jefe de agencia"

`public.comision_config_vendedor` tiene un `CHECK` que restringe `tipo` a `('externo','interno')`:

```
"check_tipo_vendedor_valido" CHECK (tipo IN ('externo','interno'))
```

La regla de negocio define un tercer perfil con tabla de tasas propia en el primer tramo (1 % vs 2 % a 21 días) **y** un componente adicional (1 % de las ventas de contado de su agencia). No es representable sin migración.

### H-7 (MEDIO) — Semántica de `conpag` verificada (contraintuitiva)

Para el componente "1 % de ventas de contado" hay que identificar ventas de contado. Verificado en `encabezadofacturas` (feb-2026, `estado='P'`), cruzando contra la existencia de CxC:

| `conpag` | Facturas | Monto | Generan CxC |
|---|---:|---:|---:|
| `C` | 786 | $226.137,77 | **786 (100 %)** → **CRÉDITO** |
| `E` | 1.493 | $110.208,77 | **0 (0 %)** → **CONTADO** |

Las letras son contraintuitivas (`E` = contado, `C` = crédito). **Cualquier implementación debe usar `conpag='E'` para "contado"**, documentado, para no invertir la regla por asumir la inicial.

Las agencias (`establ`) reales con ventas en feb-2026 son `001, 002, 003, 004, 005, 007`.

### H-8 (MEDIO) — La fórmula está hardcodeada en el motor

`calcular_comision_variable` (`commission_engine.py:350-405`) fija en código la estructura del cálculo:

```
Σ líneas(base × tasa × factor_estratégico × factor_crédito)
  × factor_tipo_vendedor × multiplicador_cumplimiento − devoluciones + bonos
```

Los *valores* son configurables (matriz, factores de crédito, settings), pero la **estructura** —qué componentes existen, en qué orden se aplican y si se multiplican o se suman— requiere cambio de código. El usuario pide explícitamente que "la fórmula para calcular las comisiones también pueda ser editable y no quemado en código".

### H-9 (BAJO) — Calidad de dato en `fp_cxc_cuotas`

- **12 filas** con `banfec` anterior a `fecemi` (mínimo −25 días) desde 2015. Producen días de cobro negativos; deben tratarse explícitamente (tramo mínimo), no propagarse a una división o a un tramo fuera de rango.
- `MIN(banfec)` para `CP` y `CH` devuelve valores con formato de año de 2 dígitos (`17-10-15`, `17-02-21`) y `MAX(banfec)` para `CP` es `2026-10-01`, **futuro respecto de la fecha de corrida** — coherente con la naturaleza de un cheque postfechado, pero implica que un cierre de mes debe filtrar por rango cerrado, nunca por `>= inicio`.
- El prefijo de `numcco` solo toma 2 valores (`RC` 26.433, `ND` 69): la exclusión `<> 'ND'` del reporte es equivalente a "solo recibos de caja".

### H-10 (BAJO) — Los depósitos no pasan por caja

Contraste feb-2026 entre `fp_cxc_cuotas` (por `banfec`) y `movimientos_caja` (`tiporg='CXC'`, `tipdoc='AB'`):

| Instrumento | `fp_cxc_cuotas` | `movimientos_caja` |
|---|---:|---:|
| EF | 57.976,34 | **57.976,34** ✔ |
| CH | 45.915,59 | **45.915,59** ✔ |
| TA | 1.466,82 | **1.466,82** ✔ |
| CP | 49.847,09 | 42.490,64 ✘ |
| DP | **103.090,59** | **ausente** ✘ |

Los depósitos/transferencias (el instrumento de **mayor monto** del mes) no se registran en caja, y los postfechados solo parcialmente. **`movimientos_caja` no sirve como fuente de la comisión sobre cobros**; la fuente correcta y completa es `fp_cxc_cuotas`. (Se verificó por pedido explícito del usuario de "verificar los movimientos de caja, cheques (depósito o transferencia)": la conclusión es que caja es un canal parcial, no la fuente de verdad.)

---

## 3. Verdad de campo — febrero 2026

Reproducción de la regla del ERP (tasas de vendedor externo, `banfec` entre 2026-02-01 y 2026-02-28, `numcco` no `ND`), para servir de **caso de aceptación** de la implementación:

| Vendedor | ≤21 | ≤60 | ≤90 | ≤120 | Total cobrado | Comisión |
|---|---:|---:|---:|---:|---:|---:|
| VEN13 | 6.381,44 | 42.320,79 | 8.867,37 | 5.650,03 | 65.893,10 | **963,00** |
| VEN02 | 12.570,81 | 16.544,07 | 28.912,58 | 4.800,21 | 63.820,92 | **781,78** |
| VEN21 | 7.164,27 | 23.205,04 | 9.408,56 | 1.433,52 | 41.354,25 | **627,11** |
| VEN24 | 6.685,38 | 11.806,16 | 7.644,05 | 2.926,10 | 29.061,69 | **412,28** |
| VEN01 | 9.718,54 | 7.369,49 | 703,65 | 455,90 | 18.247,58 | **330,89** |
| VEN03 | 3.929,40 | 7.048,31 | 2.431,35 | 34,71 | 13.443,77 | **220,34** |
| VEN22 | 0,00 | 0,00 | 5.514,67 | 3.462,61 | 10.875,78 | **58,67** |
| VEN16 | 5.296,47 | 4.906,75 | 0,00 | 0,00 | 10.203,22 | **191,80** |
| VEN15 | 2.064,72 | 3.965,74 | 882,02 | 825,48 | 7.798,48 | **121,44** |
| VEN17 | 329,00 | 0,00 | 0,00 | 0,00 | 329,00 | **6,58** |
| VEN23 | 0,00 | 228,13 | 0,00 | 0,00 | 228,13 | **3,99** |

Distribución del mes por instrumento: DP $103.090,59 · EF $57.976,34 · CP $49.847,09 · CH $45.915,59 · NC $2.959,49 · TA $1.466,82.

Se confirmó además que `fp_cxc_cuotas.fecemi` coincide **exactamente** con la fecha de la factura origen (`cuentasporcobrar.fectra` de `tiporg='FAC'`/`tipdoc='FC'`) en las 15 filas de control inspeccionadas — por lo que los días de cobro se calculan dentro de `fp_cxc_cuotas` sin necesidad de las 4 subconsultas correlacionadas del reporte PowerBuilder original.

`fp_cxc_cuotas.codven` coincide con el `codven` de la factura origen en **2.718 de 2.759** cobros (98,5 %) de ene–feb 2026. El 1,5 % restante corresponde a cobros acreditados a un vendedor distinto del que facturó; se acredita a `fp_cxc_cuotas.codven`, igual que el reporte del ERP.

---

## 4. Conclusión

La regla de comisiones realmente vigente en la empresa **no puede calcularse hoy** en la plataforma, y la causa no es el motor sino la **ausencia del dato**: la tabla que la sustenta (`fp_cxc_cuotas`) no se extrae, el instrumento de pago está 100 % en el centinela `-1`, y el único proxy de plazo disponible (`dim_formapago.dias_plazo`) proviene de un catálogo hardcodeado de 3 filas.

La corrección requiere, en este orden: (1) ETL + EDW para traer la cobranza al grano correcto con `banfec`; (2) configuración persistida y editable de tramos, tasas por perfil y estructura de fórmula; (3) un componente de cobranza en el motor variable que conviva con el actual sin romperlo; (4) exposición en el panel de configuración de gerencia. El plan de ejecución está en `docs/features/plan_comisiones_sobre_cobros.md`.

Reglas de negocio nuevas propuestas a partir de esta auditoría: **RN-CM8 … RN-CM13** (ver `docs/auditoria/02_reglas_negocio_validadas.md` §18, a redactar al aplicar la Fase correspondiente).
