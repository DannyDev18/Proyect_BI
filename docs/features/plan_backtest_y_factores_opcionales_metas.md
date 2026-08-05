# Plan — Backtest formal del motor de metas v2 y factores opcionales de la Fase 6

> **SUPERADO (2026-07-31):** este plan fue absorbido íntegramente por
> `docs/features/plan_motor_metas_v3_y_comisiones_unificadas.md` — sus Fases A/B son las Fases 9.A/9.B
> de aquel, y sus Fases C-F son su §13 (Fase 10). Se conserva como referencia histórica del análisis;
> **no ejecutar desde aquí.**
>
> **Estado:** propuesto (ninguna fase aplicada).
> **Fecha:** 2026-07-31
> **Módulo:** Metas y Comisiones (panel de Gerencia) — continuación de `docs/features/plan_motor_metas_configurable.md` (Fases 1-7 ya aplicadas, ver `docs/auditoria/46_motor_metas_configurable.md`).
> **Origen:** los dos pendientes que quedaron explícitamente fuera de alcance de esa sesión — (1) backtest formal de 12 meses cerrados, (2) los 4 factores opcionales de la §5.4 del plan anterior (días hábiles, cartera activa, meses no representativos, tope de variación intermensual).

---

## 1. Por qué estos dos pendientes se separaron del plan anterior

El plan anterior exigía en su §7 ("Validación exigida"): *"recalcular con el motor v2 las metas de los últimos 12 meses cerrados y comparar la distribución de cumplimiento resultante contra la real"* antes de dar por buena la semilla de parámetros. No se hizo porque **este entorno no tiene el dato para hacerlo**: `public.metas_comerciales_operativas` solo tiene metas aprobadas de 2026-07 y 2026-08 (ver auditoría 45 y 46) — hay 0 meses cerrados adicionales con una meta oficial contra la cual comparar. Forzar un backtest ese día habría sido inventar una comparación sin base real, exactamente lo que el proyecto evita (regla de decisión de la auditoría 46: *"no se reescribe un motor de metas sobre una hipótesis"*).

Los 4 factores opcionales quedaron fuera porque el plan anterior los definió como *"parámetros configurables desactivados por defecto, para que gerencia los active con evidencia, no por defecto"* — activar cualquiera de los 4 sin la evidencia que su propio diseño exige habría sido lo mismo: una decisión sin base.

Este plan cierra ambos pendientes **cuando exista la evidencia**, no de inmediato — dos de sus fases son de espera activa, no de código.

---

## 2. Backtest formal de 12 meses

### 2.1 El bloqueo real

El backtest necesita, para cada uno de 12 meses consecutivos ya cerrados: (a) el histórico de ventas del vendedor **hasta ese mes** (ya existe en `fact_ventas_detalle`, sin bloqueo), y (b) una meta **ya aprobada** para ese mes contra la cual comparar la distribución de cumplimiento (no existe: solo julio/agosto-2026). Sin (b) no hay "distribución de cumplimiento real" con la que contrastar al motor v2 — solo se podría comparar motor v1 vs. motor v2 sobre los mismos datos, que es una comparación **motor-a-motor**, no motor-contra-la-realidad-aprobada-por-gerencia. Este plan distingue explícitamente ambas comparaciones y ejecuta la que sí es posible hoy, dejando la otra en espera activa.

### 2.2 Fase A — Backtest motor-a-motor (ejecutable HOY, sin esperar nada)

No requiere metas históricas aprobadas — solo re-ejecuta ambos motores (v1 conservado en control de versiones vía `git show`, v2 actual) sobre el mismo histórico real de `fact_ventas_detalle` para los últimos 12 meses cerrados, con cada mes usado como "período objetivo" y el histórico disponible hasta ese mes como insumo (walk-forward real, no fuga de datos futuros).

**Entregable:** script `backend/scripts/backtest_motor_metas.py` (documentado como herramienta de auditoría, no parte del código de producción) que:

1. Para cada vendedor activo y cada uno de los últimos 12 meses cerrados, calcula la meta con el motor v1 (constantes históricas: ventana 24 meses, sin banda de alcanzabilidad, sin índice estacional multi-anual) y con el motor v2 (configuración vigente en `metas_config_parametros`).
2. Compara cada meta contra la **Venta Neta real** de ese mismo mes (ya calculable, es dato histórico real — esto SÍ es "meta vs. realidad", solo que la meta comparada es la RECALCULADA, no la que gerencia aprobó en su momento, porque esa no existe).
3. Reporta, por motor, la distribución de cumplimiento (mediana, percentiles 10/25/75/90, % bajo 90%, % sobre 125%) y el costo total agregado de comisión que ese nivel de meta habría generado (reutilizando `commission_variable_engine.calcular_comision_variable_completa` con la meta recalculada).
4. Reporta explícitamente, por vendedor y mes, los casos de mayor divergencia entre v1 y v2 (mismo formato de tabla que la auditoría 46 §A-0.4), para que la mejora sea verificable caso por caso, no solo en el agregado.

**Criterio de aceptación (adaptado de la §7 del plan anterior, sin el dato que falta):** la mediana de cumplimiento del motor v2 debe acercarse al rango 90-105% con menor dispersión (menor diferencia entre percentil 10 y 90) que el motor v1 sobre el MISMO histórico real. Se reporta también el costo agregado de comisión de ambos escenarios — la decisión final la toma gerencia viendo ambas cifras, igual que exigía el plan original.

**Salida:** `docs/auditoria/47_backtest_motor_metas.md`, con las tablas completas y la recomendación (mantener la semilla vigente / ajustar algún parámetro con evidencia).

### 2.3 Fase B — Backtest contra metas realmente aprobadas (espera activa, no ejecutable hoy)

Cuando existan ≥ 6-12 meses de metas con `estado='APROBADA'` en `public.metas_comerciales_operativas` (acumulación natural del uso mensual del sistema, sin que este plan necesite intervenir en ese proceso), se ejecuta el backtest que el plan original pedía originalmente: meta v2 recalculada vs. meta REALMENTE aprobada por gerencia vs. Venta Neta real, con la distribución de cumplimiento verdadera del negocio.

- **No requiere código nuevo** más allá de reutilizar el script de la Fase A con una bandera `--contra-metas-aprobadas` que, en vez de comparar contra el recálculo v1, compara contra `monto_meta` de la fila `APROBADA` real del período.
- **Disparador:** revisar la cobertura de `metas_comerciales_operativas` (`SELECT COUNT(DISTINCT (anio, mes)) WHERE estado='APROBADA'`) cada vez que se retome trabajo en este módulo; en cuanto haya ≥ 6 meses, correr la Fase B y decidir si la semilla de parámetros (ventana 36 meses, banda 0.85-1.20, etc.) necesita ajuste con evidencia real de la empresa, no solo de un backtest motor-a-motor.
- Este plan **no** propone generar metas aprobadas artificialmente para acelerar esto — sería fabricar la evidencia que el motor v2 existe justamente para no fabricar.

---

## 3. Factores opcionales de la Fase 6 (§5.4 del plan anterior)

Los 4 se evalúan **por separado**, porque tienen viabilidad de datos muy distinta hoy. Cada uno sigue el mismo patrón de activación: parámetro nuevo en `metas_config_parametros` (o su propia tabla si necesita más que un escalar), **apagado por defecto** (`activo=false` o multiplicador neutro 1.0), con el mismo CRUD/bitácora ya construido — no se reabre el diseño de configuración, solo se agregan filas.

### 3.1 Días hábiles del mes objetivo — **bloqueado por datos, no por diseño**

`dim_fecha.es_feriado` existe en el esquema pero **nunca se puebla** (gap ya documentado en CLAUDE.md — "riesgos técnicos" — y en la auditoría 05: *"dim_fecha.es_feriado nunca poblado (workaround hardcodeado en código ML)"*, el mismo defecto que ya afecta al pipeline de `sales_rf`). Sin feriados reales, "días hábiles" se reduce a "días que no son sábado/domingo" (`es_fin_semana`, ese sí poblado) — una aproximación que **subestima sistemáticamente** el efecto en meses con feriados largos (ej. carnaval, semana santa, navidad) y no aporta nada por encima de lo que ya captura el índice estacional propio del vendedor (que ya absorbe el patrón histórico real de esos meses, feriados incluidos, porque los datos de ventas de esos meses en años previos YA reflejan el impacto del feriado).

**Recomendación de este plan: no implementar como factor separado.** El índice estacional del motor v2 (RN-MT1/RN-MT2) ya captura el efecto real de los feriados recurrentes (un diciembre con navidad siempre tuvo navidad en los años de historia usados para el índice) — un factor de "días hábiles" adicional **duplicaría** ese ajuste en vez de complementarlo, y encima con datos peor fundamentados (aproximación fin-de-semana-only en vez del patrón real). Se documenta la evaluación y se cierra el punto sin código, salvo que una auditoría futura confirme con `SELECT` que el índice estacional propio es insuficiente en meses con feriados atípicos (ej. un año bisiesto con Semana Santa movida).

### 3.2 Cartera activa del vendedor — viable, prioridad más alta de los 4

`Cartera360Repository`/`Cartera360Service` ya calculan la cartera de clientes activos de un vendedor (`_estado_cartera`, auditoría de Ventas). Es información real y ya disponible, sin gaps de datos como §3.1.

**Diseño propuesto:**
- Nuevo parámetro `factor_cartera_activo: bool` (default `false`) en `metas_config_parametros`.
- Cuando está activo, `GoalMLService.suggest_goal` resuelve el tamaño de cartera activa del vendedor en el mes objetivo y en una ventana de referencia (ej. promedio de los 6 meses anteriores) vía `Cartera360Repository`; un cambio proporcional grande (`> umbral_cambio_cartera_pct`, nuevo parámetro) ajusta `nivel_base` por la misma proporción **antes** de aplicar el índice estacional (un vendedor que perdió el 30% de su cartera no debería recibir una meta calculada sobre un nivel histórico que ya no es alcanzable con la cartera actual, y viceversa para un vendedor que ganó cartera).
- Este factor SÍ requiere una decisión de gerencia con evidencia real, porque una cartera que crece o decrece puede deberse a reasignaciones administrativas (no a desempeño) — se documenta como tal en la descripción del parámetro.
- **Auditoría previa antes de activar (solo `SELECT`):** cuantificar cuántos vendedores tuvieron cambios de cartera `> 20%` mes a mes en el histórico disponible, y si esos cambios coinciden con saltos de venta ya explicados por otros mecanismos (para no doble-contar).

### 3.3 Meses no representativos (ausencias/vacaciones) — viable, complementa el filtro de outliers existente

Hoy un mes con ventas casi nulas por vacaciones/baja médica entra al histórico como un "mes malo real" y **reduce** la meta futura del vendedor — el espejo exacto del problema que la banda de alcanzabilidad ya corrige del lado alto, pero sin equivalente del lado bajo.

**Diseño propuesto:**
- Nuevo parámetro `umbral_mes_no_representativo` (fracción de la mediana de la ventana, ej. `0.15` = un mes con menos del 15% de la mediana histórica se considera no representativo), default **desactivado** (`0` = nunca se activa este filtro).
- Cuando está activo, en `IQRGoalCalculationEngine._indices_sin_outliers` (o un paso equivalente antes del cálculo del nivel base), los meses con venta `< umbral × mediana_ventana` se excluyen del cálculo del nivel base y de la tendencia (mismo tratamiento que un outlier alto de Tukey, pero por umbral absoluto en vez de estadístico, porque un mes de $0 no necesariamente cae fuera de las bandas de Tukey si el vendedor ya es de por sí muy variable).
- **Riesgo a documentar antes de activar:** este filtro puede ocultar una caída REAL y sostenida del vendedor (no solo una ausencia puntual) si se activa con un umbral mal calibrado — se recomienda activarlo solo tras revisar con gerencia los casos concretos que dispara (mismo patrón de previsualización ya construido en la pestaña "Fórmula de metas").

### 3.4 Tope de variación intermensual de la meta — viable, el guardarraíl más directo

Es el más simple de los 4 y el que más rápido cierra el reclamo original del usuario (una meta no debería saltar de golpe mes a mes sin justificación).

**Diseño propuesto:**
- Nuevo parámetro `tope_variacion_intermensual_pct` (ej. `0.15` = la meta nueva no puede diferir más de ±15% de la meta **aprobada** del mes inmediatamente anterior del mismo vendedor), default **desactivado**.
- Aplicado en `GoalMLService.generate_proposals`, **después** de que el motor v2 ya calculó la meta con su propia banda de alcanzabilidad: se consulta `goal_repo.get_goal_for_period(vendedor, anio_anterior, mes_anterior)` (ya existe) y, si hay una meta `APROBADA` de ese mes, se acota la meta nueva a `[meta_anterior × (1-tope), meta_anterior × (1+tope)]`.
- Es el único de los 4 que compone directamente con la banda de alcanzabilidad ya construida (RN-MT3) — se aplica como un segundo clamp, no reemplaza al primero.
- **Nota de diseño:** solo tiene efecto a partir de que exista una segunda meta aprobada consecutiva (con solo julio/agosto-2026 aprobadas, hoy activarlo tendría efecto en, como mucho, un mes) — depende del mismo crecimiento natural de datos que la Fase B del backtest (§2.3).

---

## 4. Fases de implementación

| Fase | Contenido | Depende de | Bloqueo |
|---|---|---|---|
| **A** | Backtest motor-a-motor (§2.2): script + auditoría 47 | Ninguno | — |
| **B** | Backtest contra metas realmente aprobadas (§2.3) | Fase A (reutiliza el script) | **Espera activa**: ≥6 meses de metas `APROBADA` acumuladas |
| **C** | Evaluación de "días hábiles" (§3.1) | Ninguno | **Bloqueado por datos**: `dim_feriado`/`es_feriado` sin poblar — se documenta y se cierra sin código salvo nueva evidencia |
| **D** | Cartera activa del vendedor (§3.2) | Auditoría previa (`SELECT`, cuantificar cambios de cartera reales) | — |
| **E** | Meses no representativos (§3.3) | Fase A (para calibrar el umbral con evidencia del backtest) | — |
| **F** | Tope de variación intermensual (§3.4) | Ninguno para el código; efecto real limitado hasta que exista una segunda meta aprobada consecutiva | Mismo crecimiento de datos que la Fase B |

**Orden recomendado de ejecución real:** A → F → D → E, dejando C cerrado por ahora y B en espera pasiva (se revisa cuando se retome el módulo, no se persigue activamente).

---

## 5. Validación exigida

- Fase A: `pytest` nuevo sobre el script de backtest (que produzca el reporte esperado con datos sintéticos controlados); ejecución real contra el EDW documentada en la auditoría 47 con las cifras reales.
- Fases D/E/F: mismo patrón de tests que el motor v2 (auditoría 46) — cada factor nuevo con tests unitarios que prueben que, desactivado (default), el comportamiento es idéntico al motor v2 actual (no debe cambiar nada para nadie hasta que gerencia lo active explícitamente).
- `pytest backend/tests/unit` completo sin regresiones antes de cerrar cualquier fase.
- Ninguna fase de este plan escribe sobre `metas_comerciales_operativas` en producción sin que gerencia haya revisado el impacto en la pestaña de previsualización ya existente.

---

## 6. Decisiones que requieren al usuario

1. **Fase C (días hábiles):** ¿confirma cerrar sin implementar, dado el bloqueo real de datos (`es_feriado` sin poblar), o prefiere una aproximación fin-de-semana-only pese a su fundamentación débil?
2. **Prioridad entre D/E/F:** este plan recomienda F primero (más simple, efecto más directo), pero puede reordenarse.
3. **Fase B:** confirma que es aceptable dejarla en espera pasiva (sin generar metas aprobadas artificialmente para acelerarla).
