# 19 — Grano vendedor en Metas y Comisiones + meta futura razonable

- **Fecha:** 2026-07-10
- **Objetivo:** corregir dos problemas reportados en el módulo Metas y Comisiones
  (`docs/modulo_metas.md`, `docs/auditoria/14-17_...md`): (1) duplicación de
  registros de meta/comisión por incluir la sucursal en el grano, y (2) metas para
  meses futuros muy elevadas frente a la venta real.
- **Alcance:** `backend/app/repositories/goal_repository.py`,
  `backend/app/models/goal.py`, `backend/app/services/{goals_service,
  goal_ml_service, commission_service, goal_calculation_engine}.py`,
  `backend/app/schemas/{goal,commission,analytics}.py`,
  `backend/app/api/routes/{goals,sales}.py`, tests unitarios de los servicios
  afectados, frontend (`types/goals.ts`, `types/ventas.ts`,
  `components/goals/{CommissionTracker,GoalsConsole,VendorGoalDashboard}.tsx`),
  migración manual sobre `public.metas_comerciales_operativas` (Docker,
  `bi_postgres_edw`).
- **Método:** validación contra el EDW real (Docker) con `SELECT` antes de tocar
  código (regla del CLAUDE.md raíz), lectura de la skill de proyecto
  `ml-training-pipeline` para evaluar el riesgo de mismatch entrenamiento/servicio
  antes de tocar features de `goals_rf`.
- **Estado:** ✅ Implementado y validado en vivo contra el EDW real.

---

## 1. Validación contra el EDW: la tabla del usuario es Venta Neta por vendedor

El usuario reportó valores mensuales de ventas 2026 por "sucursal" (columnas EL REY,
LOS CHASQUIS, W.SANCHEZ, LUIS SANCHEZ, PELILEO, SALCEDO, L.LOPEZ, IZAMBA,
ATAHUALPA, CHATARRA) y pidió corroborar contra el EDW antes de corregir la meta
futura. Se validó vía `SELECT` contra `bi_postgres_edw`:

- Enero 2026: ventas brutas EDW `$384,590.75` − devoluciones `$16,146.94` =
  **`$368,443.81`**, contra `$368,443.60` de la tabla del usuario -- coincide
  (diferencia de centavos por redondeo). Confirma que la tabla es **Venta Neta**
  (ventas − devoluciones), no venta bruta, y que las columnas corresponden a
  **vendedores** (`edw.dim_vendedor`), no a sucursales físicas (`edw.dim_sucursal`
  solo tiene 7 sucursales: Matriz, El Rey, Izamba, Los Chasquis, Pelileo, Salcedo,
  y "Cerrado"; los 24 vendedores activos no coinciden 1 a 1 con esas 7).
- Esto confirma que **Venta Neta** (ya usada por `IQRGoalCalculationEngine` vía
  `GoalRepository.get_vendor_monthly_history`, auditoría 16) es la base correcta
  para medir cumplimiento y para generar la meta futura, no la venta bruta que usa
  `goals_rf`.

## 2. Causa raíz de la duplicación: `dim_vendedor` no tiene sucursal propia

```sql
SELECT v.codven, v.nombre_vendedor, COUNT(DISTINCT s.nombre_sucursal) AS n_sucursales
FROM edw.fact_ventas_detalle f
JOIN edw.dim_vendedor v ON f.vendedor_sk = v.vendedor_sk
JOIN edw.dim_sucursal s ON f.sucursal_sk = s.sucursal_sk
JOIN edw.dim_fecha d ON f.fecha_sk = d.fecha_sk
WHERE d.anio = 2026
GROUP BY v.codven, v.nombre_vendedor ORDER BY n_sucursales DESC;
```

Resultado: `VEN13 ALMACEN ATAHUALPA` transacciona en **7** sucursales distintas en
2026; `VEN01 ALMACEN EL REY`, `VEN03`, `VEN15`, `VEN16`, `VEN02` en 6. `edw.dim_vendedor`
no tiene una columna de sucursal (confirmado con `\d edw.dim_vendedor`) -- el vendedor
no está atado a una sola sucursal en el modelo de datos del ERP.

Como `public.metas_comerciales_operativas` tenía grano
`(anio, mes, id_vendedor_origen, sucursal)`, `GoalRepository.get_sales_trend_for_goals`
generaba una fila de tendencia (y por lo tanto una meta) **por cada combinación**
vendedor×sucursal. Verificado en los datos reales antes de la corrección:

```
anio | mes | id_vendedor_origen | n_filas | suma_metas
2026 |   7 | VEN13              |       6 | 226761.63   -- 1 solo vendedor, 6 metas
2026 |   7 | VEN01              |       6 |  85022.76
...
Total julio 2026: 42 filas para solo 9 vendedores.
```

## 3. Causa raíz de la inflación: piso `max(ventas_ant, y_pred)` en `goals_rf`

`GoalsService.predict_goal_amount` (`backend/app/services/goals_service.py`, antes
de la corrección) calculaba una predicción acotada (`y_pred`, ya limitada contra el
promedio móvil ±20% y el mismo mes del año anterior) pero luego aplicaba:

```python
meta_monto = max(ventas_ant, y_pred) * factor_presion
```

Esto garantizaba que la meta **nunca podía ser menor** a la venta bruta del mes
anterior, sin importar lo que dijera el modelo o la tendencia -- ignorando por
completo la señal de "meses con bajo rendimiento" o estacionalidad decreciente.
Combinado con la duplicación por sucursal (§2), el efecto compuesto explica los
totales muy por encima de lo real que reportó el usuario (total proyectado 2026:
`$4,116,349.56` contra `$2,053,490.21` reales a la fecha).

## 4. Decisión (confirmada con el usuario): reparar `goals_rf` Y cambiar el generador oficial

Se presentaron 3 opciones al usuario; eligió **ambas**:

1. **Reparar el bug de `goals_rf`**: se quitó el piso `max(ventas_ant, y_pred)`.
   Ahora `meta_monto = y_pred * factor_presion` (`y_pred` ya acotado). Este número
   sigue existiendo solo como cifra informativa `meta_sugerida_ia` en el panel del
   vendedor -- ya no se persiste ni paga comisión.
2. **Motor oficial de metas = `IQRGoalCalculationEngine`**: se movió
   `generate_proposals` de `GoalsService` a `GoalMLService.generate_proposals`, que
   persiste `meta_sugerida_estadistica` (motor IQR sobre Venta Neta, ya con 17 tests
   existentes) en vez de `goals_rf`. Este motor ya implementaba exactamente lo
   pedido por el usuario: ventana de 12-24 meses, recorte de picos vía IQR (Tukey),
   tendencia de los últimos meses con atenuación por variabilidad (CV) -- sin
   reentrenar nada.

No se reentrenó `goals_rf` -- se evitó deliberadamente (ver skill
`ml-training-pipeline` y precedente de la auditoría 16 §7.1, donde reentrenar sobre
Venta Neta empeoró el R² de 0.126 a 0.043 y se revirtió). `goals_rf` deja de ser el
generador oficial, así que ese riesgo ya no aplica al monto que se paga.

## 5. Grano vendedor: cambios de esquema y consultas

`public.metas_comerciales_operativas` pasó de grano
`(anio, mes, id_vendedor_origen, sucursal)` a `(anio, mes, id_vendedor_origen)`.
Migración manual aplicada contra `bi_postgres_edw` (Docker; los DDL de `edw/` no
gestionan esta tabla -- la crea `Base.metadata.create_all`, ver CLAUDE.md raíz):

```sql
DELETE FROM public.metas_comerciales_operativas WHERE anio = 2026 AND mes IN (7, 8);
ALTER TABLE public.metas_comerciales_operativas DROP COLUMN sucursal;
```

Se eliminaron 74 filas de prueba (41 `PROPUESTA` + 1 `APROBADA` de 2026-07/08,
generadas en la sesión de validación de la auditoría 17 -- la fila `APROBADA` tenía
el monto `$115,128.27`, literalmente el ejemplo de `docs/modulo_metas.md` línea 153,
confirmando que no era un dato de negocio real). No había datos de producción en
riesgo.

Todas las consultas de `GoalRepository` que agregaban por `(vendedor, sucursal)`
pasaron a agregar por vendedor únicamente (sumando Venta Neta/ventas de TODAS sus
sucursales): `get_sales_trend_for_goals`, `find_proposal`, `insert_proposal`,
`get_commission_report`, `get_commission_tracking_rows`,
`get_vendor_net_sales_period`, `get_goal_for_period`, `get_post_goal_invoices`,
`get_vendor_monthly_history`, `get_vendor_transactions_history`.

## 6. Ventana de la tendencia: "2 años atrás y 3-4 meses recientes, sin picos"

`get_sales_trend_for_goals` tenía dos problemas de ventana, ahora corregidos:

- `Seasonality` (estacionalidad interanual) no tenía límite de años -- se acotó a
  `anio >= :anio - 2` (últimos 2 años, tal como pidió el usuario).
- `CurrentYearMonths`/`TrendSinMax` (tendencia reciente) usaban "meses del año
  calendario en curso", inconsistente entre enero (0 meses previos) y diciembre (11
  meses) -- se reemplazó por una ventana **rodante** de los últimos 4 meses
  completos anteriores al mes objetivo (`ROW_NUMBER() ... <= 4`), consistente todo
  el año y alineada literalmente con "3 o 4 meses atrás". Se mantiene la exclusión
  del mes máximo del segmento (cuando hay más de 2 puntos) como recorte de picos.

Nota de trazabilidad: este cambio de ventana también afecta las features de
entrada de `goals_rf` (`promedio_movil_3m`, `indice_estacional_relativo`) respecto
a como fue entrenado -- aceptable porque `goals_rf` ya no es el generador oficial
(§4) y queda solo como cifra informativa, con su propio capping 0.8-1.2.

## 7. Resultado verificado en vivo (Docker, tras reiniciar el backend)

`POST /gerencia/goals/generate?anio=2026&mes=7&pressure_factor=1.1`:

| Antes (por sucursal, goals_rf) | Después (por vendedor, IQR) |
|---|---|
| 42 filas para 9 vendedores | **9 filas, una por vendedor** |
| `VEN13`: 6 filas, suma `$226,761.63` | `VEN13`: 1 fila, `$105,986.93` |

`GET /gerencia/goals/commissions?anio=2026&mes=7`: una fila por vendedor, sin
columna `sucursal`, montos de meta en el mismo orden de magnitud que la Venta Neta
mensual real observada en el EDW (~$60K-$106K vs. picos previos de $226K).

## 8. Frontend

- `types/goals.ts` (`GoalProposal`, `VendorCommissionRow`) y `types/ventas.ts`
  (`MetaSugerida`, `MiComision`): se quitó el campo `sucursal` (se dejó
  `ForecastCierre.sucursal`, que es un concepto distinto -- pronóstico de ventas
  por sucursal del rol `ventas`, no del grano de metas).
- `CommissionTracker.tsx`, `GoalsConsole.tsx`: se quitó la columna "Sucursal" de la
  tabla.
- `VendorGoalDashboard.tsx`: se quitó la línea de header "Sucursal: ..." (ya no
  aplica -- el vendedor vende en todas las sucursales, no en una sola).

## 9. Validación

- `cd backend && python -m pytest tests/unit -q` → **77/77 passed** (incluye 2
  tests nuevos de `GoalMLService.generate_proposals`: una fila por vendedor sin
  duplicar por sucursal, y que no se pisa una meta `APROBADA`).
- Migración manual aplicada contra `bi_postgres_edw` (Docker): `DELETE` (74 filas de
  prueba) + `ALTER TABLE ... DROP COLUMN sucursal`.
- Extremo a extremo contra el EDW real (login `gerencia@empresa.com`):
  `POST /gerencia/goals/generate` (2026-07) → 9 filas; `GET .../commissions` → una
  fila por vendedor con montos razonables; `GET .../mi-comision` (usuario
  `ventas_gye@empresa.com`) → responde sin error 500 (limitación ya documentada en
  la auditoría 17: `id_vendedor_origen="102"` no coincide con ningún `codven` real).
- `npx tsc -b --noEmit` (frontend) → limpio (el único error reportado,
  `DashboardGerencia.tsx:12` `fmtFull` sin usar, es preexistente, no se tocó).
- No se verificó visualmente en navegador (sin herramienta de automatización de
  navegador disponible en este entorno) -- pendiente de revisión manual de
  `CommissionTracker`, `GoalsConsole` y `VendorGoalDashboard` sin la columna/línea
  de sucursal.

## 10. Pendiente / fuera de este alcance

- Reentrenar `goals_rf` sobre Venta Neta o sobre el nuevo grano de vendedor -- no
  solicitado; el modelo queda solo como cifra informativa (§4).
- `forecast_cierre`/`get_sales_goals` (KPIs de ventas por sucursal, rol `ventas`) no
  se tocaron -- es un concepto distinto (ventas totales de una sucursal, no metas
  por vendedor) y no causaba duplicación.
- Los 24 vendedores sin usuario de plataforma vinculado (o vinculados con código
  inconsistente, como `ventas_gye@empresa.com` → `id_vendedor_origen="102"`) siguen
  sin resolver -- prerrequisito operativo ya señalado en la auditoría 14/17.
