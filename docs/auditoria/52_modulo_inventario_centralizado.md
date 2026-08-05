# Auditoría 52 — Módulo de Gestión de Inventario y Reabastecimiento (MGIR)

> **Fecha:** 2026-08-04
> **Alcance:** Fases 0-4 y 7 de `docs/features/plan_modulo_inventario_reabastecimiento.md`
> (corte de valor mínimo del plan) — aplicadas en la misma sesión, petición explícita del
> usuario ("implementa el plan que esta diseñado"). Fase 0 cuantifica las duplicidades
> D-1..D-6 identificadas por lectura de código; Fases 1-4/7 las estructuran y corrigen sin
> tocar la decisión de negocio pendiente (Fase 5, D-1/D-2, ver más abajo). Método: `SELECT`
> real contra `bi_postgres_edw` vía scripts de un solo uso ejecutados dentro del
> contenedor `bi_backend` (`docker exec`, código montado en vivo con `--reload`), sin
> ningún `INSERT`/`UPDATE`/`DELETE`. Scripts descartados tras cada corrida, no versionados.

## A-0.1 — Inventario de consumidores de cada fórmula duplicada

| Fórmula | Función | Llamadores | Endpoint | Pantalla |
|---|---|---|---|---|
| Punto de reorden determinista | `WarehouseService._punto_reorden_efectivo` | `_enriquecer_producto`, `_necesidad_compra_completo`, `_inventario_matriz_completo`, `_stock_reorden_filas` | `/kpis`, `/stock-reorden`, `/necesidad-compra`, `/inventario-matriz`, `get_notificaciones`, 5 reportes | `DashboardBodega`, `BodegaAlmacenes`, `BodegaReportes`, campana de notificaciones |
| Punto de reorden estocástico | `replenishment_engine.punto_reorden` | `ReplenishmentService.get_lista_reabastecimiento` | `/reabastecimiento/{lista,resumen,alertas,lista/{codart}/explicacion}`, `/simular`, `/propuestas` | `BodegaReabastecimiento` |
| Estado de stock | `WarehouseService._estado_stock` | `_enriquecer_producto` | mismos que arriba | mismas que arriba |
| Riesgo de quiebre | `replenishment_engine.evaluar_riesgo` | `ReplenishmentService.get_lista_reabastecimiento` | mismos que arriba | `BodegaReabastecimiento` |
| Coeficiente de variación | `WarehouseService._justificacion_transferencia` (vía `BODEGA_CV_*`) | `_transferencias_completo` | `/transferencias-sugeridas` | `BodegaAlmacenes` |
| Coeficiente de variación | `replenishment_engine.coeficiente_variacion` (vía `CORTE_XYZ_*`) | `ReplenishmentService.get_lista_reabastecimiento` | `/reabastecimiento/*` | `BodegaReabastecimiento` |

Confirmado: **D-1..D-5 son reales**, no hipótesis. Ningún llamador nuevo encontrado fuera
de los ya documentados en el plan.

## A-0.2 — Cuantificación de D-1/D-2 contra el EDW real

Universo evaluado: **8.153 artículos** (`(producto, almacén)`, sin restricción de RLS —
corrida como si fuera `todos_los_almacenes=True`, equivalente al alcance más amplio
posible).

**Distribución del estado determinista** (`WarehouseService._estado_stock`, ventana de
30 días, ROP fijo `LT+SS` en días):

| Estado | Artículos | % |
|---|---:|---:|
| Seguro | 4.941 | 60,6% |
| Inmovilizado | 2.793 | 34,3% |
| Exceso | 259 | 3,2% |
| Crítico | 101 | 1,2% |
| Cerca | 59 | 0,7% |

**Distribución del riesgo estocástico** (`replenishment_engine.evaluar_riesgo`, ROP con
`z·σ·√LT`, nivel de servicio por clase ABC, lead time resuelto por producto/categoría):

| Riesgo | Artículos | % |
|---|---:|---:|
| Crítico | 4.110 | 50,4% |
| Bajo | 2.143 | 26,3% |
| Sin demanda | 1.764 | 21,6% |
| Medio | 118 | 1,4% |
| Alto | 18 | 0,2% |

**Hallazgo central (confirma y agrava D-1/D-2, severidad ALTA):** de los 4.941 artículos
que el motor determinista clasifica como **"Seguro"**, **4.045 (81,9% de ese grupo, 49,7%
del catálogo total)** el motor estocástico los clasifica como **riesgo crítico**. Un
usuario de Bodega que solo mira `/bodega/almacenes` (determinista) ve la mitad del
catálogo como "sin problema" mientras la misma mitad aparece "riesgo crítico" en
`/bodega/reabastecimiento` (estocástico), sin ninguna explicación de por qué difieren.

En sentido inverso el efecto es mucho menor: solo 8 de 8.153 artículos (0,1%) son
"Crítico" (determinista) pero "bajo/sin_demanda" (estocástico) — la fórmula determinista
casi nunca sub-alerta respecto a la estocástica; el problema real es el sentido opuesto
(sobre-confianza del motor determinista, que no ve venir el 49,7% de los quiebres que el
motor estocástico sí detecta).

Esta cifra es consistente con y **amplía** el hallazgo A-0.7 de la auditoría 50 (54,2% de
los SKU con venta en 30 días cambia el ROP más de un 30% al cambiar de fórmula): aquí se
confirma que ese cambio de magnitud efectivamente cruza el umbral de clasificación de
riesgo en la mitad del catálogo, no solo cambia el número.

**Consecuencia para la Fase 5 del plan:** la discrepancia es demasiado alta para
"convivencia silenciosa". Como mínimo, cada pantalla debe declarar explícitamente qué
motor usa (opción (a) del plan); la opción (b) — estocástico como oficial — tiene ahora
evidencia cuantitativa más fuerte a su favor, pero sigue siendo una decisión de gerencia,
no una decisión de este refactor.

## A-0.3 — Medición de rendimiento (D-6)

Flujo real medido dentro del contenedor (`ReplenishmentService`, sin caché, catálogo
completo sin restricción de almacén):

| Operación | Tiempo | Pasadas completas acumuladas sobre las 8.153 filas |
|---|---:|---:|
| `get_resumen()` | 0,45 s | 1 |
| `+ get_alertas()` | 0,39 s | 2 |
| `+ simular(...)` | 0,80 s | 4 (`simular` hace 2 pasadas: actual + simulado) |
| **Total (flujo típico de abrir la página + campana de notificaciones)** | **1,64 s** | **4** |

Confirma D-6: abrir `/bodega/reabastecimiento` con la campana de notificaciones activa
(que llama `get_alertas` vía `NotificationService._generar_bodega`) ya dispara 2 pasadas
completas antes de que el usuario toque el simulador; usar el simulador duplica el
trabajo otra vez. Target de la Fase 4: reducir a 1 pasada por request real (memoización),
y a 2 en el caso del simulador (actual + simulado, irreducible por diseño — son cálculos
distintos).

También confirma D-3: `get_inventario_productos` (1,03 s) y `get_metricas_reabastecimiento`
(0,33 s) consultan el mismo universo de 8.153 filas con dos agregaciones SQL distintas.

## A-0.4 — Consumidores de fórmulas de inventario fuera de Bodega

`grep` de `punto_reorden|stock_seguridad|cobertura_dias|salida_diaria` sobre
`backend/app/services/`: **solo 3 archivos la usan** — `warehouse_service.py`,
`replenishment_engine.py`, `replenishment_service.py`. Ningún servicio de Gerencia,
Ventas o Administrador calcula estas métricas por su cuenta.

**Hipótesis del requerimiento original refutada:** no hay duplicidad de estas fórmulas
fuera del dominio de Bodega. El alcance del refactor se mantiene acotado a Bodega, tal
como proponía el plan.

## A-0.5 — Cobertura de la RLS por almacén (RN-B10) en las consultas heredadas

`WarehouseRepository.__init__` recibe `almacenes_permitidos: list[str] | None` y lo
aplica en `_filtros_snapshot` (línea 62), el único choke point de filtros del
repositorio. Verificado que **`get_metricas_reabastecimiento`** (línea 193) llama a
`_filtros_snapshot` igual que el resto de las ~14 funciones públicas — no hay una ruta
paralela que la esquive. **Sin hallazgos**: el refactor de repositorio (Fase 1) puede
mover este método sin riesgo de perder la RLS, siempre que se preserve la llamada a
`_filtros_snapshot` (verificado también por `test_bodega_rls.py`, que debe seguir en
verde en cada fase).

## A-0.6 — Cobertura de tests existente (red de seguridad del refactor)

- `test_replenishment_engine.py` — motor puro, 50 tests (según CLAUDE.md).
- `test_replenishment_service.py` — orquestación del servicio.
- `test_warehouse_estado_stock.py` — `_estado_stock`/`_enriquecer_producto` deterministas.
- `test_warehouse_prediccion_compras.py` — no relacionado con reorden, sin tocar.
- `test_bodega_rls.py` — RLS por almacén, debe seguir verde en cada fase.

Baseline capturado antes de iniciar la Fase 1: **`pytest backend/tests/unit` → 363
passed, 0 failed.** Cualquier fase que modifique este conteo o toque un test existente
sin que la fase lo justifique explícitamente es una señal de alarma (cambió
comportamiento, no solo estructura).

## Addendum — Fase 3 aplicada (unificación de `coeficiente_variacion`, D-4)

`WarehouseService._justificacion_transferencia` pasó a llamar
`inventory_engine.coeficiente_variacion` en vez de calcular `std/media` inline. Efecto
real del cambio: la función compartida exige `meses_con_venta >= MESES_MINIMOS_CV` (3)
para devolver un CV, mientras el cálculo inline anterior solo exigía `demanda_media > 0`
(sin piso de meses). Verificado en vivo contra `GET /transferencias-sugeridas`
(212 sugerencias reales sobre el catálogo completo, sin restricción de almacén): **0 de
212** tienen exactamente `meses_con_venta_destino == 2` (el único valor que el cambio
podría afectar, dado que `BODEGA_MIN_MESES_VENTA=2` ya exigía como mínimo 2 meses para
llegar a ser candidato de transferencia). **Sin impacto real en producción.** Los cortes
de clasificación (`BODEGA_CV_ALTA`/`BODEGA_CV_MEDIA` para confianza de transferencia,
`CORTE_XYZ_X`/`CORTE_XYZ_Y` para ABC/XYZ) se mantienen como dos juegos de constantes
separados a propósito (auditoría 50 A-0.4), solo la fórmula del CV en sí quedó unificada.

## Criterio de salida de la Fase 0

A-0.2 muestra una discrepancia **alta** (49,7%, no el <10% que el plan fijó como umbral
para unificar directamente) → **la Fase 5 (unificación de motores) se confirma como
decisión de gerencia con evidencia**, no se ejecuta en esta sesión. Las Fases 1-4 y 7
(estructura, absorción de fórmulas sin cambiar su comportamiento, unificación de CV,
rendimiento, guardas de frontera) proceden según lo planificado — ninguna de ellas
depende de resolver D-1/D-2, solo de organizarlos dentro del mismo módulo con
transparencia sobre la diferencia.

## Aplicado en esta sesión (Fases 1, 2, 4, 7)

**Fase 1 — Paquete `backend/app/inventory/`.** `replenishment_engine.py` →
`app/inventory/engine.py`, `replenishment_service.py` → `service.py`,
`replenishment_config_service.py` → `config_service.py`,
`replenishment_config_repository.py` → `repository.py`,
`replenishment_proposal_repository.py` → `proposals.py`, `schemas/replenishment.py` →
`schemas.py`. `__init__.py` reexporta la API pública (`engine`, `ReplenishmentService`,
`ReplenishmentConfigService`, `ReplenishmentConfigRepository`,
`ReplenishmentProposalRepository`) — `dependencies.py`, `routes/replenishment.py` y
`notification_service.py` actualizados para importar de ahí. Validado: `pytest
backend/tests/unit` mismo conteo exacto (363 passed) antes y después del movimiento;
`import app.main` limpio.

**Fase 2 — Absorción de fórmulas deterministas.** `WarehouseService._salida_diaria` /
`_punto_reorden_efectivo` / `_dias_inventario` / `_estado_stock` pasan a delegar en
4 funciones puras nuevas de `engine.py` (`demanda_diaria_simple`,
`punto_reorden_determinista`, `dias_inventario`, `estado_stock`), que reciben los
umbrales de `settings.BODEGA_*` por parámetro (el motor no importa `settings`). Mismo
resultado exacto — los 363 tests existentes (incluidos los de
`test_warehouse_estado_stock.py`) pasaron **sin modificarse**. 12 tests nuevos directos
sobre las 4 funciones en `test_replenishment_engine.py`.

**Fase 3 — `coeficiente_variacion` unificado (D-4).**
`WarehouseService._justificacion_transferencia` pasó a llamar
`inventory_engine.coeficiente_variacion` en vez de calcular `std/media` inline (ver
addendum arriba). Impacto real medido: **0 de 212** transferencias sugeridas reales
afectadas.

**Fase 4 — Memoización (D-6).** `ReplenishmentService._evaluar_catalogo` (nuevo, privado)
concentra la evaluación cara del catálogo (~8.153 artículos) con una caché por instancia
de servicio (`self._cache_catalogo`, clave = filtros de alcance + overrides del
simulador) — segura porque el servicio se construye una instancia nueva por request vía
`Depends` y la RLS por almacén ya viaja inyectada en `warehouse_repo`. `get_lista_
reabastecimiento` pasa a ser un wrapper barato (post-filtros + orden sobre una COPIA de
la lista cacheada, nunca mutándola in situ). Verificado en vivo contra `bi_backend`
(hot-reload) con datos reales del EDW: el flujo `resumen + alertas + simular` pasó de
**4 llamadas / 1,64s** (línea base, A-0.3) a **2 llamadas / 0,87s** (las 2 restantes son
irreducibles por diseño: actual + simulado del simulador, cálculos genuinamente
distintos) — **~47% más rápido**, con los mismos números exactos que la línea base
documentada (`productos_riesgo_critico=4110`, `costo_total_compra_sugerida=$601.812,60`,
`total_articulos_evaluados=8153`): **cero cambio de comportamiento, solo de costo**. 4
tests de guarda nuevos en `test_replenishment_service.py`
(`TestMemoizacionCatalogo`), incluido uno que confirma que los post-filtros no mutan la
lista cacheada compartida.

**Fase 7 — Guarda de frontera.** `test_inventory_module_boundary.py` (nuevo): verifica
por AST que `engine.py` no importa `app.repositories`/`app.models`/`app.database`/
`app.core.config`/`app.ml`/`sqlalchemy` (motor puro, invariante estructural) y que
ninguna de sus funciones recibe un parámetro `db`/`session`; verifica también que
`app.inventory.__init__` sigue exponiendo su API pública completa. **Ajuste sobre el
texto original del plan:** la regla de frontera "nadie importa `app.inventory.engine`
directamente" (§3 del plan) se relajó deliberadamente — la Fase 2 exige que
`WarehouseService` importe `engine` para las fórmulas deterministas absorbidas, así que
la regla real y enforzada es "el motor es puro", no "nadie más allá del paquete lo toca".

**Fase 6 — Frontend, vistas hijas.** `BodegaReabastecimiento.tsx` (545 líneas, 5
componentes internos sin exportar) pasó de una sola página a un contenedor delgado (~55
líneas) con `Tabs` (mismo patrón ya establecido en `DashboardMetas.tsx` para
Operación/Config/Simulación/Bitácora, preferido sobre rutas independientes nuevas
propuestas originalmente en el requerimiento del usuario porque las 4 vistas comparten
el mismo filtro global de Bodega vía `BodegaFilterBar` -- una ruta por vista habría
exigido mover ese filtro a un store compartido entre rutas sin ganar nada que las
pestañas no dieran ya). 4 componentes nuevos extraídos a `frontend/src/components/
bodega/`: `ReplenishmentListaInteligente.tsx` (Centro de Decisiones + Lista, se
mantienen juntos porque comparten `horizonteDias`/filtros de riesgo-ABC-XYZ),
`ReplenishmentSimuladorPanel.tsx`, `ReplenishmentPropuestasPanel.tsx` (ambos ganan su
propio horizonte local, antes heredado del padre -- decisión de simplicidad al
independizar las pestañas), `ReplenishmentPoliticaPanel.tsx` (pestaña "Configuración",
gerencia/administrador). Sin cambio de contrato HTTP -- los mismos hooks/endpoints de
antes, solo reorganización de componentes.

**Diferido explícitamente (no aplicado en esta sesión):** Fase 5 (decisión de negocio
sobre unificar los dos motores de ROP, requiere a gerencia con la evidencia de A-0.2).

**Validación final:** `pytest backend/tests/unit` → **382 passed** (363 base + 12 + 4 +
3 nuevos, 0 fallas, 0 tests existentes modificados); `bi_backend` reconstruido desde
cero (`docker compose build backend`, no solo hot-reload) con arranque limpio, 4/4
modelos ML, y aplicó en vivo la migración `0018_quitar_anomalias` que CLAUDE.md
documentaba como pendiente de la sesión anterior -- **cierra ese pendiente**; verificado
con datos reales del EDW que el resultado numérico del módulo de Reabastecimiento no
cambió (mismos `productos_riesgo_critico=4110`/`costo_total_compra_sugerida=$601.812,60`
que la línea base). Frontend: `tsc --noEmit` limpio, `oxlint` sin advertencias nuevas
(las 5 preexistentes son de archivos no tocados en esta sesión), `npm run build` limpio
(bundle 1.225,34 kB, en línea con el tamaño documentado de sesiones previas);
`bi_frontend` reconstruido desde cero y reiniciado, arranque limpio.
