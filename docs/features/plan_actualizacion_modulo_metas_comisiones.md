# Plan de Actualización — Módulo Metas y Comisiones (incluye Comisiones Variables)

> **Fecha:** 2026-07-14
> **Estado:** Propuesta (requiere auditoría previa `docs/auditoria/35_actualizacion_modulo_metas.md`)
> **Alcance:** `backend/app/api/routes/goals.py` (prefijo `/gerencia/goals`, 17 endpoints), `goal_ml_service` / `GoalsService` / `IQRGoalCalculationEngine` / `commission_engine`, `frontend/src/pages/DashboardMetas.tsx` + `DashboardMetasVendedor.tsx` + Panel de Simulación de Comisiones (commit `1ac5589`).
> **Contexto crítico:** módulo 100% estadística (sin ML, `goals_rf` decomisionado — auditoría 20); Comisiones Variables en piloto sombra con rollback vía `COMISION_MODO` (regla 13, auditoría 30).

## 0. Diagnóstico preliminar

| # | Hallazgo / sospecha | Evidencia | Severidad |
|---|---|---|---|
| M-1 | **Panel de Simulación de Comisiones recién integrado sin auditoría posterior** (commit `1ac5589` es el más reciente del repo): `POST /commission-simulation` recalcula plano vs variable retroactivo — verificar que usa exactamente el mismo `commission_engine.calcular_comision_variable` que la liquidación real (si simula con una copia de la lógica, divergirá en silencio). | `goals.py:187+`, commit `1ac5589` | Alta (a verificar) |
| M-2 | **Snapshots congelados (salvaguarda 6):** `public.comision_liquidaciones` debe ser inmutable una vez liquidada; verificar que ningún endpoint la reescribe al re-simular o al cambiar la matriz de categorías retroactivamente. | regla 13 | Alta (a verificar) |
| M-3 | **Grano de metas:** las metas son por `(anio, mes, id_vendedor_origen)` — NO por sucursal (auditoría 19). Verificar que ninguna vista del frontend agregue o filtre metas "por sucursal" (sería inventar un dato que el grano no tiene). | regla 10 | Media |
| M-4 | **Campos opcionales por `COMISION_MODO`:** `comision_variable`/`nivel_variable`/`desglose_variable` solo se pueblan si el modo ≠ `plana`. Verificar que el frontend maneja `null`/ausente sin romper (instalación en modo `plana` = contrato original) y que ningún componente asume que siempre vienen. | regla 13 | Media |
| M-5 | **Datos de crédito limitados:** el ajuste por plazo solo tiene datos reales para 0 y 30 días (auditoría 30 H4). La UI de configuración `commission-config/credito` no debe ofrecer plazos sin respaldo de datos como si fueran equivalentes — necesita advertencia o deshabilitado. | auditoría 30 H4 | Media |
| M-6 | **Clasificación de productos:** el código debe clasificar por `dim_producto.clase`/`subclase`, nunca `nombre_clase` (100% vacío — auditoría 30 H2). Re-verificar tras el commit del panel de simulación que nada nuevo lee `nombre_clase`. | auditoría 30 H2 | Alta si reaparece |

## 1. Fase 0 — Auditoría de caza de bugs (entregable: `35_actualizacion_modulo_metas.md`)

1. **Paridad simulación ↔ liquidación (M-1):** liquidar un mes en modo `sombra` y simular el mismo mes con la misma configuración; los montos deben coincidir al centavo por vendedor. Cualquier diferencia = dos implementaciones del motor.
2. **Inmutabilidad de snapshots (M-2):** cambiar la matriz de categorías después de liquidar y verificar que la liquidación histórica no cambia (ni en BD ni en lo que muestra el frontend).
3. **Motor IQR:** tests de propiedad del `IQRGoalCalculationEngine` con series sintéticas: picos extremos (¿el recorte IQR actúa?), historia corta (<24 meses), vendedor nuevo sin historia (¿centinela o error claro?), tendencia negativa (¿el piso de sanidad evita metas absurdas?).
4. **Los tres modos (`plana`/`sombra`/`variable`):** matriz de pruebas de los endpoints `commissions` y `mi-comision` en cada modo — campos poblados correctos, contrato plano intacto en modo `plana` (compatibilidad, no romper instalaciones existentes).
5. **`lineas-sin-costo` (salvaguarda 2):** reconciliar el conteo del endpoint contra el EDW por SELECT; una línea sin costo comisiona margen falso.
6. **RBAC:** `only_management` en config/simulación/análisis; verificar que `mi-comision` del vendedor solo expone SU comisión (no acepta `vendedor_origen` arbitrario).

## 2. Fase 1 — Correcciones (las que confirme la auditoría)

1. Unificar simulación y liquidación sobre el único motor puro `commission_engine` (si M-1 falla).
2. Bloqueo de escritura/versionado sobre `comision_liquidaciones` (si M-2 falla): las liquidaciones se recalculan solo creando una versión nueva, nunca UPDATE del snapshot.
3. UI de crédito con plazos sin datos deshabilitados + tooltip (M-5).
4. Manejo defensivo de campos opcionales en frontend (M-4): tipos TS con `| null` y render condicional.

## 3. Fase 2 — Mejoras de valor

1. **Transparencia del cálculo de meta:** el drawer de revisión de meta muestra el desglose del motor IQR (meses usados, picos recortados, tendencia aplicada, techo/piso activado) — la gerencia hoy aprueba un número sin ver el porqué; el motor ya calcula todo esto internamente.
2. Bitácora de cambios de configuración de comisiones (quién cambió qué factor y cuándo) — crítico porque la config altera dinero; tabla `public.*` append-only.
3. Alerta automática de divergencia plano vs variable > umbral configurable durante el piloto sombra (conectar con el plan del módulo de notificaciones, `plan_modulo_notificaciones.md`).

## 4. Validación

- `pytest` con los tests de propiedad nuevos del motor IQR y del `commission_engine` (funciones puras — testeables sin BD).
- Paridad al centavo simulación/liquidación como test de integración permanente.
- Verificar en los 3 valores de `COMISION_MODO` (variable de entorno, el rollback oficial) que el sistema arranca y los contratos se cumplen.
- Nada de este módulo toca ML ni Producción SAP; validaciones de datos contra el EDW solo con SELECT.

**Reglas transversales:** no reintroducir `goals_rf` ni ML en este módulo (decisión de auditoría 20); grano vendedor sin sucursal (auditoría 19); routers thin; excepciones de dominio; actualizar auditoría 35 y `02_reglas_negocio_validadas.md`.
