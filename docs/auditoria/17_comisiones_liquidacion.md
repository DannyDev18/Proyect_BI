# 17 — Liquidación de comisiones: cumplimiento real, tramos y dashboard vendedor

- **Fecha:** 2026-07-10
- **Objetivo:** implementar la mitad "Comisiones" del módulo Metas y Comisiones
  (`docs/modulo_metas.md`), cerrando el hallazgo R-1 de `docs/auditoria/14_...md`
  (nunca se calculaba cumplimiento real ni comisión devengada, solo se mostraba la
  meta configurada) y los placeholders "Próximamente" del dashboard vendedor
  (`docs/auditoria/15_...md`).
- **Alcance:** backend (`backend/app/services/commission_engine.py`,
  `commission_service.py`, `repositories/goal_repository.py`, rutas `goals.py`/`sales.py`,
  schemas), frontend (`components/goals/GoalProgressGauge.tsx` [D3],
  `CommissionTracker.tsx`, `VendorGoalDashboard.tsx`, tipos/servicios/hooks).
- **Skills usadas (a pedido explícito del usuario):** `backend-ml-serving` (frontera
  serving/ML, no aplicó cambios directos aquí pero se respetó el patrón de capas),
  `claude-d3js-skill-main` (medidor de progreso), `frontend-design` (integración visual
  del nuevo medidor dentro del sistema de diseño ya establecido).
- **Estado:** ✅ Implementado y validado contra el EDW real (Docker).

---

## 1. Resolución de una ambigüedad del `.md` (documentada antes de implementar)

`docs/modulo_metas.md` tiene dos secciones con reglas de comisión que no coinciden
exactamente:

- Nota informal (línea 4): "si las ventas son menores a 90% no pagaría la comisión".
- Sección detallada "PROPUESTA IA" (Fase 4): 4 tramos — Excelente (≥100%): 7%+2%+$500;
  Meta (90-100%): 7%; **Cerca (80-89%): 5% sin bono**; Lejos (<80%): 0%.

La nota informal y la versión detallada se contradicen en el tramo 80-89% (¿paga o no
paga?). Se priorizó la versión detallada ("PROPUESTA IA") por ser la especificación
completa y estructurada del mismo documento — no es una regla nueva inventada, es la
parte del `.md` con más detalle resolviendo la ambigüedad de la parte informal.

## 2. Motor de comisión (`backend/app/services/commission_engine.py`)

Cálculo puro (sin acceso a BD), mismo patrón que `goal_calculation_engine.py`. En vez de
hardcodear 7%/5%/2%/$500 (los números del ejemplo del enunciado), se generalizan como
fracciones/adicionales sobre los campos **ya existentes y editables** de `Goal`
(`comision_base_pct`, `bono_sobrecumplimiento`, seteados por gerencia en
`PUT /gerencia/goals/{id}/review`):

- Tasa del tramo "Meta" (90-100%) = `comision_base_pct` tal cual.
- Tasa "Excelente" (≥100%) = `comision_base_pct + 2.0pp` (constante
  `BONUS_TASA_EXCELENTE_PP`, generaliza el "+2% adicional" del ejemplo) + bono fijo
  `bono_sobrecumplimiento`.
- Tasa "Cerca" (80-89%) = `comision_base_pct * (5/7)` (constante `FACTOR_TASA_CERCA`,
  generaliza la proporción 5%/7% del ejemplo a cualquier tasa base configurada).
- Tasa "Lejos" (<80%) = 0%.

Casos borde cubiertos (con test): `monto_meta<=0` no divide por cero (devuelve LEJOS/0%,
no un 100% arbitrario); `venta_real` negativa (vendedor con más devoluciones que ventas
en el período) no genera una comisión negativa; el umbral exacto 100% cae en EXCELENTE,
no en META.

## 3. Repositorio (`GoalRepository`, nuevos métodos)

Reutiliza el patrón de CTEs agregados por separado ya usado para Venta Neta
(`docs/auditoria/16_...md`) — ninguno de estos métodos JOINea `fact_ventas_detalle` con
`fact_devoluciones` directamente:

- `get_commission_tracking_rows(anio, mes)`: una fila por meta configurada, con su
  Venta Neta real ya resuelta — la consulta que faltaba (R-1). Panel gerencial.
- `get_vendor_net_sales_period(vendedor_origen, sucursal, anio, mes)`: Venta Neta de UN
  vendedor en UN período específico (a diferencia de `get_vendor_monthly_history`, que
  trae una serie de varios meses). Panel del vendedor.
- `get_goal_for_period(...)`: la meta ORM de un vendedor/sucursal/período (`Goal | None`).
- `get_post_goal_invoices(...)`: facturas del vendedor en el período con Venta acumulada
  (`SUM(...) OVER (ORDER BY fecha, num_factura)`), filtradas a las que quedan a partir de
  cruzar la meta. **Limitación documentada explícitamente en el código**: el acumulado usa
  venta bruta por factura, no neta línea por línea, porque `fact_devoluciones` no
  referencia `num_factura` — es una aproximación razonable para ubicar el punto de cruce
  ("qué está vendiendo después de llegar a la meta"), no para el monto exacto de
  comisión (ese cálculo sí usa Venta Neta real vía `get_vendor_net_sales_period`).

## 4. Servicio y endpoints nuevos

`CommissionService` (nuevo, `backend/app/services/commission_service.py`), inyectado vía
`CommissionServiceDep` (mismo patrón `Repository → Service → Route` del resto del
proyecto):

| Endpoint | Rol | Propósito |
|---|---|---|
| `GET /gerencia/goals/commissions?anio&mes` | gerencia, administrador | Cumplimiento real + tramo + comisión de todos los vendedores del período (reemplaza conceptualmente a `get_commission_report`, que sigue existiendo sin tocar para no romper `/tracking`) |
| `GET /analytics/ventas/goals/mi-comision` | ventas (filtrado por `current_user.id_vendedor_origen`) | Mi comisión del mes en curso: meta, venta real, tramo, tasa, bono, días restantes, alerta de última semana |
| `GET /analytics/ventas/goals/facturas-post-meta` | ventas | Facturas emitidas después de cruzar el 100% de mi meta |

**Filtrado por vendedor individual**: se eligió el camino más barato de los dos que
planteaba `docs/auditoria/14_...md §4` — no se creó un 5º rol `vendedor`; se reutiliza el
rol `ventas` agregado, filtrando por `current_user.id_vendedor_origen` (mismo patrón ya
usado en `/goals/meta-sugerida`). La limitación de datos ya documentada (24/25 vendedores
sin usuario de plataforma vinculado, y el único vinculado con un código inconsistente)
sigue vigente y no se resolvió aquí — es un prerrequisito operativo fuera de este alcance.

## 5. Frontend

- **`GoalProgressGauge.tsx`** (nuevo, D3 directo vía `useRef`+`useEffect`, patrón A de la
  skill `claude-d3js-skill-main`): medidor semicircular con 4 bandas de color que son los
  umbrales reales de comisión (0-80/80-90/90-100/100-130%), no decorativas, y una aguja
  animada (`d3.easeCubicOut`, respeta `prefers-reduced-motion`). Reemplaza la barra lineal
  plana del dashboard vendedor. Decisión de diseño (skill `frontend-design`): se reutilizan
  los tokens de color ya establecidos (`index.css`, sistema cyan=vivo/amber=ML) en vez de
  inventar una paleta nueva — es una extensión de un sistema de diseño interno ya
  consistente, no un sitio nuevo; el riesgo estético deliberado es el medidor D3 en sí
  (forma, animación, bandas informativas), no el color.
- **`CommissionTracker.tsx`** (nuevo, panel gerencial): tabla de cumplimiento real +
  tramo + comisión por vendedor, mismo sistema visual que `GoalsConsole.tsx` (Tailwind
  plano, no `ChartCard`) para no fragmentar el look del panel de Metas. Montado en
  `DashboardMetas.tsx` junto a `GoalsConsole`.
- **`VendorGoalDashboard.tsx`**: los dos placeholders "Próximamente" (`Comisión`,
  `Facturas post-meta`) ahora muestran datos reales (`useMyCommission`,
  `usePostGoalInvoices`), incluyendo el mensaje de alerta de última semana / meta
  superada.
- Tipos/servicios/hooks nuevos en `types/goals.ts`, `types/ventas.ts`, `services/goals.ts`,
  `services/ventas.ts`, `hooks/goals.ts`, `hooks/ventas.ts`, `constants/queryKeys.ts`
  siguiendo exactamente los patrones ya existentes (no se creó un dominio nuevo).
- **Dependencia nueva**: `d3`/`@types/d3` agregadas a `frontend/package.json` (no estaba
  en el proyecto; el resto de gráficos usa `recharts`). Requirió reconstruir la imagen
  Docker del frontend (`docker compose build frontend`) porque `node_modules` no está
  montado desde el host (solo `./frontend/src`).

## 6. Validación

- `cd backend && python -m pytest tests/unit -q` → **75/75 passed** (17 tests nuevos:
  9 de `commission_engine`, 8 de `commission_service`).
- `npx tsc -b --noEmit` (frontend) → limpio (el único error reportado,
  `DashboardGerencia.tsx:12` `fmtFull` sin usar, es preexistente y no se tocó en esta
  sesión).
- **Extremo a extremo contra el EDW real** (Docker, `docker compose build frontend` +
  `up -d frontend` recreó también `bi_backend`): login real (`gerencia@empresa.com`),
  `POST /gerencia/goals/generate` para 2026-07 y 2026-08, luego
  `GET /gerencia/goals/commissions` — valores reales verificados (ej. vendedor VEN01 /
  SUC. EL REY: meta $59,416.97, venta real $11,530.37, 19.41% cumplimiento, tramo LEJOS,
  comisión $0 — coherente, julio 2026 recién empezó). Confirmado también vía
  `CommissionService` invocado directamente dentro del contenedor del backend (mismos
  números que el endpoint HTTP).
- `GET /analytics/ventas/goals/mi-comision` y `/facturas-post-meta` probados con el único
  usuario de ventas sembrado (`ventas_gye@empresa.com`) — responden sin error 500 pese al
  `id_vendedor_origen` inconsistente ya documentado (degradan a ceros, no rompen).
- **No se verificó visualmente en navegador** (sin herramienta de automatización de
  navegador disponible en este entorno) — se verificó que `GET http://localhost:5173/`
  responde 200 y que el contenedor arrancó sin errores de compilación de Vite/TS. Falta
  una verificación visual manual del medidor D3 y las nuevas tablas antes de darlo por
  completamente validado en UI.

## 7. Pendiente / fuera de este alcance

- Comisión por categoría/artículo (ej. "BAT 3%, Z-999 7%" del enunciado) — requiere una
  tabla de reglas parametrizadas (`bi_reglas_comision`, evaluada y marcada como pendiente
  de decisión de negocio en `docs/auditoria/14_...md §5`); hoy `comision_base_pct` es una
  única tasa por meta, no por categoría.
- Liquidación/cierre inmutable (`bi_comisiones` como tabla append-only,
  `POST .../settle`) — este cambio calcula la comisión **al vuelo** desde datos vivos del
  EDW, no la persiste como un registro de pago cerrado. Sigue siendo la Fase 2 pendiente
  de `docs/auditoria/14_...md §9`.
- Rol `vendedor` individual y alta de usuarios de plataforma para los 24 vendedores sin
  vincular — prerrequisito operativo ya señalado (R-2/R-3), no resuelto aquí.
- Verificación visual manual del medidor D3 y las tablas nuevas en un navegador real.
