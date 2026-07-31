# Plan de acción — Correcciones integrales del sistema (Dashboard, Gerencia, Ventas, Admin, Bodega)

- **Fecha:** 2026-07-29
- **Origen:** requerimiento consolidado del usuario (revisión funcional completa del sistema).
- **Alcance:** backend FastAPI, frontend React, EDW PostgreSQL, queries de reportes de Bodega.
- **Skills consultadas para construir este plan:** `etl-edw-auditor` (§6, §7 — migración de queries y
  reconciliación EDW), `backend-ml-serving` (§3 — contratos de `sales_rf` / `demand_rf`).
- **Metodología obligatoria (CLAUDE.md §Flujo de trabajo):** auditoría en `docs/auditoria/` **antes**
  de tocar código en cada fase. Numeración libre siguiente: **42**.

---

## 0. Resumen ejecutivo

El requerimiento agrupa ~40 tareas heterogéneas. Este plan las reordena por **riesgo real**, no por
el orden en que fueron dictadas. La exploración previa del código encontró que **dos de los puntos
reportados como "no funciona" tienen una causa raíz identificada y verificable**, y que hay **un
fallo de seguridad de datos no listado en el requerimiento** que es más grave que todo lo demás.

| Prioridad | Bloque | Por qué en ese orden |
|---|---|---|
| **P0** | Segregación de datos por bodega (RLS `codalm`) | Fuga de datos activa: hoy cualquier usuario `bodega` ve **todas** las bodegas. |
| **P3** | Centralizar la desanonimización (Fase 1.c) | El mecanismo ya existe y funciona; está copiado en ~20 consultas. Higiene, sin urgencia: los reportes de Bodega no expondrán identidad de cliente. |
| **P1** | Lógica de datos incorrecta (exceso de stock, días de stock, gráficos de predicción, KPIs de Gerencia por vendedor) | Decisiones de negocio tomadas sobre números falsos. |
| **P2** | Funcionalidad faltante (CRUD de usuarios, aprobar/rechazar metas, PDF real, nombres de archivo) | Bloquea operación, pero no corrompe datos. |
| **P3** | Rediseño de dashboards y UX (filtros, datepicker, paneles) | Alto valor percibido, cero riesgo de datos. |

**Regla transversal (impuesta por el proyecto, ver refactor de Venta Cruzada en CLAUDE.md):**
ningún campo de ningún response nuevo puede ser simulado, inventado o rellenado con un placeholder.
Si un dato no sale de una consulta real al EDW o de un modelo ya entrenado, **se omite del contrato**,
no se rellena.

---

## 1. Decisiones tomadas y bloqueadores

### B-1 — RESUELTO (2026-07-29): queries de referencia entregadas

El usuario entregó el SQL literal de las 4 queries tal como corren hoy contra SAP
(`QUERY_BODEGAS`, `QUERY_PRODUCTOS_SIN_VENTA`, `QUERY_ARTICULOS_ESTANCADOS`,
`QUERY_KARDEX_MOVIMIENTOS`), con la instrucción explícita: **"eso se tiene en la BD de Producción,
lo que quiero es obtenerlo haciendo uso del EDW"** y **"utilizar lo que ya está hecho"**.
Requerimiento adicional confirmado: **un reporte de artículos sin movimientos en ventas por almacén**.

El análisis del SQL entregado y su traducción al EDW está en la **Fase 6** (§H-7 a §H-11 y el
mapeo tabla a tabla). Las queries se conservan verbatim como anexo en la auditoría 42.

### B-2 — RESUELTO (2026-07-29): asignación N:N de bodegas por usuario

Decisión del usuario, **corrigiendo la respuesta anterior**: *"un usuario puede ver varias bodegas y
otro usuario puede ver solo su bodega, esto depende de cómo lo creó el admin"*.

El modelo actual **no soporta ese caso**: `user.codalm` es un único `VARCHAR(10)` donde `NULL`
significa "todas" (`backend/app/models/user.py:32`, `user_service.py:61-68`). Es decir, hoy solo
existen "una" y "todas" — **no existe "estas tres"**. Se implementa la relación N:N.

**Coste real, medido sobre el código (mucho menor de lo estimado en la versión previa del plan):**

| Punto | Evidencia | Impacto |
|---|---|---|
| Filtro de almacén en consultas | `warehouse_repository.py:72-74` es el **único** lugar que lo aplica; las ~10 funciones restantes delegan en `_filtros_snapshot` | Un solo punto a cambiar de `= :almacen` a `IN (...)` |
| JWT | `auth.py:51-54` emite solo `rol`, `sucursal`, `id_vendedor_origen` — **no lleva `codalm`** | **No hay que tocar el token.** Las bodegas se leen del objeto `User` ya cargado por `CurrentUserDep` (mismo patrón que `notification_service.py:85`) |
| JOIN condicional | `warehouse_repository.py:375` → `join_al = "..." if almacen else ""` | Funciona igual con una lista (truthiness) |

**Trabajo que sí implica:**

1. **Migración Alembic `0006_usuario_almacenes`:**
   - Tabla `public.usuario_almacenes (usuario_id FK → public.usuarios ON DELETE CASCADE, codalm VARCHAR(10), PK compuesta)`.
   - Columna **real** `usuarios.todos_los_almacenes BOOLEAN NOT NULL DEFAULT FALSE`. Es necesaria
     para distinguir *"acceso a todas"* de *"ninguna asignada aún"* — con N:N el conjunto vacío es
     ambiguo, y hoy esa distinción la lleva `codalm IS NULL`. Sin esta columna, un error de alta
     dejaría a un usuario viendo todo el sistema.
   - **Backfill:** por cada usuario con `codalm` no nulo → una fila en la tabla nueva; con
     `codalm IS NULL` y rol `bodega` → `todos_los_almacenes = TRUE`. Luego se elimina la columna
     `usuarios.codalm` en la misma migración, una vez migradas todas las lecturas.
2. **Contratos:** `UserCreate`/`UserUpdate` cambian `codalm: str` por `codalms: list[str]`;
   `UserOut` expone la lista. `UserService._resolve_role_link` valida **cada** código contra
   `edw.dim_almacen` (reutiliza `CatalogRepository.get_almacen`, ya existe).
3. **Dependencia de seguridad:** `resolve_almacenes_filter` devuelve `list[str] | None`
   (`None` = sin restricción) en vez de un `str`.
4. **Frontend:** el formulario de alta/edición pasa a multi-selección de bodegas; `BodegaFilterBar`
   ofrece solo las bodegas asignadas al usuario (selector real si tiene varias, chip fijo si tiene una).

**Detalle que hay que resolver sí o sí (descubierto al verificar):** el filtro actual compara
`al.nombre_almacen = :almacen` (**nombre**), mientras la asignación del usuario es por **`codalm`**
(código). Son dominios distintos. La restricción de seguridad debe aplicarse por `al.codalm IN (...)`
— comparar por nombre es frágil ante renombres en el ERP y no es la llave de negocio.

### B-3 (MEDIO) — "Vendedor asociado a bodega, no a sucursal" (§2)

El requerimiento pide "eliminar todo rastro de sucursal si un vendedor no está asociado a una".
Hoy la RLS del rol `ventas` es **por sucursal** (`dependencies.py:349-353`), y las metas tienen grano
`(anio, mes, id_vendedor_origen)` **sin sucursal** por una decisión ya validada
(regla 10 del CLAUDE.md, `docs/auditoria/19_...md`).

- **Riesgo:** eliminar `sucursal` del rol `ventas` sin analizar rompe `/analytics/ventas/goals`,
  KPIs de Gerencia y Cartera 360.
- **Acción:** **no** se elimina a ciegas. La Fase 0 audita en qué endpoints `sucursal` realmente
  discrimina datos de vendedor y en cuáles es ruido heredado, y solo entonces se retira. Ver A-0.3.

---

## 2. Hallazgos ya confirmados durante la exploración previa

Estos no son hipótesis: se verificaron leyendo el código. Entran al plan como trabajo cerrado.

### H-1 (CRÍTICO, seguridad) — La segregación por bodega **no existe** en el módulo Bodega

- **Evidencia:** `grep -rn "codalm" backend/app/` → el único consumo en tiempo de consulta es
  `backend/app/services/notification_service.py:85`. **Ningún** endpoint de `/analytics/bodega/*`
  lo usa. En `backend/app/api/routes/warehouse.py` el parámetro `almacen` es un query param libre
  (líneas 88, 110, 133, 150, 170, 191, 210, 232, 265, 352, 377) que el cliente controla por completo.
- **Impacto:** un usuario con rol `bodega` asignado al almacén `X` puede consultar KPIs, stock,
  rotación, transferencias y **descargar el Excel completo** de cualquier otra bodega simplemente
  cambiando `?almacen=Y`. Es exactamente la clase de fuga que ya se corrigió para el rol `ventas`
  en `docs/auditoria/34_actualizacion_modulo_ventas.md` (RN-V4) — el módulo Bodega quedó fuera.
- **Corrección:** Fase 1.

### H-2 (ALTO, datos) — "Productos en exceso de stock" nunca puede reportar un artículo sin movimiento

- **Evidencia:** `backend/app/services/warehouse_service.py:129-145`.
  ```python
  def _dias_inventario(stock, salida_diaria):
      if salida_diaria <= 0:
          return None          # ← artículo sin salidas
      return round(stock / salida_diaria, 1)

  def _estado_stock(cls, stock, reorden, dias_inv):
      if dias_inv is not None and dias_inv > settings.BODEGA_DIAS_EXCESO:
          return ESTADO_EXCESO  # ← inalcanzable con dias_inv=None
      if reorden <= 0:
          return ESTADO_SEGURO  # ← aquí cae el artículo muerto
  ```
- **Cadena completa del fallo:** artículo con stock y **0 salidas** → `salida_diaria = 0` →
  `dias_inventario = None` → se salta la rama de exceso → `_punto_reorden_efectivo(0, 0) = 0` →
  `reorden <= 0` → **`"Seguro"`**. El reporte de exceso filtra `p["estado"] == ESTADO_EXCESO`
  (`warehouse_service.py:1375`), así que el peor caso posible de sobre-stock —el inmovilizado total—
  **es el único que nunca aparece**.
- **Esto explica el caso reportado "Consignación Verónica Sánchez: tiene stock pero 0.0 uds/día".**
  No es un dato mal mostrado: es la clasificación la que está invertida.
- **Caso "El Rey: 0 días de stock con 0.1 uds/día":** aquí la clasificación sí es correcta
  (stock 0 → `dias_inv = 0` → `reorden = 0.1 × (lead + seguridad) > 0` → `stock < reorden` →
  `"Crítico"`). El problema es de **presentación**: "0 días" sin contexto de que la salida diaria es
  marginal induce a error. Se corrige en la Fase 6 con banda de confianza por volumen de movimiento.
- **Corrección:** Fase 6.

### H-3 (MEDIO) — "Imprimir/PDF" es la impresión del navegador, no un PDF del reporte

- **Evidencia:** `frontend/src/pages/BodegaReportes.tsx:148` y
  `frontend/src/pages/DashboardGerencia.tsx:107` → `onClick={() => window.print()}`.
- **Impacto:** el PDF resultante hereda el layout de pantalla (paginación rota, tablas cortadas,
  gráficos recortados, nav/sidebar impresos).
- **Corrección:** Fase 6.

### H-4 (BAJO) — El Excel descargado no lleva fecha/hora

- **Evidencia:** `backend/app/api/routes/warehouse.py:396` →
  `filename="reporte_{tipo}.xlsx"`.
- **Corrección:** Fase 6 (trivial, mismo PR).

### H-5 (MEDIO) — Gestión de usuarios: sin paginación real, sin borrado, ruta top-level

- **Evidencia:** `backend/app/api/routes/users.py:56` → `list_users(skip: int = 0, limit: int = 100)`
  devuelve `list[UserOut]`, **no** el `Page[T]` genérico que el proyecto ya tiene
  (`backend/app/schemas/pagination.py`, usado en Bodega y Notificaciones).
  `users.py:96` expone `deactivate_user` (baja lógica), **no existe** borrado permanente.
  `frontend/src/router/AppRouter.tsx:74` monta `/users` como ruta hermana de `/admin`, no anidada.
- **Corrección:** Fase 5.

### H-6 (INFO) — El flujo aprobar/rechazar metas ya existe en el backend

- **Evidencia:** `backend/app/models/goal.py:20,39` → `estado IN ('PROPUESTA','APROBADA','RECHAZADA')`
  con `approved_by` y relación `aprobador`.
- **Consecuencia para el plan:** §3.3 del requerimiento es mayormente **cableado de frontend**, no
  desarrollo de backend. Reduce el coste estimado de esa tarea. Pendiente de verificar qué expone
  hoy `frontend/src/components/goals/`.

### Hallazgos sobre las queries de Producción entregadas (§6/§7)

Las 4 queries se auditaron contra las reglas de negocio ya validadas del proyecto. **No son un
contrato correcto a replicar tal cual**: cuatro de ellas violan reglas que el EDW sí cumple. Migrar
literalmente propagaría los errores al EDW.

#### H-7 (ALTO) — El cálculo de Stock ignora los ajustes de inventario

```sql
SUM(CASE WHEN k.tipdoc = 'EN' THEN k.cantot
         WHEN k.tipdoc = 'SA' THEN -k.cantot
         ELSE 0 END) AS Stock
```

- **Problema:** la **regla 3** del proyecto (validada contra SAP,
  `docs/auditoria/02_reglas_negocio_validadas.md`) define entrada = `('EN','AC')` y
  salida = `('SA','AD')`. La query solo cuenta `EN`/`SA`; **`AC` (ajuste de entrada) y `AD` (ajuste
  de salida) caen en el `ELSE 0`**, es decir, se descartan silenciosamente.
- **Impacto:** todo artículo que haya tenido un ajuste de inventario tiene el Stock mal calculado en
  el reporte actual de Producción. La magnitud se mide en A-0.8.
- **El EDW ya está bien:** `etl/transformers/fact_transformer.py:143-146` deriva
  `es_entrada = tipdoc ∈ ('EN','AC')` y `es_salida = tipdoc ∈ ('SA','AD')`, y los materializa como
  columnas booleanas en `edw.fact_movimientos_inventario`. **La versión EDW será más correcta que la
  de Producción**, y esa diferencia debe anticiparse al usuario antes de que la reporte como bug.

#### H-8 (ALTO) — `_ULTIMA_VENTA_JOIN` no filtra documentos anulados ni empresa

- **Problema:** el subquery de última venta filtra `k3.tiporg = 'FAC'` pero **no** `estado = 'P'`
  (regla 1: `'A'` = anulada) ni `codemp = '01'` (regla 2).
- **Impacto:** `FechaUltimaVenta` y `NumeroFactura` pueden provenir de una **factura anulada**, y el
  `ROW_NUMBER() ... ORDER BY fecdoc DESC` la elegiría preferentemente por ser la más reciente.
  Un artículo reportado como "vendido recientemente" puede no haberse vendido nunca.
- **Corrección en EDW:** filtrar por el estado válido y por empresa. Pendiente de validar en A-0.8
  si `fact_movimientos_inventario` conserva ya solo documentos `'P'` (el extractor debería aplicar
  el token `{ESTADO}`) — si es así, el filtro es implícito y solo hay que documentarlo.

#### H-9 (ALTO) — `QUERY_PRODUCTOS_SIN_VENTA` y `QUERY_ARTICULOS_ESTANCADOS` son la misma query

- **Evidencia:** diferencia textual única = `HAVING SUM(...) > 0` en la de estancados.
- **Consecuencia:** "sin venta" incluye artículos con stock **cero o negativo** (los que ya no están
  en la bodega), mientras "estancados" son los que sí tienen existencia. Semánticamente:
  *estancados ⊂ sin venta*. **No son dos reportes independientes, son un reporte con un filtro.**
- **Acción:** implementar **un solo** endpoint parametrizado (`?solo_con_stock=true|false`) en vez de
  dos, y nombrarlos en la UI por lo que realmente responden. Cumple "utilizar lo que ya está hecho".

#### H-10 (MEDIO) — `nombre_clase` está vacío en el EDW

- `COALESCE(c.nomcla, 'SIN CLASE')` traduce a `edw.dim_producto.nombre_clase`, pero esa columna está
  **100% vacía** en el catálogo (hallazgo H2 de `docs/auditoria/30_comisiones_variables.md`; por eso
  el código de comisiones clasifica por `clase`/`subclase`, nunca por `nombre_clase`).
- **Impacto si se migra literal:** la columna "NombreGrupo" mostraría `'SIN CLASE'` en el 100% de las
  filas — un reporte visiblemente roto.
- **Opciones:** (a) mostrar solo el código `clase` (dato real disponible); (b) poblar `nombre_clase`
  en el ETL desde `dbo.clasesarticulos` (corrige la raíz, requiere pasada de ETL). **Se recomienda
  (b)** y se implementa (a) como estado intermedio, nunca inventando el nombre.

#### H-11 (MEDIO) — `QUERY_KARDEX_MOVIMIENTOS`: `GROUP BY` sin agregación y granos mezclados

- El `GROUP BY` no acompaña a ninguna función de agregación → es un `DISTINCT` disfrazado, y el
  rendimiento en el EDW será peor si se replica tal cual.
- `a.exiact` (`ExistenciaGlobal`) es la existencia **global** del artículo, mezclada en un reporte
  cuyo grano es `(bodega, artículo)`. **No tiene equivalente directo en el EDW**:
  `edw.dim_producto` no almacena `exiact`. Se deriva sumando el kardex sobre todos los almacenes, o
  desde `fact_inventario_snapshot` — que solo está poblada hacia adelante (<1% de histórico
  pre-2026, auditoría 05). **Debe declararse la fuente elegida en la UI**, no servirse en silencio.

---

## 3. Fases del plan

Cada fase abre con su auditoría obligatoria y cierra con validación ejecutable.

---

### Fase 0 — Auditoría transversal (`docs/auditoria/42_correcciones_integrales_sistema.md`)

**Sin código.** Produce la evidencia que las fases 1-7 consumen.

| ID | Actividad | Método | Entregable |
|---|---|---|---|
| A-0.1 | Inventariar todos los endpoints que devuelven datos de bodega/almacén | Estático: grep de `almacen` en routes/services/repositories | Matriz endpoint → ¿aplica `codalm`? (se espera "no" en todos, confirmando H-1) |
| A-0.2 | Inventariar endpoints que devuelven datos de vendedor | Estático + `resolve_sucursal_filter` | Matriz endpoint → mecanismo de RLS actual |
| A-0.3 | Determinar si `sucursal` discrimina realmente para el rol `ventas` | `SELECT` sobre EDW: ¿cuántos vendedores transaccionan en >1 sucursal? | Decide B-3: retirar `sucursal` o conservarla |
| A-0.4 | Contrastar cada modelo TypeScript de `frontend/src/types/` con su schema Pydantic | Estático, campo a campo | Lista de desalineaciones (§7.1 del requerimiento) |
| A-0.5 | Medir el impacto de H-2 en datos reales | `SELECT` EDW: nº de artículos con stock > 0 y 0 salidas en 30/90/180 días, por almacén | Magnitud real del reporte de exceso vacío |
| A-0.6 | Verificar consistencia `sales_rf` vs `demand_rf` en los dos gráficos del §3.2 | Leer contratos `ml/contracts/models/{sales,demand}.json` + llamar ambos endpoints en vivo | Explica la diferencia real entre ambos gráficos (insumo del tooltip pedido) |
| A-0.7 | Estado actual de aprobar/rechazar metas en frontend | Estático `frontend/src/components/goals/` | Confirma alcance de §3.3 |
| A-0.8 | Cuantificar H-7 y H-8 sobre las queries de Producción | `SELECT` sobre SAP: nº de filas de kardex con `tipdoc IN ('AC','AD')` y % de artículos afectados; nº de facturas con `estado='A'` que hoy ganan el `ROW_NUMBER()` de última venta | Magnitud de la divergencia esperada Producción ↔ EDW, a comunicar antes de entregar |
| A-0.9 | Verificar que `fact_movimientos_inventario` solo contiene documentos `estado='P'` | Revisar `etl/extractors/kardex_extractor.sql` (token `{ESTADO}`) + `SELECT` de conteo en EDW | Determina si el filtro de H-8 es implícito o hay que añadirlo |
| A-0.10 | Verificar poblado real de `dim_producto.nombre_clase` (H-10) | `SELECT COUNT(*) FILTER (WHERE nombre_clase IS NOT NULL AND nombre_clase <> '')` | Decide entre opción (a) y (b) de H-10 |

**Validaciones mínimas exigidas por `etl-edw-auditor`** (se ejecutan en A-0.5 y en Fase 6, y se
reportan aunque salgan limpias): pérdida de registros origen↔destino, duplicados por llave de
negocio, cambios de volumen vía `edw.etl_control`, cambios de granularidad, % de FKs resueltas al
centinela `-1`, fechas fuera de rango, business keys huérfanas, integridad SCD2.

**Declaración obligatoria en el reporte:** "no se ejecutó ninguna escritura contra Producción".

---

### Fase 1 (P0) — Segregación de datos por bodega y por usuario

Cierra H-1 y el §1.2 del requerimiento.

**Fase 1.a — Modelo N:N de asignación de bodegas.** Migración `0006_usuario_almacenes`, contratos y
formulario de administración, según el detalle de B-2. Debe ir primero: la RLS de 1.b se apoya en él.

**Fase 1.b — Aplicar la restricción.**

1. **Nueva dependencia `resolve_almacenes_filter`** en `backend/app/api/dependencies.py`, análoga a
   `resolve_sucursal_filter` (líneas 334-353) pero devolviendo `list[str] | None`:
   - rol `bodega` con `todos_los_almacenes = FALSE` → devuelve **sus** `codalm` asignados.
   - rol `bodega` con `todos_los_almacenes = TRUE` → `None` (sin restricción).
   - `gerencia` / `administrador` → `None`.
   - rol `ventas` → no aplica (su RLS es por cartera/vendedor).
2. **Separar restricción de filtro — es el punto delicado del diseño.** Son dos conceptos distintos
   que no deben colapsarse en un parámetro:
   - `almacenes_permitidos` (seguridad, del token/usuario, **no negociable**).
   - `almacen` (elección del usuario en la barra de filtros, opcional).

   `_filtros_snapshot` recibe ambos y aplica la **intersección**: si el usuario elige una bodega que
   no le pertenece, el resultado es vacío, nunca los datos de esa bodega. Implementado como
   `al.codalm IN (:almacenes_permitidos)` **por código, no por nombre** (ver B-2), sumado al filtro
   existente por elección.
3. **Un solo punto de cambio en el repositorio:** `warehouse_repository.py:72-74`. Las ~10 funciones
   restantes ya delegan ahí, así que quedan cubiertas sin tocarlas. El `join_al` condicional de la
   línea 375 debe activarse también cuando hay `almacenes_permitidos`, aunque no haya `almacen`
   elegido — **si se omite, el `WHERE` referenciaría un alias inexistente y la query fallaría**.
4. **Aplicar la dependencia a los 11 endpoints** de `warehouse.py` identificados en A-0.1, incluidos
   `/reportes/{tipo}` y `/reportes/{tipo}/excel` (líneas 352, 377) y el PDF nuevo de la Fase 6.5 —
   la exportación es el vector de fuga de mayor volumen.
5. **Comportamiento ante un almacén ajeno:** se ignora y se aplica la restricción, sin 403 (mismo
   criterio que `resolve_sucursal_filter`; el frontend puede arrastrar el parámetro sin intención
   maliciosa y un 403 rompería la UI). **Se loguea en `WARNING`** para detectar abuso real.
6. **Frontend:** `BodegaFilterBar.tsx` ofrece únicamente las bodegas asignadas — selector real si el
   usuario tiene varias, chip fijo no editable si tiene una, selector completo si tiene todas.
7. **Auditoría cruzada (§1.2 "en todos los módulos"):** aplicar la misma revisión a Notificaciones
   (`notification_service.py:85` — hoy lee `user.codalm` singular, **hay que migrarlo a la lista**),
   Gerencia y Dashboard principal.

**Fase 1.c — Desanonimización en backend: estado actual y alcance acotado.**

> **Decisión del usuario (2026-07-29): los reportes de Bodega NO llevan columna de nombre de
> cliente.** Se elimina `Cliente` del contrato de los tres reportes migrados. Esto resuelve la
> pregunta de política de acceso a PII **por eliminación del caso de uso**: no hay PII fluyendo
> hacia el módulo Bodega, así que no hace falta una compuerta de rol para él. Esta fase queda
> reducida a higiene técnica (**P3**), sin bloquear nada.

**El mecanismo ya existe y es la arquitectura oficial del proyecto** — no se construye uno nuevo:

- `edw.dim_cliente` almacena **solo** `hash_anonimo` (hash + `PII_SALT`, regla 8). Eso **no cambia**.
- La identidad real vive aislada en `public.cliente_lookup` (`hash_anonimo` PK,
  `id_cliente_transaccional`, `nombre_cliente`), fuera del esquema `edw` a propósito
  (`edw/07_public_app_tables.sql:93-101`), y la puebla el ETL (`etl/orchestrator.py:653-657`).
- El backend la resuelve **al vuelo, en la consulta**, con
  `JOIN public.cliente_lookup l ON c.hash_anonimo = l.hash_anonimo`. Ya está en uso en **más de 20
  puntos**: `cartera360_repository.py` (7), `prediction_repository.py` (5),
  `catalog_repository.py` (5), y la vista `ml.v_ventas_cruzadas_desanonima`.

Es decir: **la BD queda anónima y el backend devuelve el dato original**, que es exactamente lo
pedido. El trabajo real de esta fase no es inventar el proceso sino cerrar dos huecos suyos:

1. **Centralizar.** Hoy el `JOIN` está copiado en ~20 consultas. Se extrae un helper único
   (`app/repositories/base.py` o un `PiiResolver` inyectable) con el `JOIN` y la resolución
   `hash → (id_cliente_transaccional, nombre_cliente)`, y todas las consultas nuevas lo usan.
   Motivo: hoy nada impide que una consulta nueva olvide filtrar `es_vigente` (SCD2, regla 7) o
   incluya el centinela `-1` (regla 12) — ya hay comentarios en el código advirtiéndolo caso por caso
   en vez de garantizarlo en un solo lugar.
2. **Dejar constancia del hueco de política.** La desanonimización **no tiene compuerta de rol
   propia**: cualquier endpoint que haga el `JOIN` devuelve el nombre real. Las protecciones
   existentes son de *alcance* (`cliente_pertenece_a_vendedor`, RLS de cartera de la auditoría 34),
   no de *visibilidad de PII*. Con la decisión de arriba **no hay que resolverlo ahora** (Bodega no
   recibe PII, y Ventas/Cartera 360 la necesitan legítimamente para operar). Se registra como
   hallazgo abierto en la auditoría 42 para que una futura consulta que sí exponga identidad no lo
   descubra tarde.

**Restricciones innegociables de esta fase:**
- **No** se escribe PII en `edw.*`, ni se desnormaliza `nombre_cliente` en ninguna tabla de hechos
  o dimensión "para evitar el JOIN". La aislación de `cliente_lookup` es deliberada (regla 8).
- **No** se expone `hash_anonimo` en ningún response de la API: no aporta al usuario y filtra un
  detalle interno del esquema.
- El ETL sigue anonimizando en la carga y abortando sin `PII_SALT` válido. Sin cambios.
- Los datasets de entrenamiento (`ml/`) siguen consumiendo el EDW anonimizado; la vista
  desanonimizada es solo para notebooks, como hoy.

**Regla de negocio nueva a documentar** en `docs/auditoria/02_reglas_negocio_validadas.md` §16:
`RN-B10 — un usuario con rol bodega solo puede leer datos de los almacenes que el administrador le
asignó (public.usuario_almacenes), o de todos si se marcó todos_los_almacenes. El parámetro almacen
del request se intersecta con ese conjunto, nunca lo amplía.`

**Validación:** test de integración nuevo `backend/tests/integration/test_bodega_rls.py` cubriendo
los tres casos que el modelo nuevo introduce: (a) usuario con **una** bodega pidiendo otra;
(b) usuario con **varias** — recibe la unión de las suyas y nada más, y al elegir una ajena recibe
vacío; (c) usuario con `todos_los_almacenes` — sin restricción. Repetir sobre Excel y PDF.
Más test de la migración `0006` (backfill correcto de los usuarios existentes) y suite completa.

---

### Fase 2 (P1) — Filtros, fechas y consistencia de modelos (transversal, §1.1, §1.3, §7.1)

1. **Datepicker:** reemplazar `<input type="date">` nativo (presente en `BodegaFilterBar.tsx`,
   `QuickLogForm.tsx`, `DashboardAdmin.tsx`, `DashboardGerencia.tsx`) por un componente único
   `components/ui/DateField.tsx` con icono de calendario renderizado explícitamente (no dependiente
   del pseudo-elemento `::-webkit-calendar-picker-indicator`, que es el origen del icono invisible
   en navegadores no-Chromium y en tema oscuro).
2. **Filtros inteligentes:** implementar dependencia declarativa entre filtros
   (`categoria` → `proveedor` → `producto`): al cambiar un filtro padre, los hijos incompatibles se
   limpian y sus opciones se recargan desde el catálogo real. **No** se inventan opciones; si el
   backend no devuelve combinaciones, el filtro hijo se deshabilita con leyenda explícita.
3. **Filtros híbridos texto + combobox:** un solo `ComboboxField` con búsqueda tipeable sobre el
   catálogo real y opción de texto libre solo donde el backend acepta búsqueda parcial. Donde el
   backend exige un código exacto, se **deshabilita** el texto libre en vez de permitir enviar basura.
4. **Alineación de modelos (§7.1):** corregir las desalineaciones que arroje A-0.4.

**Validación:** `tsc` + `oxlint` limpios; prueba manual de cada filtro contra `bi_frontend` real.

---

### Fase 3 (P1) — Módulo Gerencia

1. **KPIs filtrables por vendedor (§3.1):** `/gerencia/goals/commissions` y los KPIs de meta ya
   tienen grano `id_vendedor_origen` (regla 10). Añadir parámetro `vendedor` opcional a los
   endpoints de KPI y un selector en la consola: sin selección → vista agregada de **todos** los
   vendedores; con selección → progreso individual. Hoy la vista muestra un solo vendedor por
   defecto, que es el bug reportado.
2. **Gráficos "Histórico y Predicción" vs "Predicción de Compras — Próximo Mes" (§3.2):**
   Según los criterios de `backend-ml-serving`, ambos son modelos **distintos con contratos
   distintos** y su comparación directa carece de sentido:
   - "Histórico y Predicción" = `sales_rf` (`sales.pkl`), forecast **de ventas** en moneda, ventana
     continua de 730 días, vía `walk_forward_forecast`. **No respeta filtros de categoría ni rangos
     de fecha arbitrarios** — limitación estructural ya documentada como RN-G1
     (`docs/auditoria/33_actualizacion_modulo_gerencia.md`).
   - "Predicción de Compras — Próximo Mes" = `demand_rf` (`demand.pkl`), demanda **en unidades** a
     grano `(fecha, codart, almacén)`, con umbral mínimo de historia.
   - **Acción:** (a) verificar en A-0.6 que ninguno viola su `plausible_range` de contrato;
     (b) unificar la unidad mostrada en cada gráfico y **eliminar los porcentajes** que mezclan
     escalas; (c) añadir el tooltip explicativo con el texto derivado de los contratos reales, no
     redactado a mano; (d) **no** activar contratos en `status: draft` para silenciar desvíos —
     si un valor sale de rango, se investiga la escala antes de bajar la barrera.
3. **Metas y comisiones (§3.3):** cablear en el frontend el flujo ya existente en backend (H-6):
   tabla de estado con acciones **Aprobar / Rechazar / Modificar** por vendedor, escribiendo
   `estado` y `approved_by`. Exponer como editables el factor de presión comercial y el número de
   meses a simular, con **simulación previa** (endpoint `POST /commission-simulation` ya existe)
   antes de la aplicación definitiva.
4. **Gráficos de rendimiento (§3.4):** "Vendedores en riesgo", "Alta probabilidad de superar la
   meta" y "Recomendaciones por categoría" — auditar en A-0.2 si sus valores provienen del EDW o
   son estáticos. **Si algún indicador no tiene respaldo real, se retira del dashboard**, no se
   rellena con un valor plausible (regla transversal §0).

---

### Fase 4 (P1) — Módulo Ventas

1. Auditar cada gráfico del dashboard de Ventas: confirmar que filtra por el vendedor autenticado
   (RLS ya endurecida en la auditoría 34, RN-V4) y que la agregación es correcta.
2. **Rediseño del panel de Cartera:** el módulo ya tiene la infraestructura necesaria —
   `Cartera360Repository.get_perfil_cliente` y `get_productos_favoritos_cliente` (Fase 1 del refactor
   de Venta Cruzada) devuelven clientes principales, productos favoritos y CLV histórico reales.
   El panel se reconstruye **sobre esos repositorios existentes**, añadiendo únicamente
   "última fecha de compra" y "estado de cartera (activo / inactivo / potencial)" —este último
   derivado de `recency` real, con umbrales configurables en `config.py`, nunca hardcodeados.
3. **Rediseño del dashboard de Ventas** como herramienta principal del vendedor: progreso vs. meta,
   cartera, análisis de ventas propias.
4. **Estado vacío real** obligatorio para clientes sin historial (`tiene_historial=false`, campos
   `null`) — nunca ceros inventados (RN-CS5, ya establecida).

---

### Fase 5 (P2) — Módulo Administración

1. **Paginación real:** migrar `GET /users` a `Page[UserOut]` reutilizando
   `backend/app/schemas/pagination.py` + `PaginationParams` (mismo patrón que Bodega/Notificaciones)
   y `components/ui/Pagination.tsx` + `hooks/usePagination.ts` en el frontend. No crear un mecanismo
   de paginación nuevo.
2. **Cambio de estado Activo/Inactivo:** los endpoints ya existen (`deactivate_user`,
   `activate_user`); falta el control explícito en la UI (toggle con estado visible).
3. **Eliminación permanente:** endpoint nuevo `DELETE /users/{id}/permanente`.
   - Restricción: no puede eliminarse a sí mismo ni al último administrador activo.
   - `public.usuarios` es referenciada por `Goal.approved_by` y por `notificaciones.leida_por` →
     evaluar en la auditoría si el borrado duro es viable o si debe ser `ON DELETE SET NULL`.
     **Si rompe integridad referencial, se mantiene solo la baja lógica** y se comunica al usuario.
   - **Doble confirmación** en UI: modal con checkbox de consentimiento + escritura del email del
     usuario a eliminar, luego botón destructivo.
4. **Submenú:** anidar `/users` bajo `/admin` en `AppRouter.tsx` (`/admin/usuarios`) y en el Sidebar.
5. **Dashboard de Admin:** métricas reales — total usuarios activos/inactivos, vendedores, bodegas
   (desde `edw.dim_almacen`), actividad reciente (desde `fact_logs_auditoria` / `audit_repository`).

---

### Fase 6 (P1/P2) — Módulo Bodega: reportes y abastecimiento

**Fase 6.0 — auditoría de datos previa (obligatoria, `etl-edw-auditor`).**
Reconciliar con `SELECT` en ambos lados y el **mismo recorte** (`codemp='01'`, mismo rango,
`estado='P'`). Verificar en particular:
- Dirección de kardex por `tipdoc` incluyendo `AC`/`AD` (regla 3) — **H-7, divergencia esperada**.
- Transferencias `tiporg='TRA'` generan 2 filas pareadas (regla 4) → riesgo de doble conteo en el
  Stock, ya que ambas filas comparten `(numdoc, numren, codart)` y difieren solo en almacén/dirección.
- Cardinalidad de cada `JOIN` (conteo antes/después) — patrón de bug histórico del proyecto.
- Partición del `ROW_NUMBER()` contra el grano real del hecho en el EDW.
- `EXPLAIN` sobre las queries migradas (en el EDW; contra Producción, `EXPLAIN` plano solamente).

**Mapeo de origen SAP → EDW (verificado contra el DDL, no supuesto):**

| Origen (SAP) | Destino (EDW) | Nota |
|---|---|---|
| `dbo.kardex` | `edw.fact_movimientos_inventario` | `edw/03_hechos.sql:68-84` |
| `k.codalm` | `almacen_sk` → `edw.dim_almacen.codalm` | FK, no código crudo |
| `k.tiporg` | `tipo_movimiento` | `'FAC'`, `'CPA'`, `'TRA'`… |
| `k.tipdoc` (`EN`/`AC`/`SA`/`AD`) | `es_entrada` / `es_salida` (BOOLEAN) | Ya materializado y **correcto** (H-7) |
| `k.cantot` | `cantidad_movimiento` | Siempre positivo (regla 3) |
| `k.fecdoc` | `fecha_sk` → `edw.dim_fecha.fecha_completa` | Nunca comparar `fecha_sk` contra una fecha |
| `k.numdoc` | `num_documento` | |
| `k.codcli` | `cliente_sk` | **NULL salvo `tipo_movimiento='FAC'`** (comentario del DDL, auditoría 07 H5) — coincide con el `LEFT JOIN` de la query |
| `dbo.articulos` | `edw.dim_producto` | **SCD2**: filtrar `es_vigente = TRUE` (regla 7) |
| `a.nomart` / `a.codcla` / `a.prec01` | `nombre_articulo` / `clase` / `precio_oficial` | |
| `dbo.clasesarticulos.nomcla` | `dim_producto.nombre_clase` | **Vacío hoy — H-10** |
| `dbo.clientes.nomcli` | *(no se migra)* | **Decisión del usuario: la columna `Cliente` se omite** en los tres reportes. El `LEFT JOIN dbo.clientes` desaparece de las queries migradas |
| `a.exiact` | *(sin equivalente)* | **H-11** — derivar o declarar |

**Cambio de sustitución del `SUM(CASE tipdoc…)`:** en el EDW se escribe
`SUM(CASE WHEN es_entrada THEN cantidad_movimiento WHEN es_salida THEN -cantidad_movimiento ELSE 0 END)`,
lo que **corrige H-7 automáticamente** sin reescribir la regla.

**Columna `Cliente` — se omite (decisión del usuario, 2026-07-29).** Los tres reportes migrados
**no** incluyen el nombre del cliente. Consecuencias concretas en la migración:

- Desaparece el `LEFT JOIN dbo.clientes cli` del `_ULTIMA_VENTA_JOIN`, y `COALESCE(cli.nomcli, ...)`
  no se traduce. El `JOIN` a `public.cliente_lookup` **no se usa** en este módulo.
- **`FechaUltimaVenta` y `NumeroFactura` sí se conservan** — no son PII y responden la pregunta de
  negocio real del reporte ("¿hace cuánto que este artículo no se mueve en esta bodega?"). El
  subquery de última venta se mantiene, solo pierde la columna del nombre.
- El `GROUP BY` de las tres queries pierde `lv.Cliente`, y el `ORDER BY` no lo usaba.
- **Simplificación colateral:** al no haber PII, los reportes de Bodega no necesitan compuerta de rol
  para su contenido — basta la RLS por almacén de la Fase 1.b.

**Fase 6.1 — Corregir la clasificación de stock (H-2).**
- Introducir un estado nuevo **`"Inmovilizado"`** para `stock > 0` con `salida_diaria == 0` en la
  ventana analizada. Es información distinta de "Exceso" (que sí rota, pero demasiado lento) y
  distinta de "Seguro" (que es donde cae hoy, incorrectamente).
- El reporte "Productos en exceso de stock" pasa a incluir **`Exceso` ∪ `Inmovilizado`**, ordenado
  por capital inmovilizado (`stock × costo`) descendente — que es la pregunta de negocio real.
- Añadir umbral `BODEGA_DIAS_VENTANA_INMOVILIZADO` en `config.py` (default 90), nunca hardcodeado.
- **Caso "El Rey":** mostrar junto a "días de stock" la salida diaria que lo origina y una marca de
  baja confianza cuando `salida_diaria < BODEGA_MIN_SALIDA_CONFIABLE`, para que "0 días" no se lea
  como una urgencia idéntica a la de un producto de alta rotación.
- **Regla nueva a documentar:** `RN-B11`.

**Fase 6.2 — Reporte "Artículos sin movimiento en ventas por almacén" (§6.1 + requerimiento nuevo).**

Un solo reporte parametrizado que cubre `QUERY_PRODUCTOS_SIN_VENTA` y `QUERY_ARTICULOS_ESTANCADOS`
(son la misma query, H-9), reutilizando la infraestructura existente en vez de crear una paralela:

- **Repositorio:** método nuevo en `WarehouseRepository` (ya concentra el acceso a
  `fact_movimientos_inventario` y el choke point de filtros `_filtros_snapshot`).
- **Servicio:** método nuevo en `WarehouseService`, devolviendo el contrato **ya existente**
  `ReporteBodegaResponse` (`resumen_ejecutivo` / `interpretacion` / `secciones`) — así hereda gratis
  el renderizado de `BodegaReportes.tsx`, la exportación a Excel de `warehouse_export.py` y el PDF
  de la Fase 6.5, sin código de presentación nuevo.
- **Endpoint:** un `tipo` nuevo en `GET /reportes/{tipo}` (no una ruta aparte), con
  `?solo_con_stock=true` para el modo "estancados" y `false` para "sin venta".
- **Filtros:** almacén (sujeto a la RLS de la Fase 1), búsqueda por código/nombre, rango de fechas.
- **Traducción del `NOT EXISTS`:** "no tuvo movimientos con `tipo_movimiento='FAC'` en el rango" —
  el patrón se conserva; en PostgreSQL, evaluar `NOT EXISTS` vs. `LEFT JOIN ... IS NULL` con
  `EXPLAIN` y quedarse con el mejor plan.
- **`FechaUltimaVenta` / `NumeroFactura`:** `ROW_NUMBER() OVER (PARTITION BY almacen_sk,
  producto_sk ORDER BY fecha DESC, num_documento DESC)` sobre movimientos `FAC`, con el filtro de
  estado válido que la query original omite (H-8). **Sin la columna `Cliente`** (§6.0).
- **Precaución conocida:** `fact_inventario_snapshot` solo está poblada "hacia adelante"
  (<1% de histórico pre-2026, auditoría 05). Por eso el Stock se calcula **desde el kardex**
  (`fact_movimientos_inventario`), igual que la query original — no desde el snapshot.

**Fase 6.3 — UI/UX de los tres reportes de abastecimiento (§6.2).**
La Fase 5 del plan de Bodega ya estableció el contrato tipado
(`ReporteBodegaResponse` con `resumen_ejecutivo` / `interpretacion` / `secciones`) y la
`BodegaReportes.tsx` que lo renderiza. La mejora pedida se implementa **dentro de ese contrato**:
título + pregunta de negocio que responde cada reporte, y descripción explícita
("Productos con exceso de stock" / "Productos estancados" / "Productos sin salidas").

**Fase 6.4 — Nombres de archivo con fecha/hora (H-4).**
`warehouse.py:396` → `reporte_{tipo}_{YYYY-MM-DD_HH-MM}.xlsx`, generado en backend (zona horaria del
servidor, declarada), no en frontend.

**Fase 6.5 — PDF real (H-3).**
**Decisión del usuario (2026-07-29): generación en backend.**
Sustituir `window.print()` por un endpoint `GET /reportes/{tipo}/pdf` que construye el documento
**desde el contrato tipado** (`ReporteBodegaResponse`), no desde el DOM, reutilizando exactamente la
misma estructura que ya alimenta el Excel (`warehouse_export.py`) — una sola fuente de verdad para
Excel y PDF, y salida idéntica en cualquier navegador. Mismo `Content-Disposition` con fecha/hora
que la Fase 6.4. Requiere una dependencia nueva de generación de PDF en `backend/requirements.txt`,
a fijar con rango de versión igual que el resto del proyecto.

**Fase 6.6 — Motivos de transferencia (§6.4).**
`/transferencias-sugeridas` ya devuelve `justificacion` / `confianza` / `beneficio_neto_estimado`
(RN-B9). El problema es que el texto no es accionable. Reescribir el generador de `justificacion`
para que incluya, **solo con datos reales ya disponibles en el cálculo**: días sin movimiento en
origen, demanda observada en destino, beneficio neto estimado y la acción concreta. Ejemplo:
> "Sin salidas en 118 días en BODEGA A (32 uds, $1.240 inmovilizados). BODEGA B vendió 9 uds/mes en
> los últimos 6 meses y tiene 4 días de cobertura. Transferir 24 uds cubre 2,6 meses de su demanda."

**Sobre el ejemplo "Cliente asociado: X" del requerimiento:** técnicamente es implementable
(`fact_movimientos_inventario.cliente_sk` está poblada para `tipo_movimiento='FAC'`,
`edw/03_hechos.sql:85`), pero **se omite** por la misma decisión de §6.0: los reportes de Bodega no
llevan identidad de cliente. La justificación se construye solo con días sin movimiento, demanda del
destino y beneficio estimado — que es la información que el encargado de bodega necesita para actuar.

**Fase 6.7 — `QUERY_BODEGAS` y `QUERY_KARDEX_MOVIMIENTOS`.**

- **`QUERY_BODEGAS`** (`codalm`, `nomalm` desde `dbo.almacenes`) **ya está implementada**:
  `CatalogRepository.get_almacenes` (`catalog_repository.py:37-43`) lee
  `edw.dim_almacen` excluyendo el centinela `-1` (regla 12), y se expone en
  `GET /users/almacenes` (`users.py:16-23`). **No se reimplementa**; si el módulo Bodega necesita el
  catálogo, consume ese repositorio.
- **`QUERY_KARDEX_MOVIMIENTOS`**: implementar como `tipo` adicional del contrato tipado, corrigiendo
  H-11 — sustituir el `GROUP BY` sin agregación por `DISTINCT` (o por la agregación que corresponda
  al grano declarado) y **declarar explícitamente la fuente de `ExistenciaGlobal`**: se calcula
  sumando el kardex sobre todos los almacenes, con la etiqueta de la ventana usada, en vez de
  presentar un `exiact` que el EDW no almacena.

---

### Fase 7 (P3) — Dashboard principal por rol (§2)

Rediseñar el dashboard de entrada según el rol del token:
- **Vendedor:** progreso vs. meta, ventas día/semana/mes, alertas de productos críticos.
- **Gerente:** resumen ejecutivo de todos los vendedores, cumplimiento global, alertas comerciales.
- **Bodega / Admin:** ver Fases 5 y 6.

Reutilizar los generadores de notificación ya existentes (`NotificationService`) para las alertas en
vez de crear un cálculo paralelo que pueda derivar.

**Dependencia:** requiere la decisión de B-3 (sucursal vs. bodega) tomada en A-0.3.

---

## 4. Criterios de validación (aplican a todas las fases)

1. `cd backend && python -m pytest tests/ -v` — línea base actual conocida: **282 passed, 3 skipped,
   8 failed preexistentes** (4 por `ML_MODELS_DIR` sin resolver en el entorno de pruebas, 3 de
   metas/`goal_ml_service`, 1 de `classify_vendor_risk`). Cualquier fallo **nuevo** bloquea la fase.
2. `cd frontend && npx tsc --noEmit && npx oxlint src/` limpios en los archivos tocados.
3. Reconciliación EDW ↔ Producción (solo `SELECT`) re-ejecutada tras cada cambio de la Fase 6.
4. `edw/06_verificacion.sql` sin regresiones.
5. Prueba en vivo contra `bi_backend` / `bi_frontend` reales con un usuario de cada rol.
6. **Limitación conocida de este entorno:** no hay `chromium-cli`, así que la verificación visual en
   navegador real no es automatizable — queda como paso manual del usuario, declarado, no asumido.

## 5. Documentación exigida al cierre

- `docs/auditoria/42_correcciones_integrales_sistema.md` — hallazgos con severidad, evidencia
  (`archivo:línea` o SQL + resultado), impacto, riesgo y acción aplicada por fase.
- `docs/auditoria/02_reglas_negocio_validadas.md` — reglas nuevas `RN-B10` (RLS por almacén),
  `RN-B11` (estado Inmovilizado y días de stock de baja confianza), `RN-B12` (el Stock del kardex
  incluye los ajustes `AC`/`AD`, corrigiendo la query de Producción — H-7), `RN-B13` (los reportes
  del módulo Bodega no exponen identidad de cliente: la columna `Cliente` de las queries de
  Producción se omite deliberadamente), más las que surjan.
- **Anexo en la auditoría 42:** el SQL literal de las 4 queries de Producción entregadas por el
  usuario, para trazabilidad de la migración.
- `CLAUDE.md` — actualización del bloque de contexto al cerrar el plan.
- Comentarios en código explicando el **porqué**, con referencia al hallazgo que lo valida.

## 6. Secuencia recomendada

```
B-1, B-2, B-3 (usuario decide)
      │
   Fase 0 ── auditoría transversal
      │
      ├── Fase 1 (P0, seguridad)  ──┐
      ├── Fase 2 (P1, transversal) ─┤
      │                             ├── Fase 7 (dashboards)
      ├── Fase 3 (Gerencia)       ──┤
      ├── Fase 4 (Ventas)         ──┤
      ├── Fase 5 (Admin)          ──┤
      └── Fase 6 (Bodega)         ──┘
```

Fases 3-6 son independientes entre sí y pueden paralelizarse tras la Fase 2. La Fase 7 depende de
todas porque consume sus KPIs.
