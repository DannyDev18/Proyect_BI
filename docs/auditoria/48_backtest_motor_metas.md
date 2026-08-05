# Backtest motor-a-motor de metas (Fase 9.A de `docs/features/plan_motor_metas_v3_y_comisiones_unificadas.md`, R-13)

> **Fecha:** 2026-08-04. **Método:** `backend/scripts/backtest_motor_metas.py` (herramienta
> de auditoría, no código de producción; 100% de solo lectura contra `bi_postgres_edw`
> real), ejecutado dentro de `bi_backend`. Corrida real, sin datos sintéticos: walk-forward
> mes a mes, cada mes objetivo recalculado usando SOLO el histórico estrictamente anterior
> a ese mes (nunca datos del propio mes o posteriores), sobre `edw.fact_ventas_detalle`
> real. Población por mes: vendedores activos con al menos una venta en los 12 meses
> previos al mes objetivo (`GoalRepository.get_vendors_with_recent_sales`, la misma regla
> de elegibilidad de producción tras el hallazgo H-2 de esta misma auditoría) -- 10-11
> vendedores por mes, 129 observaciones vendedor-mes en total sobre los últimos 12 meses
> cerrados (2025-08 a 2026-07).

## Resultado

| Motor | n | Mediana % cumpl. | P10 | P25 | P75 | P90 | % ≥100% | % <90% | % >125% | Costo comisión agregado |
|---|---|---|---|---|---|---|---|---|---|---|
| v2 (estadístico puro, sin madurez/tipo/redondeo) | 129 | 99.5% | 0.0% | 81.8% | 122.5% | 144.9% | 48.8% | 35.7% | 23.3% | $109.022,44 |
| v3 (pipeline modular vigente hoy, incluye E6 madurez/E8 tipo/E11 redondeo) | 129 | 93.2% | 0.0% | 73.6% | 112.7% | 130.5% | 37.2% | 44.2% | 14.0% | $99.230,67 |

**Costo de comisión**: reutiliza `calcular_comision_variable_completa` -- el MISMO motor
que liquida comisiones reales -- con la meta recalculada por cada motor como denominador
del % de cumplimiento y el gate de la Fase 2 (RN-CM16, umbral 90%) activo; no es una
aproximación, es el cálculo real aplicado a una meta hipotética.

## Casos de mayor divergencia entre motores (top 15, vendedor-mes)

| Vendedor | Período | Meta v2 | Meta v3 | Divergencia % |
|---|---|---|---|---|
| VEN23 | 2025-12 | $26,80 | $16.800,00 | 62.586,6% |
| VEN23 | 2026-05 | $133,21 | $12.600,00 | 9.358,7% |
| VEN23 | 2026-06 | $131,27 | $12.400,00 | 9.346,2% |
| VEN23 | 2026-07 | $138,29 | $12.500,00 | 8.939,0% |
| VEN23 | 2026-01 | $133,89 | $12.100,00 | 8.937,3% |
| VEN23 | 2026-04 | $119,60 | $10.000,00 | 8.261,2% |
| VEN23 | 2026-02 | $117,60 | $9.500,00 | 7.978,2% |
| VEN23 | 2025-08 | $292,42 | $22.600,00 | 7.628,6% |
| VEN23 | 2025-09 | $287,28 | $21.700,00 | 7.453,6% |
| VEN23 | 2025-11 | $270,59 | $19.400,00 | 7.069,5% |
| VEN23 | 2025-10 | $294,40 | $20.700,00 | 6.931,2% |
| VEN23 | 2026-03 | $124,93 | $8.600,00 | 6.783,9% |
| VEN24 | 2025-11 | $13.879,39 | $26.600,00 | 91,7% |
| VEN17 | 2025-12 | $591,53 | $700,00 | 18,3% |
| VEN22 | 2026-05 | $24.601,33 | $29.100,00 | 18,3% |

## Interpretación

1. **El caso `VEN23` confirma que E6/madurez corrige un defecto real de v2, no lo
   introduce.** `VEN23` entra a la ventana de 12 meses (hallazgo H-2 de esta auditoría)
   con muy poco histórico PROPIO -- v2 (sin madurez) calcula metas de apenas
   $26,80-$294,40 sobre esa serie casi vacía, valores sin ningún sentido de negocio
   (cualquier venta real, por mínima que sea, dispara un "sobrecumplimiento" de miles por
   ciento). v3 mezcla ese histórico casi vacío con la mediana del equipo (transición
   gradual, meses_antiguedad bajo) y produce metas de $8.600-$22.600 -- órdenes de
   magnitud más razonables. Este es exactamente el defecto que motivó la Fase 7/E6.
2. **Ninguno de los dos motores llega al rango objetivo de 60-70% de vendedores ≥100%**
   (v2: 48,8%; v3: 37,2%) sobre esta muestra de 12 meses/10-11 vendedores. v3 queda MÁS
   lejos del objetivo que v2 en esta métrica agregada -- pero el resultado está sesgado
   por el propio caso `VEN23`: al reemplazar metas artificialmente bajas (que v2
   "cumplía" trivialmente en cualquier mes con venta) por metas realistas del tamaño del
   equipo, el % de cumplimiento de esos meses cae de +1000% a un rango normal, arrastrando
   la métrica agregada hacia abajo aunque el cambio individual sea una mejora real, no un
   empeoramiento. Con solo 10-11 vendedores por mes, un solo caso como `VEN23` pesa
   ~10% de la muestra mensual -- el tamaño de muestra es la limitación real de esta
   corrida, no necesariamente la calibración del motor.
3. **Costo de comisión agregado**: v3 cuesta $99.230,67 contra $109.022,44 de v2 (-9,0%)
   sobre el mismo período -- consistente con que v3 generalmente asigna metas más altas a
   vendedores de historial débil (más difíciles de superar, menos sobrecumplimiento
   pagado) y con el gate/techo de bonos de la Fase 2 ya activo en ambos cálculos.
4. **No se recalibró la semilla del v3 a partir de este resultado en esta sesión** --
   el propio caso `VEN23` muestra que la comparación agregada está dominada por un solo
   vendedor con muy poca historia; antes de tocar parámetros (banda, umbral de madurez,
   agrupador de benchmark) se recomienda repetir este backtest con una ventana más amplia
   de vendedores (relajando el filtro de 12 meses solo para esta herramienta de
   diagnóstico, no para producción) o esperar a que la ventana de elegibilidad H-2
   recientemente ampliada acumule más meses de datos reales.

## Pendiente

- **Fase 9.B** (backtest contra metas realmente aprobadas): sigue bloqueada -- este
  entorno solo tiene metas `APROBADA` de 2026-07/08 (`SELECT COUNT(DISTINCT (anio,mes))
  FROM public.metas_comerciales_operativas WHERE estado='APROBADA'` = 2), muy por debajo
  del umbral de 6-12 meses que el plan exige para no fabricar la evidencia. Disparador ya
  documentado: revisar ese `COUNT` cada vez que se retome el módulo.
- Repetir este backtest con una muestra de vendedores más amplia (o una ventana temporal
  más larga, cuando el EDW acumule más meses tras esta sesión) antes de tomar cualquier
  decisión de recalibración de la semilla v3 con este resultado como única evidencia.
