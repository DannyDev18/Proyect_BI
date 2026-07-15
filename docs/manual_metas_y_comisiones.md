# Manual del Módulo Metas y Comisiones

> **Fecha:** 2026-07-14
> **Alcance:** módulo completo tal como está implementado hoy en el repositorio — metas automáticas (estadística IQR) + esquema de comisión plano (vigente) + sistema de **Comisiones Variables** por margen/categoría/crédito/tipo de vendedor (piloto en sombra, opcional).
> **Referencias de origen:** `docs/modulo_metas.md` (especificación original), `docs/features/plan_integracion_comisiones_variables.md` (plan de integración), `docs/auditoria/30_comisiones_variables.md` (auditoría de datos), `docs/auditoria/02_reglas_negocio_validadas.md` §15/§18 (reglas RN-CM1..CM4).

---

## Parte 1 — Manual de Usuario

### 1.1 ¿Qué hace este módulo?

Cada mes, la plataforma:

1. **Genera una meta de venta por vendedor** de forma automática, basada en su historial de los últimos 24 meses (sin inventar números: usa estadística — mediana, recorte de picos, tendencia reciente).
2. **Calcula la comisión devengada** de cada vendedor según cuánto vendió respecto a su meta.
3. Opcionalmente (si gerencia lo activa), calcula en paralelo una **comisión alternativa** que paga según el margen real que dejó cada producto vendido, no solo el monto total — sin afectar el pago real hasta que gerencia decida activarla oficialmente.

Hay dos roles con vistas distintas:

- **Vendedor:** ve su propia meta, su progreso, y su comisión — página `Mi Meta y Comisión` (menú Ventas → Metas).
- **Gerencia / Administrador:** ve y aprueba las metas de todos los vendedores, la liquidación de comisiones del mes, y (nuevo) la configuración y simulación del esquema de Comisiones Variables — página `Metas y Comisiones` (menú Gerencia).

### 1.2 Panel del vendedor

Ruta: `/ventas/metas` → componente "Mi Meta y Comisión".

| Sección | Qué muestra |
|---|---|
| **Meta Asignada / Ventas Actuales / Cumplimiento / Restante** | Tarjetas con la meta del mes en curso, lo vendido hasta hoy (Venta Neta = ventas − devoluciones), y cuánto falta. |
| **Progreso hacia la meta** | Medidor circular con el % de cumplimiento y una alerta si estás en la última semana del mes por debajo del 70%. |
| **Pronóstico de cierre del mes** | Proyección de cuánto venderás al cierre del mes (modelo de ventas `sales_rf`) y la probabilidad de alcanzar la meta. |
| **Meta sugerida (próximo período)** | Adelanto de lo que sería tu meta el mes que viene, con el detalle de cuántos meses de histórico se usaron y cuántos se excluyeron por atípicos. |
| **Comisión** | Tu comisión devengada del mes en curso, el tramo alcanzado (Excelente/Meta/Cerca/Lejos), la tasa aplicada y el bono de sobrecumplimiento si aplica. |
| **"Con el sistema nuevo habrías ganado"** | *Solo aparece si gerencia activó el piloto en sombra.* Compara tu comisión actual contra lo que ganarías con el nuevo esquema por margen — es informativo, **no afecta tu pago** mientras esté en modo sombra. |
| **Productos recomendados para cerrar tu meta** | Sugerencias de productos que sueles vender bien, para ayudarte a llegar a la meta. |
| **Facturas post-meta** | Una vez superado el 100%, lista las facturas que emitiste después de cruzar la meta. |

### 1.3 Panel de gerencia

Ruta: `/gerencia/metas` (o el menú "Metas y Comisiones"). Tiene **3 pestañas**:

#### Pestaña "Operación" (la que ya existía)

- **Consola de Metas:** elige el período, ajusta el "Factor de Presión Comercial" (un slider que empuja las metas al alza o a la baja, ej. +10%) y presiona **"Generar Plan con Inteligencia ML"**. Esto crea o actualiza una propuesta de meta para cada vendedor. Desde la tabla puedes editar el monto y el % de comisión de cada propuesta, y **Aprobar** o **Rechazar**.
- **Comisiones devengadas:** tabla con la Venta Neta real, meta, % de cumplimiento, tramo y comisión de cada vendedor en el período elegido. Si el piloto en sombra está activo, aparece una columna adicional "Comisión (variable · piloto)" con el monto que pagaría el esquema nuevo.
- **Vendedores en riesgo / Alta probabilidad / Recomendaciones por categoría:** paneles de IA que resaltan quién va mal encaminado, quién va a superar la meta, y qué categorías conviene empujar.

#### Pestaña "Comisiones Variables · Config" (nueva)

Aquí gerencia configura el esquema de comisión por margen **sin necesidad de programar**. Tiene 3 sub-pestañas:

1. **Matriz de categorías:** define, por código de categoría de producto (ej. `BAT`, `REP`, o `*` como comodín), qué grupo le corresponde (A/B/C/S/X), qué tasa de comisión aplica, si se calcula sobre el **margen** o sobre el **valor** de venta, y un factor estratégico temporal (ej. 1.3x para empujar liquidación de inventario). Cada regla que guardas queda con fecha de vigencia — no se pierde el historial.
2. **Factores de crédito:** tabla editable de cuánto se reduce la comisión según el plazo de pago otorgado al cliente (ej. contado = factor 1.0, 30 días = factor 0.85). Puedes agregar o quitar tramos y guardar todo de una vez.
3. **Tipo de vendedor:** marca cada vendedor como **externo** (factor 1.0, el de referencia) o **interno** (factor 0.70 por defecto, editable) — refleja que un vendedor externo tiene mayor costo de soporte para la empresa. Un vendedor sin configurar se trata automáticamente como externo, nunca se le penaliza por omisión.

> ⚠️ Nota de datos reales (ver auditoría 30): el catálogo de productos no tiene nombres de categoría cargados desde SAP, así que las categorías se identifican por **código** (ej. `BAT` = baterías), no por nombre. Y el ajuste por plazo de crédito hoy solo tiene información real para **contado** y **30 días** — los demás tramos (45/60/90 días) están disponibles para configurar pero sin historial de ventas real que los respalde todavía.

#### Pestaña "Comisiones Variables · Simulación" (nueva)

Antes de activar nada, gerencia puede simular: elige cuántos meses hacia atrás (3/6/12/24) y presiona **Simular**. El sistema recalcula, con datos reales del EDW, cuánto se habría pagado con el esquema plano vs. con el esquema variable configurado, mes a mes y vendedor por vendedor. Muestra:

- Costo total de comisiones en cada esquema.
- % que representa la comisión sobre el margen bruto total generado (el indicador de salud: idealmente entre 15–20%).
- El detalle línea por línea: quién gana más, quién gana menos, y por cuánto.

Esto es lo que permite decidir, con números reales de la propia empresa, si conviene activar el esquema nuevo y con qué tasas.

### 1.4 ¿Cómo se activa el esquema nuevo de verdad?

El sistema tiene 3 modos, controlados por una sola variable de configuración (`COMISION_MODO`), que solo puede cambiar un desarrollador/administrador de infraestructura:

| Modo | Qué pasa |
|---|---|
| **`plana`** (el de siempre, activo por defecto) | Solo se calcula y paga el esquema plano de tasa por tramos. Nada nuevo es visible. |
| **`sombra`** | Se calculan **ambos** esquemas. El pago real sigue siendo el plano, pero tanto vendedores como gerencia ven la comparación ("lo que habrías ganado con el nuevo sistema"). Es el modo recomendado para el piloto de 2–3 meses. |
| **`variable`** | El esquema por margen pasa a ser el oficial. El plano se sigue calculando solo como referencia. |

**Volver atrás es instantáneo:** cambiar `COMISION_MODO` de vuelta a `plana` restaura el comportamiento anterior sin perder nada — cada mes calculado en modo sombra queda guardado como un registro histórico ("liquidación congelada"), así que nunca se pierde el rastro de lo que se calculó.

---

## Parte 2 — Manual del Desarrollador

### 2.1 Arquitectura general

```
Frontend (React)                Backend (FastAPI)                         PostgreSQL (edw + public)
─────────────────                ──────────────────                        ──────────────────────
DashboardMetas.tsx        →      goals.py (router)             →           edw.fact_ventas_detalle
 ├─ GoalsConsole                  ├─ GoalsService                          edw.fact_devoluciones
 ├─ CommissionTracker             ├─ CommissionService                     edw.dim_producto
 ├─ CommissionConfigPanel         ├─ CommissionSimulationService           edw.dim_formapago
 └─ CommissionSimulationPanel     ├─ CommissionConfigService                public.metas_comerciales_operativas
                                  ├─ GoalMLService                          public.comision_matriz_categorias
VendorGoalDashboard.tsx   →      sales.py (router, /goals/mi-comision)     public.comision_factores_credito
                                  └─ commission_engine.py (motor puro)      public.comision_config_vendedor
                                                                             public.comision_liquidaciones
```

El módulo tiene **dos capas de comisión que conviven**:

1. **Esquema plano** (preexistente): `commission_engine.calcular_comision` — tasa sobre Venta Neta total por tramos de cumplimiento (EXCELENTE/META/CERCA/LEJOS). No se tocó.
2. **Esquema variable** (nuevo): `commission_engine.calcular_comision_variable` — función pura adicional, calcula la comisión línea por línea según margen/categoría/crédito/tipo de vendedor.

Ambas conviven porque `settings.COMISION_MODO` decide cuál(es) se ejecuta(n) en cada request.

### 2.2 Archivos clave

| Capa | Archivo | Responsabilidad |
|---|---|---|
| Motor de cálculo (puro, sin BD) | `backend/app/services/commission_engine.py` | `calcular_comision` (plano) y `calcular_comision_variable` (nuevo). Testeado con `backend/tests/unit/test_commission_engine.py` (32 tests, incluye los ejemplos numéricos de la propuesta original como golden tests). |
| Repositorio de datos | `backend/app/repositories/goal_repository.py` | Consultas SQL sobre `edw.*` — venta neta, líneas de venta a grano de línea (`get_commission_lines`), perfil de margen por categoría, líneas sin costo, bonos (cliente nuevo, venta cruzada aceptada), devoluciones. |
| Repositorio de configuración | `backend/app/repositories/commission_config_repository.py` | CRUD de las tablas `public.comision_*` (matriz, crédito, tipo de vendedor) y snapshots de liquidación. Todo con vigencias — nunca se sobreescribe una fila vigente, se cierra y se inserta una nueva. |
| Servicio de liquidación | `backend/app/services/commission_service.py` | `get_commission_tracking` (panel gerencial) y `get_my_commission` (panel vendedor). Según `COMISION_MODO`, calcula uno o ambos esquemas y persiste snapshots. |
| Simulación retroactiva | `backend/app/services/commission_simulation_service.py` | Solo lectura del EDW — recorre N meses, calcula ambos esquemas por vendedor y agrega costos/porcentajes. No persiste nada. |
| Configuración expuesta a gerencia | `backend/app/services/commission_config_service.py` | Envuelve `CommissionConfigRepository` para los endpoints CRUD y los reportes de solo lectura (perfil de categorías, líneas sin costo). |
| Ajuste de metas por tipo de vendedor | `backend/app/services/goal_ml_service.py` (`generate_proposals`, `_ajustar_meta_por_tipo`) | Si hay configuración de tipo de vendedor, multiplica la meta base por `COMISION_META_FACTOR_EXTERNO`/`_INTERNO`, o aplica la regla de vendedor nuevo (60% del promedio del equipo durante los primeros meses). |
| Modelos SQLAlchemy | `backend/app/models/commission_config.py` | `ComisionMatrizCategoria`, `ComisionFactorCredito`, `ComisionConfigVendedor`, `ComisionLiquidacion`. Registrados en `backend/app/database/base.py` para que `Base.metadata.create_all` los cree. |
| DDL espejo | `edw/07_public_app_tables.sql` (sección 5) | Mismo esquema para cuando se levanta un volumen Docker nuevo desde cero (no depende de que el backend arranque primero). |
| Endpoints | `backend/app/api/routes/goals.py` (gerencia) y `backend/app/api/routes/sales.py` (vendedor, `/goals/mi-comision`) | Ver tabla de endpoints abajo. |
| Inyección de dependencias | `backend/app/api/dependencies.py` | Fábricas `get_commission_config_repository`, `get_commission_service`, `get_commission_simulation_service`, `get_commission_config_service`, y sus `...Dep` para los routers. |
| Configuración | `backend/app/core/config.py` (bloque "Comisiones Variables") | Todos los umbrales/tasas por defecto, sin hardcodes — ver tabla completa abajo. |
| Frontend — tipos | `frontend/src/types/commissionConfig.ts`, campos añadidos en `types/goals.ts` y `types/ventas.ts` | Espejo TS de los schemas Pydantic. |
| Frontend — servicio | `frontend/src/services/commissionConfig.ts` | Llamadas axios a los endpoints nuevos. |
| Frontend — hooks | `frontend/src/hooks/commissionConfig.ts` | React Query: queries + mutations para cada recurso de configuración. |
| Frontend — UI | `frontend/src/components/goals/CommissionConfigPanel.tsx`, `CommissionSimulationPanel.tsx` | Paneles de gerencia (pestañas "Config" y "Simulación" en `DashboardMetas.tsx`). |
| Frontend — comparador vendedor | `frontend/src/components/goals/VendorGoalDashboard.tsx` (tarjeta "Con el sistema nuevo habrías ganado") | Aparece solo si `comision_variable != null` en la respuesta de `mi-comision`. |

### 2.3 La fórmula del motor variable

```
Comisión mes = [ Σ por cada línea de venta:
                   base_comisionable × tasa_categoría × factor_estratégico × factor_crédito ]
               × factor_tipo_vendedor
               × multiplicador_cumplimiento(meta)      ← reutiliza calcular_nivel() del motor plano
               − devoluciones_estimadas
               + bonos (venta cruzada aceptada, cliente nuevo/reactivado, cobranza sana)
               , con piso $0 (nunca negativa)
```

Reglas de clasificación de línea (`_calcular_linea` en `commission_engine.py`):

1. Descuento de la línea > `COMISION_TOPE_DESCUENTO_PCT` y no aprobado → comisión $0, marcada `pendiente_aprobacion`.
2. `|subtotal_neto| < COMISION_UMBRAL_SUBTOTAL_X` (cortesías/redondeos) → grupo **X**, tasa 0%.
3. `es_servicio = true` → grupo **S**, tasa sobre el **valor** de venta (no hay costo de inventario que dé margen).
4. `margen_bruto IS NULL` (línea sin costo en SAP) → tasa mínima (`COMISION_TASA_MINIMA_SIN_COSTO_PCT`) sobre el valor.
5. Resto → se busca la regla más específica en la matriz configurada: `(clase, subclase)` exacto > `(clase, NULL)` > comodín `('*', NULL)`.

El multiplicador de cumplimiento reutiliza los mismos 4 tramos del motor plano (`NivelCumplimiento`), pero con multiplicadores propios y configurables: `COMISION_MULT_EXCELENTE` (default 1.2), 1.0 para META, `COMISION_MULT_CERCA` (default 0.7), `COMISION_PISO_LEJOS` (default 0.0).

### 2.4 Configuración (`backend/app/core/config.py`)

| Variable | Default | Qué controla |
|---|---|---|
| `COMISION_MODO` | `plana` | `plana` \| `sombra` \| `variable` — **el mecanismo de rollback**. |
| `COMISION_TOPE_DESCUENTO_PCT` | `30.0` | Umbral de descuento que bloquea comisión sin aprobación. |
| `COMISION_TASA_MINIMA_SIN_COSTO_PCT` | `5.0` | Tasa aplicada a líneas sin costo registrado (sobre valor). |
| `COMISION_UMBRAL_SUBTOTAL_X` | `1.0` | Bajo este monto, la línea se excluye (grupo X). |
| `COMISION_BONO_CLIENTE_NUEVO` | `50.0` | Monto fijo por cliente nuevo/reactivado. |
| `COMISION_BONO_CROSS_SELL_PCT` | `5.0` | % adicional sobre ventas originadas en sugerencias aceptadas del asistente. |
| `COMISION_BONO_COBRANZA_PCT` / `COMISION_BONO_COBRANZA_DIAS` | `5.0` / `30` | % de bono si el promedio de días de cobro del vendedor es menor al umbral. |
| `COMISION_MESES_CLIENTE_REACTIVADO` | `6` | Ventana de inactividad para contar a un cliente como "nuevo/reactivado". |
| `COMISION_MULT_EXCELENTE` / `COMISION_MULT_CERCA` / `COMISION_PISO_LEJOS` | `1.2` / `0.7` / `0.0` | Multiplicadores del esquema variable por tramo de cumplimiento. |
| `COMISION_FACTOR_EXTERNO_DEFAULT` / `COMISION_FACTOR_INTERNO_DEFAULT` | `1.0` / `0.70` | Factor de comisión por tipo de vendedor cuando no hay fila explícita en `comision_config_vendedor`. |
| `COMISION_META_FACTOR_EXTERNO` / `COMISION_META_FACTOR_INTERNO` | `1.10` / `0.95` | Ajuste de la meta generada según el tipo de vendedor. |
| `COMISION_VENDEDOR_NUEVO_MESES` / `COMISION_VENDEDOR_NUEVO_FACTOR` | `3` / `0.60` | Ventana y factor de la regla de "vendedor nuevo" (meta = % del promedio del equipo). |

### 2.5 Endpoints

Todos bajo `/api/v1`, con `PermissionChecker` de gerencia/administrador salvo donde se indica.

| Endpoint | Método | Rol | Descripción |
|---|---|---|---|
| `/gerencia/goals/tracking` | GET | gerencia | Metas configuradas del período (sin venta real). |
| `/gerencia/goals/periods` | GET | gerencia | Períodos con datos disponibles. |
| `/gerencia/goals/generate` | POST | gerencia | Genera/actualiza propuestas de meta (motor IQR + ajuste por tipo de vendedor). |
| `/gerencia/goals/ai-summary` | GET | gerencia | Vendedores en riesgo/alta probabilidad + recomendaciones por categoría. |
| `/gerencia/goals/commissions` | GET | gerencia | Cumplimiento real + comisión devengada por vendedor; incluye `comision_variable`/`nivel_variable` cuando `COMISION_MODO != plana`. |
| `/gerencia/goals/{goal_id}/review` | PUT | gerencia | Aprobar/rechazar una meta propuesta. |
| `/gerencia/goals/commission-config/matriz` | GET, POST | gerencia | Leer / crear-actualizar reglas de categoría (con vigencia). |
| `/gerencia/goals/commission-config/credito` | GET, PUT | gerencia | Leer / reemplazar la matriz completa de factores de crédito. |
| `/gerencia/goals/commission-config/vendedores` | GET | gerencia | Listar configuración de tipo de vendedor. |
| `/gerencia/goals/commission-config/vendedores/{vendedor_origen}` | PUT | gerencia | Crear/actualizar tipo y factor de un vendedor. |
| `/gerencia/goals/commission-simulation` | POST | gerencia | Simulación retroactiva N meses, plano vs. variable. |
| `/gerencia/goals/commission-analysis/categorias` | GET | gerencia | Perfil de margen agregado por categoría (Fase 1 del plan). |
| `/gerencia/goals/lineas-sin-costo` | GET | gerencia | Reporte de líneas sin costo registrado (salvaguarda 2). |
| `/analytics/ventas/goals/mi-comision` | GET | ventas | Comisión del vendedor autenticado en el mes en curso; incluye `comision_variable`/`desglose_variable` cuando corresponde. |
| `/analytics/ventas/goals/facturas-post-meta` | GET | ventas | Facturas emitidas tras alcanzar el 100% de la meta. |
| `/analytics/ventas/goals/meta-sugerida`, `/goals/forecast-cierre`, `/goals/recomendaciones` | GET | ventas | Meta sugerida, pronóstico de cierre y recomendaciones comerciales (sin cambios). |

### 2.6 Tablas nuevas (`public.*`)

```sql
comision_matriz_categorias   (id, clase, subclase, grupo, tasa_pct, base, factor_estrategico, vigente_desde, vigente_hasta, creado_por)
comision_factores_credito    (id, dias_desde, dias_hasta, factor, pct_al_facturar, vigente_desde, vigente_hasta)
comision_config_vendedor     (id, id_vendedor_origen UNIQUE, tipo, factor_tipo, fecha_ingreso, activo)
comision_liquidaciones       (id, anio, mes, id_vendedor_origen, esquema, modo, comision_total, detalle_json, fecha_calculo,
                               UNIQUE(anio, mes, id_vendedor_origen, esquema, modo))
```

Se crean automáticamente al arrancar el backend (`Base.metadata.create_all`, ver `backend/app/database/base.py`) y también existen como DDL explícito en `edw/07_public_app_tables.sql` para volúmenes Docker nuevos. Ninguna toca el esquema `edw` (regla del proyecto: el DW es solo lectura/append desde el ETL).

`comision_liquidaciones` es el registro de auditoría/transparencia: cada vez que se consulta un período **ya cerrado** (no el mes en curso) en modo sombra o variable, se congela un snapshot con el desglose completo línea por línea en `detalle_json`. El mes en curso nunca se persiste porque cambia con cada consulta.

### 2.7 Cómo extender el módulo

- **Agregar un bono nuevo:** añadir el cálculo en `CommissionService._calcular_bonos` (o crear un método propio si necesita datos nuevos del repositorio), sumar al total que ya se pasa a `calcular_comision_variable(bonos_total=...)`. No tocar el motor puro para lógica que depende de BD.
- **Agregar una salvaguarda nueva:** si depende solo de los datos de la línea (ej. otro tipo de descuento), añadir la regla dentro de `_calcular_linea` en `commission_engine.py` y su test correspondiente en `test_commission_engine.py`. Si depende de datos externos (ej. historial de churn del vendedor), resolverla en el servicio antes de llamar al motor.
- **Cambiar los umbrales de tramos o tasas por defecto:** son env vars (`COMISION_*` en `config.py`) — no requiere despliegue de código, solo reiniciar el backend con la nueva variable.
- **Activar el piloto en producción:** cambiar `COMISION_MODO=sombra` en `.env` (o el mecanismo de configuración del entorno) y reiniciar el contenedor backend (`docker compose up -d backend` para que tome el `.env` nuevo — un `docker restart` simple **no** relee `env_file`).

### 2.8 Testing

```bash
cd backend
python -m pytest tests/unit/test_commission_engine.py -v   # motor puro, 32 tests
python -m pytest tests/unit -v                              # suite completa
```

Los tests del motor variable cubren: clasificación por grupo (A/B/C/S/X), factor de crédito, línea sin costo, descuento excesivo (con y sin aprobación), umbral de exclusión, factor por tipo de vendedor, piso configurable del tramo LEJOS, devoluciones, bonos, y el golden test del ejemplo numérico de `docs/features/propuesta_sistema_comisiones_variables.md` §5.

Para probar contra datos reales del EDW (requiere Docker corriendo):

```bash
docker compose up -d backend
# Login y prueba de endpoints, ver docs/auditoria/30_comisiones_variables.md para ejemplos de consultas SQL de validación
```

### 2.9 Limitaciones conocidas (no son bugs, son brechas de datos documentadas)

| Brecha | Detalle | Dónde está documentada |
|---|---|---|
| Categorías por código, no por nombre | `dim_producto.nombre_clase` está 100% vacío en el catálogo cargado | Auditoría 30, H2 |
| Crédito con cobertura parcial | Solo hay tráfico real en plazos de 0 y 30 días; los demás tramos son configuración sin historial | Auditoría 30, H4 |
| Ventas compartidas externo/interno | No implementado — requiere un CRM de cotizaciones que el EDW no tiene | Plan de integración, brecha B2 |
| Bono de visitas (solo externos) | No implementado — requiere geolocalización/plan de visitas | Plan de integración, brecha B3 |
| Split de pago al facturar/cobrar | Solo el factor de crédito simple está implementado; el split porcentual (ej. 70% al facturar / 30% al cobrar) queda para una fase futura | Plan de integración §3.1, Fase 5 |
