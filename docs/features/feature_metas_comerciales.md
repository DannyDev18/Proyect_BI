# FEATURE SPEC: Módulo de Metas y Comisiones

## 1. Descripción General

Módulo encargado de gestionar, visualizar y calcular el cumplimiento de los objetivos comerciales mensuales asignados a cada vendedor y sucursal. Impacta directamente en el Dashboard de Ventas (progreso individual) y el Dashboard de Gerencia (cumplimiento global).

## 2. Dependencias de Base de Datos

- **Tabla de Hechos:** `edw.fact_metas_comerciales`
  - Claves foráneas: `vendedor_sk`, `sucursal_sk`, `fecha_sk` (asociada al primer día del mes evaluado).
  - Métrica: `monto_meta` (Numérico/Decimal).
- **Tabla Cruzada:** `edw.fact_ventas_detalle` (para obtener la sumatoria de ventas reales).

## 3. Lógica de Machine Learning y Cálculo de Metas (`Analytics Service / API`)

A diferencia de una simple tabla SQL, el cálculo de metas está automatizado mediante Machine Learning y reglas empíricas de negocio:

### 3.1 Pipeline de Proyección

1. **Extracción**: Lectura de historial de ventas de los últimos 2 años para Vendedor X en Sucursal Y (`make_dataset.py`).
2. **Transformación (Baseline)**: Cálculo del promedio móvil suavizado ponderado:
   - 50% Estacionalidad Histórica (Mismo mes, año anterior)
   - 50% Tendencia Desestacionalizada (Promedio del año actual, excluyendo el mes atípico pico).
3. **Inferencia (ML)**: El modelo `RandomForestRegressor` predice la "Tasa de Crecimiento" o `Growth Ratio`.
4. **Capping y Aseguramiento Funcional (Guarding)**:
   - Limitar predicciones aberrantes para que no excedan del 120% del promedio histórico (`safe_limit_max`).
   - Evitar proyecciones deprimentes al no permitir caer del 80% del histórico (`safe_limit_min`).
5. **Factor de Presión Comercial**: Una vez calculada la Meta Predictiva (ML), se multiplica por `factor_presion` (ej. `1.15` u 15%) según las exigencias gerenciales del año.

### 3.2 Porcentaje de Logro y Comisiones (Incentivos)

Si un vendedor supera la meta pre-calculada por la IA:

- **Tramos**: Ventas netas totales evaluando umbrales (ej. > 80%, > 100%, > 115%).
- **Ejecución**: El Frontend (`GoalsConsole.tsx`) renderiza tramos de color dinámicos basados en la respuesta JSON `/api/v1/goals/vendedor/{id}`. Dependiendo del escalón logrado, se desbloquean multiplicadores extra en la tasa de comisión final otorgada en el rol de pago.
