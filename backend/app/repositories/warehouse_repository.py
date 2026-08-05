# backend/app/repositories/warehouse_repository.py
"""SQL del módulo Bodega (docs/features/modulo_bodega.md, auditoría 23).

Fuentes (H23-1): el inventario actual es SIEMPRE el último snapshot disponible de
`edw.fact_inventario_snapshot` (sumar histórico duplicaría conteos — mismo patrón
validado en AnalyticsRepository.get_inventory_alerts); las salidas se miden con
`edw.fact_movimientos_inventario.es_salida = TRUE` (regla de negocio 3: dirección
por tipdoc, nunca por signo). El grano de producto es `codart` (colapsa versiones
SCD2 de dim_producto para no partir el stock de un mismo artículo en dos filas).

Mismo estilo que AnalyticsRepository: cláusulas WHERE construidas con f-strings de
fragmentos fijos del propio código y SIEMPRE bind params para los valores.
"""

from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.exceptions import ValidationError
from app.utils.validators import sanitize_date_str

EXCLUIR_CODART = {"Z-9001"}

# Catálogo cerrado de kardex.tiporg (docs/auditoria/02_reglas_negocio_validadas.md §3):
# usado tanto para validar el filtro `tipo_movimiento` como para poblar el selector
# del frontend (WarehouseService.get_filtros).
TIPOS_MOVIMIENTO = [
    {"codigo": "FAC", "etiqueta": "Ventas (facturas)"},
    {"codigo": "TRA", "etiqueta": "Transferencias entre bodegas"},
    {"codigo": "EGR", "etiqueta": "Egresos"},
    {"codigo": "CPA", "etiqueta": "Compras"},
    {"codigo": "DEV", "etiqueta": "Devoluciones"},
    {"codigo": "ING", "etiqueta": "Ingresos"},
    {"codigo": "BOD", "etiqueta": "Ajustes de bodega"},
    {"codigo": "DEC", "etiqueta": "Ajustes / decrementos"},
]
_CODIGOS_TIPO_MOVIMIENTO = {t["codigo"] for t in TIPOS_MOVIMIENTO}

# RN-B8 (docs/auditoria/32_actualizacion_modulo_bodega.md H32-1): únicos 2 tipos de
# movimiento cuyo `valor_venta`/`costo_total` en `fact_movimientos_inventario`
# representa una venta o una compra real (el resto de tipos también trae esas
# columnas pobladas -- heredadas de kardex.totven/costot para cualquier movimiento --
# pero mostrarlas ahí induciría a error: no es dinero de venta ni de compra).
TIPOS_MOVIMIENTO_CON_MONTO = {"FAC": "venta", "CPA": "compra"}


class WarehouseRepository:
    def __init__(self, db: Session, almacenes_permitidos: list[str] | None = None):
        """`almacenes_permitidos` (RN-B10, docs/features/plan_correcciones_integrales_
        sistema.md Fase 1.b): restricción de seguridad resuelta por
        `resolve_almacenes_filter` a partir de las bodegas asignadas al usuario --
        `None` = sin restricción, `[]` = rol bodega sin ninguna asignada (no ve nada).
        Se aplica en `_filtros_snapshot`, el único choke point de filtros del módulo,
        así que las ~14 funciones públicas de este repositorio quedan cubiertas sin
        tocar cada una."""
        self.db = db
        self.almacenes_permitidos = almacenes_permitidos

    # ── Filtros comunes ─────────────────────────────────────────────────────
    def _filtros_snapshot(
        self, sucursal: str | None, almacen: str | None, categoria: str | None,
        proveedor: str | None, tipo_movimiento: str | None,
    ) -> tuple[str, dict[str, Any]]:
        """Filtros para queries basadas en el snapshot (alias fijos: su=dim_sucursal,
        al=dim_almacen, p=dim_producto). `almacen` es la elección del usuario en la
        barra de filtros; `self.almacenes_permitidos` es la restricción de seguridad --
        se aplican ambos, en AND (intersección), nunca solo el segundo ampliando al
        primero."""
        filtros: list[str] = []
        params: dict[str, Any] = {}

        if EXCLUIR_CODART:
        # Construir placeholders para los códigos a excluir
            placeholders = ", ".join([f":excl_{i}" for i in range(len(EXCLUIR_CODART))])
            for i, cod in enumerate(EXCLUIR_CODART):
                params[f"excl_{i}"] = cod
            filtros.append(f"p.codart NOT IN ({placeholders})")
        if sucursal:
            filtros.append("su.nombre_sucursal = :sucursal")
            params["sucursal"] = sucursal
        if almacen:
            filtros.append("al.nombre_almacen = :almacen")
            params["almacen"] = almacen
        if self.almacenes_permitidos is not None:
            if not self.almacenes_permitidos:
                # Rol bodega sin ninguna bodega asignada: no debe ver ningún dato.
                filtros.append("1 = 0")
            else:
                placeholders_alm = ", ".join(
                    f":alm_perm_{i}" for i in range(len(self.almacenes_permitidos))
                )
                for i, codalm in enumerate(self.almacenes_permitidos):
                    params[f"alm_perm_{i}"] = codalm
                filtros.append(f"al.codalm IN ({placeholders_alm})")
        if categoria:
            filtros.append("p.clase = :categoria")
            params["categoria"] = categoria
        if proveedor:
            # El ERP no guarda proveedor en el artículo: se infiere de fact_compras
            # (qué artículos se le compran a cada proveedor, requerimiento §1.1).
            filtros.append(
                "p.codart IN (SELECT p2.codart FROM edw.fact_compras fc "
                "JOIN edw.dim_producto p2 ON fc.producto_sk = p2.producto_sk "
                "JOIN edw.dim_proveedor pr ON fc.proveedor_sk = pr.proveedor_sk "
                "WHERE pr.nombre_proveedor = :proveedor)"
            )
            params["proveedor"] = proveedor
        if tipo_movimiento:
            if tipo_movimiento not in _CODIGOS_TIPO_MOVIMIENTO:
                raise ValidationError(
                    f"tipo_movimiento inválido: '{tipo_movimiento}'. Valores permitidos: "
                    f"{', '.join(sorted(_CODIGOS_TIPO_MOVIMIENTO))}."
                )
            # Filtro por tipo de movimiento de Kardex (kardex.tiporg, regla de negocio §3):
            # solo incluye artículos con AL MENOS UN movimiento de ese tipo (FAC=venta,
            # TRA=transferencia entre bodegas, EGR=egreso, CPA=compra, DEV=devolución,
            # BOD=ajuste de bodega, ING=ingreso, DEC=ajuste/decremento). FAC en particular
            # matchea ~462k de las ~949k filas del hecho (casi todo el catálogo alguna vez
            # se vendió) -- muy poco selectivo. El IN anidado por producto_sk (en vez de
            # unir primero a dim_producto por codart) deja que Postgres resuelva un Hash/
            # Nested Loop Semi Join que se detiene en el primer movimiento por producto,
            # en vez de materializar las 462k filas antes de deduplicar: medido 113ms →
            # 12ms contra el EDW real, evitando el `DiskFull` de /dev/shm (64MB) que
            # tumbaba /kpis y otros endpoints con varias CTEs que repiten este filtro
            # (docs/auditoria/28_bug_filtro_tipo_movimiento.md).
            filtros.append(
                "p.codart IN (SELECT p2.codart FROM edw.dim_producto p2 "
                "WHERE p2.producto_sk IN (SELECT fmi.producto_sk "
                "FROM edw.fact_movimientos_inventario fmi "
                "WHERE fmi.tipo_movimiento = :tipo_movimiento))"
            )
            params["tipo_movimiento"] = tipo_movimiento
        clausula = (" AND " + " AND ".join(filtros)) if filtros else ""
        return clausula, params

    @staticmethod
    def _rango_fechas(
        fecha_desde: str | None, fecha_hasta: str | None, params: dict[str, Any],
    ) -> str:
        """Fragmento de rango sobre dim_fecha (alias d) para hechos de movimiento/venta."""
        fecha_desde = sanitize_date_str(fecha_desde)
        fecha_hasta = sanitize_date_str(fecha_hasta)
        fragmentos = []
        if fecha_desde:
            fragmentos.append("d.fecha_completa >= :fecha_desde")
            params["fecha_desde"] = fecha_desde
        if fecha_hasta:
            fragmentos.append("d.fecha_completa <= :fecha_hasta")
            params["fecha_hasta"] = fecha_hasta
        return (" AND " + " AND ".join(fragmentos)) if fragmentos else ""

    # ── Surtido real por almacén (KPI "Artículos en Inventario") ────────────
    def get_skus_surtido(
        self, sucursal: str | None = None, almacen: str | None = None,
        categoria: str | None = None, proveedor: str | None = None, tipo_movimiento: str | None = None,
    ) -> int:
        """Tamaño real del surtido de un almacén/sucursal. `vi_mv_existencias` (SAP) no
        distingue "nunca asignado a este almacén" de "agotado temporalmente": siempre expone
        TODO el catálogo por almacén con existencia 0 donde nunca hubo stock, por lo que
        `COUNT(DISTINCT codart)` sobre el snapshot da el mismo número (tamaño del catálogo)
        sin importar el almacén filtrado. Se aproxima el surtido real contando los codart con
        AL MENOS UN movimiento histórico de kardex en el almacén (fact_movimientos_inventario,
        cualquier dirección -- regla de negocio 3); verificado que ningún codart con stock
        actual > 0 carece de movimiento histórico, así que nunca subcuenta lo realmente activo."""
        where_extra, params = self._filtros_snapshot(sucursal, almacen, categoria, proveedor, tipo_movimiento)
        query = f"""
            SELECT COUNT(DISTINCT p.codart)
            FROM edw.fact_movimientos_inventario m
            JOIN edw.dim_producto p ON m.producto_sk = p.producto_sk
            JOIN edw.dim_almacen  al ON m.almacen_sk = al.almacen_sk
            JOIN edw.dim_sucursal su ON m.sucursal_sk = su.sucursal_sk
            WHERE p.producto_sk <> -1 {where_extra}
        """
        return int(self.db.execute(text(query), params).scalar() or 0)

    # ── Reabastecimiento Inteligente (docs/features/plan_reabastecimiento_
    # inteligente.md §6.4, auditoría docs/auditoria/50_..md) ────────────────
    def get_metricas_reabastecimiento(
        self, sucursal: str | None = None, almacen: str | None = None,
        categoria: str | None = None, proveedor: str | None = None,
        tipo_movimiento: str | None = None, meses_ventana: int = 12,
    ) -> list[dict[str, Any]]:
        """Insumo crudo del motor puro (`replenishment_engine`): stock/costo actual
        (último snapshot, mismo criterio que `get_inventario_productos`), valor de
        consumo de `meses_ventana` meses (para ABC, ordenado por el llamador -- esta
        consulta no calcula el acumulado de Pareto, eso es responsabilidad del
        servicio, que ya tiene TODO el catálogo en memoria) y estadística mensual de
        salidas (para XYZ y para `estadistica_demanda`: media/sigma sobre unidades
        mensuales, más `meses_con_venta` para decidir el método). Reutiliza
        `_filtros_snapshot` -- mismo choke point de RLS que el resto del repositorio."""
        where_extra, params = self._filtros_snapshot(sucursal, almacen, categoria, proveedor, tipo_movimiento)
        params["meses_ventana"] = meses_ventana

        query = f"""
            WITH ultimo AS (SELECT MAX(fecha_sk) AS fecha_sk FROM edw.fact_inventario_snapshot),
            snap AS (
                SELECT p.codart,
                       MAX(p.nombre_articulo)              AS nombre,
                       MAX(COALESCE(p.clase, 'SIN-CLASE'))  AS categoria,
                       SUM(s.stock_actual)                  AS stock_actual,
                       MAX(s.costo_promedio)                AS costo_unitario,
                       SUM(s.punto_reorden)                 AS punto_reorden_config
                FROM edw.fact_inventario_snapshot s
                JOIN ultimo u ON s.fecha_sk = u.fecha_sk
                JOIN edw.dim_producto p ON s.producto_sk = p.producto_sk
                JOIN edw.dim_almacen  al ON s.almacen_sk = al.almacen_sk
                JOIN edw.dim_sucursal su ON s.sucursal_sk = su.sucursal_sk
                WHERE p.producto_sk <> -1 {where_extra}
                GROUP BY p.codart
            ),
            valor_consumo AS (
                SELECT p.codart, SUM(v.cantidad * v.costo_unitario) AS valor_consumo
                FROM edw.fact_ventas_detalle v
                JOIN edw.dim_producto p ON p.producto_sk = v.producto_sk
                JOIN edw.dim_fecha d ON d.fecha_sk = v.fecha_sk
                JOIN edw.dim_almacen  al ON v.almacen_sk = al.almacen_sk
                JOIN edw.dim_sucursal su ON v.sucursal_sk = su.sucursal_sk
                WHERE p.producto_sk <> -1
                  AND d.fecha_completa >= CURRENT_DATE - (:meses_ventana * INTERVAL '1 month')
                  {where_extra}
                GROUP BY p.codart
            ),
            mensual AS (
                SELECT p.codart, d.anio, d.mes, SUM(m.cantidad_movimiento) AS unidades
                FROM edw.fact_movimientos_inventario m
                JOIN edw.dim_producto p ON p.producto_sk = m.producto_sk
                JOIN edw.dim_fecha d ON d.fecha_sk = m.fecha_sk
                JOIN edw.dim_almacen  al ON m.almacen_sk = al.almacen_sk
                JOIN edw.dim_sucursal su ON m.sucursal_sk = su.sucursal_sk
                WHERE m.es_salida AND p.producto_sk <> -1
                  AND d.fecha_completa >= CURRENT_DATE - (:meses_ventana * INTERVAL '1 month')
                  {where_extra}
                GROUP BY p.codart, d.anio, d.mes
            ),
            demanda AS (
                SELECT codart,
                       COUNT(*)                                    AS meses_con_venta,
                       ARRAY_AGG(unidades ORDER BY anio, mes)       AS unidades_mensuales
                FROM mensual GROUP BY codart
            )
            SELECT snap.codart, snap.nombre, snap.categoria, snap.stock_actual,
                   snap.costo_unitario, snap.punto_reorden_config,
                   COALESCE(vc.valor_consumo, 0)      AS valor_consumo,
                   COALESCE(d.meses_con_venta, 0)      AS meses_con_venta,
                   COALESCE(d.unidades_mensuales, ARRAY[]::numeric[]) AS unidades_mensuales
            FROM snap
            LEFT JOIN valor_consumo vc ON vc.codart = snap.codart
            LEFT JOIN demanda d ON d.codart = snap.codart
        """
        res = self.db.execute(text(query), params).fetchall()
        return [
            {
                "codart": str(r[0]),
                "nombre": str(r[1]),
                "categoria": str(r[2]),
                "stock_actual": float(r[3] or 0),
                "costo_unitario": float(r[4] or 0),
                "punto_reorden_config": float(r[5] or 0),
                "valor_consumo": float(r[6] or 0),
                "meses_con_venta": int(r[7] or 0),
                "unidades_mensuales": [float(u) for u in (r[8] or [])],
            }
            for r in res
        ]

    # ── Catálogos para los filtros globales (§1.1) ──────────────────────────
    def get_proveedores(self, categoria: str | None = None) -> list[str]:
        """Catálogo de proveedores para el filtro de bodega. `categoria` (Fase 2,
        docs/features/plan_correcciones_integrales_sistema.md §Fase 2.2 -- filtros
        "inteligentes"): si se pasa, restringe a los proveedores que realmente
        suministran algún artículo de esa categoría (`edw.fact_compras`, mismo criterio
        de inferencia que `_filtros_snapshot` usa para el filtro `proveedor` -- el ERP
        no guarda proveedor en el artículo directamente)."""
        # Centinela -1 fuera del catálogo (regla 12), mismo criterio que get_almacenes.
        if not categoria:
            res = self.db.execute(text(
                "SELECT DISTINCT nombre_proveedor FROM edw.dim_proveedor "
                "WHERE nombre_proveedor IS NOT NULL AND proveedor_sk <> -1 ORDER BY nombre_proveedor"
            )).fetchall()
            return [str(r[0]) for r in res]
        res = self.db.execute(text(
            "SELECT DISTINCT pr.nombre_proveedor FROM edw.dim_proveedor pr "
            "WHERE pr.nombre_proveedor IS NOT NULL AND pr.proveedor_sk <> -1 AND EXISTS ("
            "  SELECT 1 FROM edw.fact_compras fc "
            "  JOIN edw.dim_producto p2 ON fc.producto_sk = p2.producto_sk "
            "  WHERE fc.proveedor_sk = pr.proveedor_sk AND p2.clase = :categoria"
            ") ORDER BY pr.nombre_proveedor"
        ), {"categoria": categoria}).fetchall()
        return [str(r[0]) for r in res]

    # ── Inventario maestro por producto (KPIs, G5, G6, plan de compras) ────
    def get_inventario_productos(
        self, sucursal: str | None = None, almacen: str | None = None,
        categoria: str | None = None, proveedor: str | None = None,
        tipo_movimiento: str | None = None, dias_salidas: int = 30,
        dias_ventana_inmovilizado: int = settings.BODEGA_DIAS_VENTANA_INMOVILIZADO,
    ) -> list[dict[str, Any]]:
        """Una fila por codart: stock/valor del último snapshot (sumado sobre los
        almacenes filtrados) + salidas de los últimos `dias_salidas` días + salidas del
        período previo equivalente (tendencia) + salidas de la ventana más amplia
        `dias_ventana_inmovilizado` (Fase 6.1, H-2/RN-B11: clasificar "Inmovilizado" con
        una ventana de 90 días evita marcar como estancado un artículo que simplemente
        no vendió en los últimos 30 días por estacionalidad)."""
        where_extra, params = self._filtros_snapshot(sucursal, almacen, categoria, proveedor, tipo_movimiento)
        params["dias"] = dias_salidas
        params["dias_inmov"] = dias_ventana_inmovilizado

        query = f"""
            WITH ultimo AS (SELECT MAX(fecha_sk) AS fecha_sk FROM edw.fact_inventario_snapshot),
            snap AS (
                SELECT p.codart,
                       MAX(p.nombre_articulo)              AS nombre_articulo,
                       MAX(COALESCE(p.clase, 'SIN-CLASE')) AS categoria,
                       SUM(s.stock_actual)                 AS stock_actual,
                       SUM(s.valor_inventario)             AS valor_inventario,
                       MAX(s.costo_promedio)               AS costo_unitario,
                       SUM(s.punto_reorden)                AS punto_reorden_config
                FROM edw.fact_inventario_snapshot s
                JOIN ultimo u ON s.fecha_sk = u.fecha_sk
                JOIN edw.dim_producto p ON s.producto_sk = p.producto_sk
                JOIN edw.dim_almacen  al ON s.almacen_sk = al.almacen_sk
                JOIN edw.dim_sucursal su ON s.sucursal_sk = su.sucursal_sk
                WHERE p.producto_sk <> -1 {where_extra}
                GROUP BY p.codart
            ),
            salidas AS (
                SELECT p.codart,
                       SUM(m.cantidad_movimiento) FILTER (
                           WHERE d.fecha_completa >= CURRENT_DATE - (:dias * INTERVAL '1 day')
                       ) AS salidas_periodo,
                       SUM(m.cantidad_movimiento) FILTER (
                           WHERE d.fecha_completa <  CURRENT_DATE - (:dias * INTERVAL '1 day')
                       ) AS salidas_periodo_anterior,
                       SUM(m.cantidad_movimiento) FILTER (
                           WHERE d.fecha_completa >= CURRENT_DATE - (:dias_inmov * INTERVAL '1 day')
                       ) AS salidas_ventana_inmovilizado
                FROM edw.fact_movimientos_inventario m
                JOIN edw.dim_fecha d ON m.fecha_sk = d.fecha_sk
                JOIN edw.dim_producto p ON m.producto_sk = p.producto_sk
                JOIN edw.dim_almacen  al ON m.almacen_sk = al.almacen_sk
                JOIN edw.dim_sucursal su ON m.sucursal_sk = su.sucursal_sk
                WHERE m.es_salida
                  AND d.fecha_completa >= CURRENT_DATE - (GREATEST(2 * :dias, :dias_inmov) * INTERVAL '1 day')
                  {where_extra}
                GROUP BY p.codart
            )
            SELECT snap.codart, snap.nombre_articulo, snap.categoria,
                   snap.stock_actual, snap.valor_inventario, snap.costo_unitario,
                   snap.punto_reorden_config,
                   COALESCE(sal.salidas_periodo, 0)               AS salidas_periodo,
                   COALESCE(sal.salidas_periodo_anterior, 0)      AS salidas_periodo_anterior,
                   COALESCE(sal.salidas_ventana_inmovilizado, 0)  AS salidas_ventana_inmovilizado
            FROM snap
            LEFT JOIN salidas sal ON sal.codart = snap.codart
            ORDER BY salidas_periodo DESC, snap.valor_inventario DESC
        """
        res = self.db.execute(text(query), params).fetchall()
        return [
            {
                "codart": str(r[0]),
                "nombre": str(r[1]),
                "categoria": str(r[2]),
                "stock_actual": float(r[3] or 0),
                "valor_inventario": float(r[4] or 0),
                "costo_unitario": float(r[5] or 0),
                "punto_reorden_config": float(r[6] or 0),
                "salidas_periodo": float(r[7] or 0),
                "salidas_periodo_anterior": float(r[8] or 0),
                "salidas_ventana_inmovilizado": float(r[9] or 0),
            }
            for r in res
        ]

    # ── Fase 6.2 (H-9): "Artículos sin movimiento en ventas por almacén" ────
    # Reporte único parametrizado que reemplaza QUERY_PRODUCTOS_SIN_VENTA y
    # QUERY_ARTICULOS_ESTANCADOS (misma query en Producción salvo un `HAVING`, ver
    # docs/features/plan_correcciones_integrales_sistema.md §6.2 / H-9).
    def get_articulos_sin_venta(
        self, fecha_desde: str, fecha_hasta: str,
        sucursal: str | None = None, almacen: str | None = None,
        categoria: str | None = None, proveedor: str | None = None,
        solo_con_stock: bool = True, busqueda: str | None = None, limit: int = 500,
    ) -> list[dict[str, Any]]:
        """Una fila por (codart, almacén) sin ninguna venta (`tipo_movimiento='FAC'`) en
        `[fecha_desde, fecha_hasta]`. `solo_con_stock=True` = "artículos estancados"
        (tienen existencia pero no rotan); `False` = "sin venta" completo (incluye
        artículos con stock cero o negativo -- H-9: antes eran dos queries casi
        idénticas, ahora un solo filtro). El universo son las combinaciones
        (producto, almacén) con AL MENOS UN movimiento histórico (evita escanear el
        catálogo completo del ERP contra bodegas donde el artículo nunca ha estado).

        Stock actual se calcula agregando el kardex completo (regla 3: dirección por
        `es_entrada`/`es_salida`, nunca por signo) en vez de `fact_inventario_snapshot`
        -- el snapshot solo está poblado "hacia adelante" (<1% de histórico pre-2026,
        auditoría 05), y este reporte necesita responder correctamente sobre rangos de
        fecha arbitrarios, no solo el estado de hoy.

        `FechaUltimaVenta`/`NumeroFactura` (última venta histórica, no solo en el rango
        analizado -- responde "¿cuándo fue la última vez que se vendió, si acaso?") vía
        `ROW_NUMBER() OVER (PARTITION BY almacen_sk, producto_sk ORDER BY fecha DESC,
        num_documento DESC)` sobre movimientos `FAC`.

        **Limitación heredada, no introducida por este método (H-8 del plan):**
        `fact_movimientos_inventario` no tiene columna de estado de documento --
        verificado en `etl/extractors/kardex_extractor.sql`, que no aplica el token
        `{ESTADO}` (a diferencia de otros extractores) -- así que una factura anulada
        ('A') puede aparecer como "última venta" si es la más reciente. Corregirlo
        requeriría un cambio de ETL/esquema (agregar la columna y re-extraer desde SAP),
        fuera del alcance de este reporte; se documenta en vez de fingir que no existe.
        Sin columna `Cliente` -- decisión del usuario (§6.0 del plan)."""
        where_extra, params = self._filtros_snapshot(sucursal, almacen, categoria, proveedor, None)
        params["fecha_desde"] = fecha_desde
        params["fecha_hasta"] = fecha_hasta
        params["limit"] = limit
        clausula_busqueda = ""
        if busqueda:
            clausula_busqueda = "AND (p.codart ILIKE :busqueda OR p.nombre_articulo ILIKE :busqueda)"
            params["busqueda"] = f"%{busqueda}%"
        clausula_stock = "HAVING MAX(COALESCE(stk.stock_actual, 0)) > 0" if solo_con_stock else ""

        query = f"""
            WITH universo AS (
                SELECT DISTINCT m.producto_sk, m.almacen_sk
                FROM edw.fact_movimientos_inventario m
                JOIN edw.dim_producto p ON m.producto_sk = p.producto_sk
                JOIN edw.dim_almacen  al ON m.almacen_sk = al.almacen_sk
                JOIN edw.dim_sucursal su ON m.sucursal_sk = su.sucursal_sk
                WHERE p.producto_sk <> -1 AND al.almacen_sk <> -1 {where_extra}
            ),
            stock AS (
                SELECT m.producto_sk, m.almacen_sk,
                       SUM(CASE WHEN m.es_entrada THEN m.cantidad_movimiento
                                WHEN m.es_salida THEN -m.cantidad_movimiento ELSE 0 END) AS stock_actual
                FROM edw.fact_movimientos_inventario m
                JOIN universo u ON u.producto_sk = m.producto_sk AND u.almacen_sk = m.almacen_sk
                GROUP BY m.producto_sk, m.almacen_sk
            ),
            ventas_ordenadas AS (
                SELECT m.producto_sk, m.almacen_sk, d.fecha_completa AS fecha, m.num_documento,
                       ROW_NUMBER() OVER (
                           PARTITION BY m.almacen_sk, m.producto_sk ORDER BY d.fecha_completa DESC, m.num_documento DESC
                       ) AS rn
                FROM edw.fact_movimientos_inventario m
                JOIN edw.dim_fecha d ON m.fecha_sk = d.fecha_sk
                JOIN universo u ON u.producto_sk = m.producto_sk AND u.almacen_sk = m.almacen_sk
                WHERE m.tipo_movimiento = 'FAC'
            ),
            sin_venta_rango AS (
                SELECT u.producto_sk, u.almacen_sk
                FROM universo u
                WHERE NOT EXISTS (
                    SELECT 1 FROM edw.fact_movimientos_inventario m2
                    JOIN edw.dim_fecha d2 ON m2.fecha_sk = d2.fecha_sk
                    WHERE m2.tipo_movimiento = 'FAC'
                      AND m2.producto_sk = u.producto_sk AND m2.almacen_sk = u.almacen_sk
                      AND d2.fecha_completa BETWEEN :fecha_desde AND :fecha_hasta
                )
            )
            SELECT p.codart, MAX(p.nombre_articulo) AS nombre, MAX(COALESCE(p.clase, 'SIN-CLASE')) AS categoria,
                   al.nombre_almacen, MAX(COALESCE(stk.stock_actual, 0)) AS stock_actual,
                   MAX(p.costo_promedio) AS costo_unitario,
                   MAX(uv.fecha) AS fecha_ultima_venta, MAX(uv.num_documento) AS numero_factura
            FROM sin_venta_rango sv
            JOIN edw.dim_producto p ON p.producto_sk = sv.producto_sk
            JOIN edw.dim_almacen al ON al.almacen_sk = sv.almacen_sk
            LEFT JOIN stock stk ON stk.producto_sk = sv.producto_sk AND stk.almacen_sk = sv.almacen_sk
            LEFT JOIN ventas_ordenadas uv
                ON uv.producto_sk = sv.producto_sk AND uv.almacen_sk = sv.almacen_sk AND uv.rn = 1
            WHERE 1 = 1 {clausula_busqueda}
            GROUP BY p.codart, al.nombre_almacen, sv.producto_sk, sv.almacen_sk
            {clausula_stock}
            ORDER BY stock_actual DESC
            LIMIT :limit
        """
        res = self.db.execute(text(query), params).fetchall()
        return [
            {
                "codart": str(r[0]),
                "nombre": str(r[1]),
                "categoria": str(r[2]),
                "almacen": str(r[3]),
                "stock_actual": float(r[4] or 0),
                "costo_unitario": float(r[5] or 0),
                "fecha_ultima_venta": r[6].isoformat() if r[6] else None,
                "numero_factura": r[7],
            }
            for r in res
        ]

    def get_movimientos_kardex(
        self, fecha_desde: str, fecha_hasta: str,
        sucursal: str | None = None, almacen: str | None = None,
        categoria: str | None = None, proveedor: str | None = None,
        tipo_movimiento: str | None = None, busqueda: str | None = None, limit: int = 1000,
    ) -> list[dict[str, Any]]:
        """Fase 6.7 (H-11 del plan): migración de `QUERY_KARDEX_MOVIMIENTOS` al EDW.
        Grano de la fila = un movimiento individual de kardex (mismo grano que
        `edw.fact_movimientos_inventario`) -- corrige el `GROUP BY` sin agregación de
        la query original (era un `DISTINCT` disfrazado) con un `SELECT` directo sobre
        el hecho, sin agrupar.

        `existencia_global` (columna `a.exiact` de la query original) **no tiene
        equivalente directo en el EDW** -- `dim_producto` no almacena existencia. Se
        deriva sumando el kardex COMPLETO (todos los almacenes, todo el histórico
        disponible) por producto, igual que el cálculo de stock del resto del módulo
        (regla 3: dirección por `es_entrada`/`es_salida`, nunca por signo) -- la fuente
        se declara explícitamente en el título de columna del contrato tipado, nunca
        se sirve en silencio como si fuera el mismo dato que `exiact` de Producción.

        `tipo_movimiento` se aplica directo sobre `m.tipo_movimiento` (cada fila ES ese
        movimiento) -- a diferencia del resto de reportes del módulo, donde
        `_filtros_snapshot` lo traduce a "artículos que alguna vez tuvieron ese tipo de
        movimiento" (semántica correcta para agregados por artículo, pero incorrecta
        para un listado de movimientos individuales: filtrar por FAC debe devolver solo
        filas FAC, no todas las filas de artículos que alguna vez se vendieron)."""
        where_extra, params = self._filtros_snapshot(sucursal, almacen, categoria, proveedor, None)
        params["fecha_desde"] = fecha_desde
        params["fecha_hasta"] = fecha_hasta
        params["limit"] = limit
        clausula_busqueda = ""
        if busqueda:
            clausula_busqueda = "AND (p.codart ILIKE :busqueda OR p.nombre_articulo ILIKE :busqueda)"
            params["busqueda"] = f"%{busqueda}%"
        clausula_tipo = ""
        if tipo_movimiento:
            if tipo_movimiento not in _CODIGOS_TIPO_MOVIMIENTO:
                raise ValidationError(
                    f"tipo_movimiento inválido: '{tipo_movimiento}'. Valores permitidos: "
                    f"{', '.join(sorted(_CODIGOS_TIPO_MOVIMIENTO))}."
                )
            clausula_tipo = "AND m.tipo_movimiento = :tipo_movimiento"
            params["tipo_movimiento"] = tipo_movimiento

        query = f"""
            WITH existencia_global AS (
                SELECT m2.producto_sk,
                       SUM(CASE WHEN m2.es_entrada THEN m2.cantidad_movimiento
                                WHEN m2.es_salida THEN -m2.cantidad_movimiento ELSE 0 END) AS existencia_global
                FROM edw.fact_movimientos_inventario m2
                GROUP BY m2.producto_sk
            )
            SELECT d.fecha_completa AS fecha, al.nombre_almacen AS almacen,
                   p.codart, p.nombre_articulo AS nombre, COALESCE(p.clase, 'SIN-CLASE') AS categoria,
                   m.tipo_movimiento,
                   CASE WHEN m.es_entrada THEN 'Entrada' WHEN m.es_salida THEN 'Salida' ELSE 'N/D' END AS direccion,
                   m.cantidad_movimiento AS cantidad, m.num_documento AS numero_documento,
                   COALESCE(eg.existencia_global, 0) AS existencia_global
            FROM edw.fact_movimientos_inventario m
            JOIN edw.dim_fecha d ON m.fecha_sk = d.fecha_sk
            JOIN edw.dim_producto p ON m.producto_sk = p.producto_sk
            JOIN edw.dim_almacen al ON m.almacen_sk = al.almacen_sk
            JOIN edw.dim_sucursal su ON m.sucursal_sk = su.sucursal_sk
            LEFT JOIN existencia_global eg ON eg.producto_sk = m.producto_sk
            WHERE p.producto_sk <> -1 AND al.almacen_sk <> -1
              AND d.fecha_completa BETWEEN :fecha_desde AND :fecha_hasta
              {where_extra} {clausula_busqueda} {clausula_tipo}
            ORDER BY d.fecha_completa DESC, al.nombre_almacen, p.codart
            LIMIT :limit
        """
        res = self.db.execute(text(query), params).fetchall()
        return [
            {
                "fecha": r[0].isoformat() if r[0] else None,
                "almacen": str(r[1]),
                "codart": str(r[2]),
                "nombre": str(r[3]),
                "categoria": str(r[4]),
                "tipo_movimiento": str(r[5]),
                "direccion": str(r[6]),
                "cantidad": float(r[7] or 0),
                "numero_documento": r[8],
                "existencia_global": float(r[9] or 0),
            }
            for r in res
        ]

    # ── KPIs de período (rotación, valor, stockouts, comparativa mensual) ──
    def get_kpis_periodo(
        self, fecha_desde: str | None, fecha_hasta: str | None,
        sucursal: str | None = None, almacen: str | None = None,
        categoria: str | None = None, proveedor: str | None = None,
        tipo_movimiento: str | None = None,
    ) -> dict[str, Any]:
        where_extra, params = self._filtros_snapshot(sucursal, almacen, categoria, proveedor, tipo_movimiento)
        rango = self._rango_fechas(fecha_desde, fecha_hasta, params)

        # Rotación (RN-B5): costo de ventas del período / inventario promedio del
        # período (promedio de los snapshots dentro del rango; si no hay ninguno,
        # el servicio degrada usando el valor del último snapshot).
        query = f"""
            WITH costo_ventas AS (
                SELECT COALESCE(SUM(f.costo_total), 0) AS costo,
                       COUNT(DISTINCT d.fecha_completa) AS dias_con_venta
                FROM edw.fact_ventas_detalle f
                JOIN edw.dim_fecha d ON f.fecha_sk = d.fecha_sk
                JOIN edw.dim_producto p ON f.producto_sk = p.producto_sk
                JOIN edw.dim_almacen  al ON f.almacen_sk = al.almacen_sk
                JOIN edw.dim_sucursal su ON f.sucursal_sk = su.sucursal_sk
                JOIN edw.dim_estado_documento ed ON f.estado_documento_sk = ed.estado_documento_sk
                WHERE ed.estado_documento_sk <> -1 {where_extra} {rango}
            ),
            inv_por_dia AS (
                SELECT d.fecha_completa,
                       SUM(s.valor_inventario) AS valor_dia,
                       COUNT(*) FILTER (WHERE s.stock_actual <= 0) AS skus_sin_stock,
                       COUNT(*) AS skus_total
                FROM edw.fact_inventario_snapshot s
                JOIN edw.dim_fecha d ON s.fecha_sk = d.fecha_sk
                JOIN edw.dim_producto p ON s.producto_sk = p.producto_sk
                JOIN edw.dim_almacen  al ON s.almacen_sk = al.almacen_sk
                JOIN edw.dim_sucursal su ON s.sucursal_sk = su.sucursal_sk
                WHERE p.producto_sk <> -1 {where_extra} {rango}
                GROUP BY d.fecha_completa
            )
            SELECT cv.costo,
                   (SELECT AVG(valor_dia) FROM inv_por_dia),
                   (SELECT SUM(skus_sin_stock)::float / NULLIF(SUM(skus_total), 0) * 100 FROM inv_por_dia),
                   (SELECT COUNT(*) FROM inv_por_dia)
            FROM costo_ventas cv
        """
        r = self.db.execute(text(query), params).fetchone()
        return {
            "costo_ventas": float(r[0] or 0) if r else 0.0,
            "inventario_promedio": float(r[1]) if r and r[1] is not None else None,
            "tasa_stockout_pct": round(float(r[2]), 2) if r and r[2] is not None else None,
            "dias_snapshot_periodo": int(r[3] or 0) if r else 0,
        }

    def get_snapshot_total_a_fecha(
        self, fecha_corte: str | None, sucursal: str | None = None, almacen: str | None = None,
        categoria: str | None = None, proveedor: str | None = None, tipo_movimiento: str | None = None,
    ) -> dict[str, Any] | None:
        """Totales (SKUs, valor) del snapshot más reciente <= fecha_corte (o el último
        disponible si fecha_corte es None). Para la tendencia "vs mes anterior" (H23-2:
        si no existe snapshot previo devuelve None y el frontend muestra '—')."""
        where_extra, params = self._filtros_snapshot(sucursal, almacen, categoria, proveedor, tipo_movimiento)
        fecha_corte = sanitize_date_str(fecha_corte)
        corte = ""
        if fecha_corte:
            corte = "WHERE d.fecha_completa <= :fecha_corte"
            params["fecha_corte"] = fecha_corte

        query = f"""
            WITH corte AS (
                SELECT MAX(s.fecha_sk) AS fecha_sk
                FROM edw.fact_inventario_snapshot s
                JOIN edw.dim_fecha d ON s.fecha_sk = d.fecha_sk
                {corte}
            )
            SELECT COUNT(DISTINCT p.codart)                                  AS total_skus,
                   COUNT(DISTINCT p.codart) FILTER (WHERE s.stock_actual > 0) AS skus_activos,
                   COALESCE(SUM(s.valor_inventario), 0)                       AS valor_total,
                   COALESCE(SUM(s.stock_actual), 0)                          AS cantidad_total
            FROM edw.fact_inventario_snapshot s
            JOIN corte c ON s.fecha_sk = c.fecha_sk
            JOIN edw.dim_producto p ON s.producto_sk = p.producto_sk
            JOIN edw.dim_almacen  al ON s.almacen_sk = al.almacen_sk
            JOIN edw.dim_sucursal su ON s.sucursal_sk = su.sucursal_sk
            WHERE p.producto_sk <> -1 {where_extra}
        """
        r = self.db.execute(text(query), params).fetchone()
        if not r or not r[0]:
            return None
        return {
            "total_skus": int(r[0]),
            "skus_activos": int(r[1] or 0),
            "valor_total": float(r[2] or 0),
            "cantidad_total": float(r[3] or 0),
        }

    def get_valor_por_categoria(
        self, sucursal: str | None = None, almacen: str | None = None,
        proveedor: str | None = None, tipo_movimiento: str | None = None, limit: int = 5,
    ) -> list[dict[str, Any]]:
        """Top categorías por valor de inventario del último snapshot (KPI 5)."""
        where_extra, params = self._filtros_snapshot(sucursal, almacen, None, proveedor, tipo_movimiento)
        params["limit"] = limit
        query = f"""
            WITH ultimo AS (SELECT MAX(fecha_sk) AS fecha_sk FROM edw.fact_inventario_snapshot)
            SELECT COALESCE(p.clase, 'SIN-CLASE') AS categoria, SUM(s.valor_inventario) AS valor
            FROM edw.fact_inventario_snapshot s
            JOIN ultimo u ON s.fecha_sk = u.fecha_sk
            JOIN edw.dim_producto p ON s.producto_sk = p.producto_sk
            JOIN edw.dim_almacen  al ON s.almacen_sk = al.almacen_sk
            JOIN edw.dim_sucursal su ON s.sucursal_sk = su.sucursal_sk
            WHERE p.producto_sk <> -1 {where_extra}
            GROUP BY COALESCE(p.clase, 'SIN-CLASE')
            ORDER BY valor DESC
            LIMIT :limit
        """
        res = self.db.execute(text(query), params).fetchall()
        return [{"categoria": str(r[0]), "valor": float(r[1] or 0)} for r in res]

    # ── Gráfico 1: serie diaria de salidas ──────────────────────────────────
    def get_salidas_serie_diaria(
        self, producto_cod: str | None, fecha_desde: str | None, fecha_hasta: str | None,
        sucursal: str | None = None, almacen: str | None = None,
        categoria: str | None = None, proveedor: str | None = None,
        top_n: int | None = None,
    ) -> list[dict[str, Any]]:
        """Serie diaria de unidades salidas. `producto_cod` restringe a un artículo;
        `top_n` restringe a los N artículos con más salida del rango (para "Top 10").

        Los JOIN a `dim_almacen`/`dim_sucursal` son condicionales: solo se agregan si el
        usuario realmente filtra por esa dimensión (`_filtros_snapshot` solo referencia
        los alias `al`/`su` en el WHERE cuando `almacen`/`sucursal` vienen seteados).
        Unirlos siempre -- aunque no filtren nada -- desvía al planner del índice parcial
        `idx_fmi_salidas_fecha_prod` (fecha_sk, producto_sk) WHERE es_salida hacia un Seq
        Scan completo de fact_movimientos_inventario (~950k filas): medido 63ms → 7ms al
        quitar los JOIN innecesarios en el caso sin filtro de almacén/sucursal (el caso
        del gráfico "Histórico y Predicción de Salidas" con "Top 10 productos")."""
        where_extra, params = self._filtros_snapshot(sucursal, almacen, categoria, proveedor, None)
        rango = self._rango_fechas(fecha_desde, fecha_hasta, params)
        # El JOIN a dim_almacen debe activarse también cuando hay una restricción de
        # seguridad por bodega (RN-B10), aunque el usuario no haya elegido `almacen`:
        # si se omite, el WHERE de _filtros_snapshot referenciaría un alias `al`
        # inexistente y la query fallaría.
        join_al = (
            "JOIN edw.dim_almacen  al ON {m}.almacen_sk = al.almacen_sk"
            if (almacen or self.almacenes_permitidos is not None) else ""
        )
        join_su = "JOIN edw.dim_sucursal su ON {m}.sucursal_sk = su.sucursal_sk" if sucursal else ""

        filtro_prod = ""
        if producto_cod:
            filtro_prod = "AND p.codart = :producto_cod"
            params["producto_cod"] = producto_cod
        filtro_top = ""
        if top_n and not producto_cod:
            filtro_top = f"""
                AND p.codart IN (
                    SELECT p2.codart
                    FROM edw.fact_movimientos_inventario m2
                    JOIN edw.dim_fecha d ON m2.fecha_sk = d.fecha_sk
                    JOIN edw.dim_producto p2 ON m2.producto_sk = p2.producto_sk
                    {join_al.format(m='m2')}
                    {join_su.format(m='m2')}
                    WHERE m2.es_salida {where_extra} {rango}
                    GROUP BY p2.codart
                    ORDER BY SUM(m2.cantidad_movimiento) DESC
                    LIMIT :top_n
                )
            """
            params["top_n"] = top_n

        query = f"""
            SELECT d.fecha_completa AS fecha, SUM(m.cantidad_movimiento) AS unidades
            FROM edw.fact_movimientos_inventario m
            JOIN edw.dim_fecha d ON m.fecha_sk = d.fecha_sk
            JOIN edw.dim_producto p ON m.producto_sk = p.producto_sk
            {join_al.format(m='m')}
            {join_su.format(m='m')}
            WHERE m.es_salida {where_extra} {rango} {filtro_prod} {filtro_top}
            GROUP BY d.fecha_completa
            ORDER BY d.fecha_completa
        """
        res = self.db.execute(text(query), params).fetchall()
        return [{"fecha": str(r[0]), "unidades": float(r[1] or 0)} for r in res]

    # ── Gráfico 2: rotación × margen por producto ───────────────────────────
    def get_rotacion_productos(
        self, fecha_desde: str | None, fecha_hasta: str | None,
        sucursal: str | None = None, almacen: str | None = None,
        categoria: str | None = None, proveedor: str | None = None,
        tipo_movimiento: str | None = None, limit: int = 200,
    ) -> list[dict[str, Any]]:
        """Por producto: costo de ventas y margen del período (fact_ventas_detalle) +
        stock/valor del último snapshot. El servicio calcula rotación y cuadrantes."""
        where_extra, params = self._filtros_snapshot(sucursal, almacen, categoria, proveedor, tipo_movimiento)
        rango = self._rango_fechas(fecha_desde, fecha_hasta, params)
        params["limit"] = limit

        query = f"""
            WITH ultimo AS (SELECT MAX(fecha_sk) AS fecha_sk FROM edw.fact_inventario_snapshot),
            ventas AS (
                SELECT p.codart,
                       MAX(p.nombre_articulo)             AS nombre_articulo,
                       MAX(COALESCE(p.clase, 'SIN-CLASE')) AS categoria,
                       SUM(f.cantidad)                    AS unidades_vendidas,
                       SUM(f.costo_total)                 AS costo_ventas,
                       SUM(f.margen_bruto)                AS margen_total
                FROM edw.fact_ventas_detalle f
                JOIN edw.dim_fecha d ON f.fecha_sk = d.fecha_sk
                JOIN edw.dim_producto p ON f.producto_sk = p.producto_sk
                JOIN edw.dim_almacen  al ON f.almacen_sk = al.almacen_sk
                JOIN edw.dim_sucursal su ON f.sucursal_sk = su.sucursal_sk
                JOIN edw.dim_estado_documento ed ON f.estado_documento_sk = ed.estado_documento_sk
                WHERE ed.estado_documento_sk <> -1 AND p.es_servicio = FALSE {where_extra} {rango}
                GROUP BY p.codart
            ),
            snap AS (
                SELECT p.codart,
                       SUM(s.stock_actual)     AS stock_actual,
                       SUM(s.valor_inventario) AS valor_inventario
                FROM edw.fact_inventario_snapshot s
                JOIN ultimo u ON s.fecha_sk = u.fecha_sk
                JOIN edw.dim_producto p ON s.producto_sk = p.producto_sk
                JOIN edw.dim_almacen  al ON s.almacen_sk = al.almacen_sk
                JOIN edw.dim_sucursal su ON s.sucursal_sk = su.sucursal_sk
                WHERE p.producto_sk <> -1 {where_extra}
                GROUP BY p.codart
            )
            SELECT v.codart, v.nombre_articulo, v.categoria, v.unidades_vendidas,
                   v.costo_ventas, v.margen_total,
                   COALESCE(sn.stock_actual, 0), COALESCE(sn.valor_inventario, 0)
            FROM ventas v
            LEFT JOIN snap sn ON sn.codart = v.codart
            ORDER BY v.costo_ventas DESC NULLS LAST
            LIMIT :limit
        """
        res = self.db.execute(text(query), params).fetchall()
        return [
            {
                "codart": str(r[0]),
                "nombre": str(r[1]),
                "categoria": str(r[2]),
                "unidades_vendidas": float(r[3] or 0),
                "costo_ventas": float(r[4] or 0),
                "margen_total": float(r[5] or 0),
                "stock_actual": float(r[6] or 0),
                "valor_inventario": float(r[7] or 0),
            }
            for r in res
        ]

    # ── Gráficos 3 y 4: top salidas y distribución por categoría ───────────
    def get_salidas_por_producto(
        self, fecha_desde: str | None, fecha_hasta: str | None,
        fecha_desde_prev: str | None, fecha_hasta_prev: str | None,
        sucursal: str | None = None, almacen: str | None = None,
        categoria: str | None = None, proveedor: str | None = None,
        tipo_movimiento: str | None = None, limit: int = 20,
    ) -> list[dict[str, Any]]:
        """Top N productos por unidades salidas en el rango, con el rango previo
        (tendencia §1.3-G3) y stock del último snapshot."""
        where_extra, params = self._filtros_snapshot(sucursal, almacen, categoria, proveedor, tipo_movimiento)
        rango = self._rango_fechas(fecha_desde, fecha_hasta, params)
        params["limit"] = limit
        # Rango previo con parámetros propios (mismos filtros dimensionales).
        prev_params: dict[str, Any] = {}
        rango_prev = self._rango_fechas(fecha_desde_prev, fecha_hasta_prev, prev_params)
        params.update({f"prev_{k}": v for k, v in prev_params.items()})
        rango_prev = rango_prev.replace(":fecha_desde", ":prev_fecha_desde").replace(":fecha_hasta", ":prev_fecha_hasta")

        query = f"""
            WITH ultimo AS (SELECT MAX(fecha_sk) AS fecha_sk FROM edw.fact_inventario_snapshot),
            actual AS (
                SELECT p.codart, MAX(p.nombre_articulo) AS nombre,
                       MAX(COALESCE(p.clase, 'SIN-CLASE')) AS categoria,
                       SUM(m.cantidad_movimiento) AS unidades,
                       -- RN-B8 (docs/auditoria/32_...md H32-1): valor_venta/costo_total ya
                       -- vienen a nivel de movimiento (kardex.totven/costot) -- el servicio
                       -- decide cuál exponer según TIPOS_MOVIMIENTO_CON_MONTO y el filtro activo.
                       SUM(m.valor_venta) AS monto_venta,
                       SUM(m.costo_total) AS monto_compra
                FROM edw.fact_movimientos_inventario m
                JOIN edw.dim_fecha d ON m.fecha_sk = d.fecha_sk
                JOIN edw.dim_producto p ON m.producto_sk = p.producto_sk
                JOIN edw.dim_almacen  al ON m.almacen_sk = al.almacen_sk
                JOIN edw.dim_sucursal su ON m.sucursal_sk = su.sucursal_sk
                WHERE m.es_salida {where_extra} {rango}
                GROUP BY p.codart
            ),
            previo AS (
                SELECT p.codart, SUM(m.cantidad_movimiento) AS unidades
                FROM edw.fact_movimientos_inventario m
                JOIN edw.dim_fecha d ON m.fecha_sk = d.fecha_sk
                JOIN edw.dim_producto p ON m.producto_sk = p.producto_sk
                JOIN edw.dim_almacen  al ON m.almacen_sk = al.almacen_sk
                JOIN edw.dim_sucursal su ON m.sucursal_sk = su.sucursal_sk
                WHERE m.es_salida {where_extra} {rango_prev}
                GROUP BY p.codart
            ),
            snap AS (
                SELECT p.codart, SUM(s.stock_actual) AS stock_actual
                FROM edw.fact_inventario_snapshot s
                JOIN ultimo u ON s.fecha_sk = u.fecha_sk
                JOIN edw.dim_producto p ON s.producto_sk = p.producto_sk
                JOIN edw.dim_almacen  al ON s.almacen_sk = al.almacen_sk
                JOIN edw.dim_sucursal su ON s.sucursal_sk = su.sucursal_sk
                WHERE p.producto_sk <> -1 {where_extra}
                GROUP BY p.codart
            )
            SELECT a.codart, a.nombre, a.categoria, a.unidades,
                   COALESCE(pr.unidades, 0) AS unidades_previo,
                   COALESCE(sn.stock_actual, 0) AS stock_actual,
                   a.monto_venta, a.monto_compra
            FROM actual a
            LEFT JOIN previo pr ON pr.codart = a.codart
            LEFT JOIN snap   sn ON sn.codart = a.codart
            ORDER BY a.unidades DESC
            LIMIT :limit
        """
        res = self.db.execute(text(query), params).fetchall()
        return [
            {
                "codart": str(r[0]),
                "nombre": str(r[1]),
                "categoria": str(r[2]),
                "unidades": float(r[3] or 0),
                "unidades_previo": float(r[4] or 0),
                "stock_actual": float(r[5] or 0),
                "monto_venta": float(r[6]) if r[6] is not None else None,
                "monto_compra": float(r[7]) if r[7] is not None else None,
            }
            for r in res
        ]

    def get_salidas_por_categoria(
        self, fecha_desde: str | None, fecha_hasta: str | None,
        fecha_desde_prev: str | None, fecha_hasta_prev: str | None,
        sucursal: str | None = None, almacen: str | None = None,
        proveedor: str | None = None, tipo_movimiento: str | None = None,
    ) -> list[dict[str, Any]]:
        where_extra, params = self._filtros_snapshot(sucursal, almacen, None, proveedor, tipo_movimiento)
        rango = self._rango_fechas(fecha_desde, fecha_hasta, params)
        prev_params: dict[str, Any] = {}
        rango_prev = self._rango_fechas(fecha_desde_prev, fecha_hasta_prev, prev_params)
        params.update({f"prev_{k}": v for k, v in prev_params.items()})
        rango_prev = rango_prev.replace(":fecha_desde", ":prev_fecha_desde").replace(":fecha_hasta", ":prev_fecha_hasta")

        query = f"""
            WITH ultimo AS (SELECT MAX(fecha_sk) AS fecha_sk FROM edw.fact_inventario_snapshot),
            actual AS (
                SELECT COALESCE(p.clase, 'SIN-CLASE') AS categoria, SUM(m.cantidad_movimiento) AS unidades,
                       SUM(m.valor_venta) AS monto_venta, SUM(m.costo_total) AS monto_compra
                FROM edw.fact_movimientos_inventario m
                JOIN edw.dim_fecha d ON m.fecha_sk = d.fecha_sk
                JOIN edw.dim_producto p ON m.producto_sk = p.producto_sk
                JOIN edw.dim_almacen  al ON m.almacen_sk = al.almacen_sk
                JOIN edw.dim_sucursal su ON m.sucursal_sk = su.sucursal_sk
                WHERE m.es_salida {where_extra} {rango}
                GROUP BY COALESCE(p.clase, 'SIN-CLASE')
            ),
            previo AS (
                SELECT COALESCE(p.clase, 'SIN-CLASE') AS categoria, SUM(m.cantidad_movimiento) AS unidades
                FROM edw.fact_movimientos_inventario m
                JOIN edw.dim_fecha d ON m.fecha_sk = d.fecha_sk
                JOIN edw.dim_producto p ON m.producto_sk = p.producto_sk
                JOIN edw.dim_almacen  al ON m.almacen_sk = al.almacen_sk
                JOIN edw.dim_sucursal su ON m.sucursal_sk = su.sucursal_sk
                WHERE m.es_salida {where_extra} {rango_prev}
                GROUP BY COALESCE(p.clase, 'SIN-CLASE')
            ),
            stock AS (
                SELECT COALESCE(p.clase, 'SIN-CLASE') AS categoria, SUM(s.stock_actual) AS stock
                FROM edw.fact_inventario_snapshot s
                JOIN ultimo u ON s.fecha_sk = u.fecha_sk
                JOIN edw.dim_producto p ON s.producto_sk = p.producto_sk
                JOIN edw.dim_almacen  al ON s.almacen_sk = al.almacen_sk
                JOIN edw.dim_sucursal su ON s.sucursal_sk = su.sucursal_sk
                WHERE p.producto_sk <> -1 {where_extra}
                GROUP BY COALESCE(p.clase, 'SIN-CLASE')
            )
            SELECT a.categoria, a.unidades, COALESCE(pr.unidades, 0), COALESCE(st.stock, 0),
                   a.monto_venta, a.monto_compra
            FROM actual a
            LEFT JOIN previo pr ON pr.categoria = a.categoria
            LEFT JOIN stock  st ON st.categoria = a.categoria
            ORDER BY a.unidades DESC
        """
        res = self.db.execute(text(query), params).fetchall()
        return [
            {
                "categoria": str(r[0]),
                "unidades": float(r[1] or 0),
                "unidades_previo": float(r[2] or 0),
                "stock_disponible": float(r[3] or 0),
                "monto_venta": float(r[4]) if r[4] is not None else None,
                "monto_compra": float(r[5]) if r[5] is not None else None,
            }
            for r in res
        ]

    # ── Panel §3: stock por producto × almacén (matriz y transferencias) ───
    def get_stock_por_almacen(
        self, sucursal: str | None = None, categoria: str | None = None,
        proveedor: str | None = None, tipo_movimiento: str | None = None,
        almacen: str | None = None, dias_salidas: int = 30, limit: int = 500,
        dias_ventana_inmovilizado: int = settings.BODEGA_DIAS_VENTANA_INMOVILIZADO,
    ) -> list[dict[str, Any]]:
        """Una fila por (codart, almacén) con stock del último snapshot y salidas de los
        últimos `dias_salidas` días EN ESE almacén — insumo de la matriz §3.1 y de la
        lógica de transferencias RN-B3 (excedente/déficit por bodega). `almacen` es
        opcional: la matriz de §3.1 lo usa para restringir a una sola bodega cuando el
        usuario filtra por almacén; las transferencias (§3.2) lo dejan en None porque
        necesitan comparar TODAS las bodegas entre sí (origen/destino). También trae
        `salidas_ventana_inmovilizado` (Fase 6.1, H-2) para que la matriz clasifique
        "Inmovilizado" igual que `get_inventario_productos`."""
        where_extra, params = self._filtros_snapshot(sucursal, almacen, categoria, proveedor, tipo_movimiento)
        params["dias"] = dias_salidas
        params["dias_inmov"] = dias_ventana_inmovilizado
        params["limit"] = limit

        query = f"""
            WITH ultimo AS (SELECT MAX(fecha_sk) AS fecha_sk FROM edw.fact_inventario_snapshot),
            snap AS (
                SELECT p.codart,
                       MAX(p.nombre_articulo) AS nombre,
                       MAX(COALESCE(p.clase, 'SIN-CLASE')) AS categoria,
                       al.nombre_almacen,
                       SUM(s.stock_actual)   AS stock_actual,
                       MAX(s.costo_promedio) AS costo_unitario,
                       SUM(s.punto_reorden)  AS punto_reorden_config
                FROM edw.fact_inventario_snapshot s
                JOIN ultimo u ON s.fecha_sk = u.fecha_sk
                JOIN edw.dim_producto p ON s.producto_sk = p.producto_sk
                JOIN edw.dim_almacen  al ON s.almacen_sk = al.almacen_sk
                JOIN edw.dim_sucursal su ON s.sucursal_sk = su.sucursal_sk
                WHERE p.producto_sk <> -1 AND al.almacen_sk <> -1 {where_extra}
                GROUP BY p.codart, al.nombre_almacen
            ),
            salidas AS (
                SELECT p.codart, al.nombre_almacen,
                       SUM(m.cantidad_movimiento) FILTER (
                           WHERE d.fecha_completa >= CURRENT_DATE - (:dias * INTERVAL '1 day')
                       ) AS salidas,
                       SUM(m.cantidad_movimiento) FILTER (
                           WHERE d.fecha_completa >= CURRENT_DATE - (:dias_inmov * INTERVAL '1 day')
                       ) AS salidas_ventana_inmovilizado
                FROM edw.fact_movimientos_inventario m
                JOIN edw.dim_fecha d ON m.fecha_sk = d.fecha_sk
                JOIN edw.dim_producto p ON m.producto_sk = p.producto_sk
                JOIN edw.dim_almacen  al ON m.almacen_sk = al.almacen_sk
                JOIN edw.dim_sucursal su ON m.sucursal_sk = su.sucursal_sk
                WHERE m.es_salida
                  AND d.fecha_completa >= CURRENT_DATE - (GREATEST(:dias, :dias_inmov) * INTERVAL '1 day')
                  {where_extra}
                GROUP BY p.codart, al.nombre_almacen
            ),
            relevantes AS (
                -- Corta la matriz a los artículos con actividad o stock (evita
                -- devolver decenas de miles de SKUs muertos, ~948k movimientos).
                SELECT codart FROM snap GROUP BY codart
                ORDER BY SUM(stock_actual * costo_unitario) DESC
                LIMIT :limit
            )
            SELECT sn.codart, sn.nombre, sn.categoria, sn.nombre_almacen,
                   sn.stock_actual, sn.costo_unitario, sn.punto_reorden_config,
                   COALESCE(sa.salidas, 0) AS salidas_periodo,
                   COALESCE(sa.salidas_ventana_inmovilizado, 0) AS salidas_ventana_inmovilizado
            FROM snap sn
            JOIN relevantes r ON r.codart = sn.codart
            LEFT JOIN salidas sa ON sa.codart = sn.codart AND sa.nombre_almacen = sn.nombre_almacen
            ORDER BY sn.codart, sn.nombre_almacen
        """
        res = self.db.execute(text(query), params).fetchall()
        return [
            {
                "codart": str(r[0]),
                "nombre": str(r[1]),
                "categoria": str(r[2]),
                "almacen": str(r[3]),
                "stock_actual": float(r[4] or 0),
                "costo_unitario": float(r[5] or 0),
                "punto_reorden_config": float(r[6] or 0),
                "salidas_periodo": float(r[7] or 0),
                "salidas_ventana_inmovilizado": float(r[8] or 0),
            }
            for r in res
        ]

    # ── RN-B9: justificación estadística de transferencias ─────────────────
    def get_series_salidas_producto_almacen(self, codarts: list[str], dias: int = 180) -> list[dict[str, Any]]:
        """Serie diaria de salidas (unidades + venta FAC) por (codart, almacén) para los
        últimos `dias` días, restringida a los `codarts` candidatos (los que ya tienen
        stock en 2+ bodegas, ver `_transferencias_completo`) -- una sola query batch en
        vez de N+1 por par origen/destino. El servicio rellena los días sin movimiento
        con 0 (pandas) para que el coeficiente de variación de RN-B9 sea representativo
        de la demanda real, no solo de los días con actividad."""
        if not codarts:
            return []
        params: dict[str, Any] = {"codarts": codarts, "dias": dias}
        # RN-B10: mismo criterio de restricción que _filtros_snapshot -- un usuario
        # bodega no debe recibir series de salida de almacenes fuera de su asignación,
        # aunque este método no pase por el choke point (no filtra por sucursal/almacen
        # elegido, compara TODAS las bodegas entre sí para las transferencias sugeridas).
        restriccion = ""
        if self.almacenes_permitidos is not None:
            if not self.almacenes_permitidos:
                restriccion = "AND 1 = 0"
            else:
                placeholders_alm = ", ".join(
                    f":alm_perm_{i}" for i in range(len(self.almacenes_permitidos))
                )
                for i, codalm in enumerate(self.almacenes_permitidos):
                    params[f"alm_perm_{i}"] = codalm
                restriccion = f"AND al.codalm IN ({placeholders_alm})"
        query = f"""
            SELECT p.codart, al.nombre_almacen AS almacen, d.fecha_completa AS fecha,
                   SUM(m.cantidad_movimiento) AS unidades,
                   SUM(m.valor_venta) FILTER (WHERE m.tipo_movimiento = 'FAC') AS venta
            FROM edw.fact_movimientos_inventario m
            JOIN edw.dim_fecha d ON m.fecha_sk = d.fecha_sk
            JOIN edw.dim_producto p ON m.producto_sk = p.producto_sk
            JOIN edw.dim_almacen  al ON m.almacen_sk = al.almacen_sk
            WHERE m.es_salida
              AND p.codart = ANY(:codarts)
              AND d.fecha_completa >= CURRENT_DATE - (:dias * INTERVAL '1 day')
              {restriccion}
            GROUP BY p.codart, al.nombre_almacen, d.fecha_completa
        """
        res = self.db.execute(text(query), params).fetchall()
        return [
            {
                "codart": str(r[0]),
                "almacen": str(r[1]),
                "fecha": str(r[2]),
                "unidades": float(r[3] or 0),
                "venta": float(r[4] or 0),
            }
            for r in res
        ]
