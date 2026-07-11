# backend/app/repositories/goal_repository.py
"""Acceso a datos de metas comerciales: histórico de ventas para el cálculo de
propuestas (edw.*, solo lectura) y CRUD de `public.metas_comerciales_operativas`
(ORM vía el modelo `Goal`, lectura/escritura normal)."""
import datetime
from typing import NamedTuple

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.models.goal import Goal


class VendorMonthlySales(NamedTuple):
    """Un mes de histórico agregado de un vendedor -- insumo de
    `app.services.goal_calculation_engine.RegistroMensual` (integración ML, Metas y
    Comisiones). `ventas` es **Venta Neta** (ventas - devoluciones del período), no venta
    bruta -- ver `GoalRepository.get_vendor_monthly_history`."""
    anio: int
    mes: int
    ventas: float
    unidades: float


class VendorTransactionFeatures(NamedTuple):
    """Mismas 4 columnas que `ml/contracts/models/anomalies.json` (ver también
    `PredictionRepository.get_transaction_features`), etiquetadas con anio/mes -- se usa
    para detectar MESES con transacciones anómalas, no para correr el modelo de
    anomalías sobre agregados mensuales (el contrato del modelo exige el grano de línea
    de transacción, no el de mes)."""
    anio: int
    mes: int
    subtotal_neto: float
    cantidad: float
    costo_total: float
    margen: float


class VendorRecentSales(NamedTuple):
    """Un vendedor con actividad en el mes anterior al objetivo -- insumo mínimo de
    `GoalMLService.generate_proposals` para saber a quién generarle una meta y cuántas
    unidades vendió el mes anterior (`unidades_meta` se deriva de eso). El monto de la
    meta en sí lo calcula `IQRGoalCalculationEngine` sobre el histórico completo
    (`GoalRepository.get_vendor_monthly_history`), no esta consulta."""
    vendedor_origen: str
    unidades_anterior: float


class GoalRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_vendors_with_recent_sales(self, anio: int, mes: int) -> list[VendorRecentSales]:
        """Vendedores (grano vendedor, NO vendedor×sucursal -- `edw.dim_vendedor` no tiene
        sucursal propia, ver docs/auditoria/19_...md) con ventas en el mes anterior al
        `anio`/`mes` objetivo, y sus unidades vendidas ese mes."""
        mes_ant = 12 if mes == 1 else mes - 1
        anio_ant = anio - 1 if mes == 1 else anio

        query = text("""
            SELECT v.codven AS vendedor_origen, SUM(f.cantidad) AS unidades_anterior
            FROM edw.fact_ventas_detalle f
            JOIN edw.dim_fecha d ON f.fecha_sk = d.fecha_sk
            JOIN edw.dim_vendedor v ON f.vendedor_sk = v.vendedor_sk
            JOIN edw.dim_estado_documento ed ON f.estado_documento_sk = ed.estado_documento_sk
            WHERE ed.estado_documento_sk <> -1 AND d.anio = :anio_ant AND d.mes = :mes_ant
            GROUP BY v.codven
        """)
        rows = self.db.execute(query, {"anio_ant": anio_ant, "mes_ant": mes_ant}).fetchall()
        return [VendorRecentSales(vendedor_origen=str(r[0]), unidades_anterior=float(r[1] or 0.0)) for r in rows]

    def find_proposal(self, anio: int, mes: int, vendedor: str) -> tuple[int, str] | None:
        row = self.db.execute(
            text("""
                SELECT id, estado FROM public.metas_comerciales_operativas
                WHERE anio = :anio AND mes = :mes AND id_vendedor_origen = :vendedor
            """),
            {"anio": anio, "mes": mes, "vendedor": vendedor},
        ).fetchone()
        return (row[0], row[1]) if row else None

    def insert_proposal(self, anio: int, mes: int, vendedor: str, monto_meta: float, unidades_meta: float) -> None:
        self.db.execute(
            text("""
                INSERT INTO public.metas_comerciales_operativas
                (anio, mes, id_vendedor_origen, monto_meta, unidades_meta, estado, comision_base_pct, bono_sobrecumplimiento)
                VALUES (:anio, :mes, :vendedor, :meta_monto, :meta_unidades, 'PROPUESTA', 0.0, 0.0)
            """),
            {"anio": anio, "mes": mes, "vendedor": vendedor,
             "meta_monto": monto_meta, "meta_unidades": unidades_meta},
        )

    def update_proposal_amounts(self, proposal_id: int, monto_meta: float, unidades_meta: float) -> None:
        self.db.execute(
            text("""
                UPDATE public.metas_comerciales_operativas
                SET monto_meta = :meta_monto, unidades_meta = :meta_unidades
                WHERE id = :id
            """),
            {"meta_monto": monto_meta, "meta_unidades": unidades_meta, "id": proposal_id},
        )

    def commit(self) -> None:
        self.db.commit()

    def rollback(self) -> None:
        self.db.rollback()

    def get_periods_with_data(self) -> list[dict[str, int]]:
        rows = self.db.execute(text("""
            SELECT DISTINCT anio, mes FROM public.metas_comerciales_operativas
            ORDER BY anio DESC, mes DESC
        """)).fetchall()
        return [{"anio": row[0], "mes": row[1]} for row in rows]

    def get_latest_edw_period(self) -> tuple[int, int] | None:
        row = self.db.execute(text("""
            SELECT MAX(d.anio) as max_anio, MAX(d.mes) as max_mes
            FROM edw.fact_ventas_detalle f
            JOIN edw.dim_fecha d ON f.fecha_sk = d.fecha_sk
            WHERE d.anio = (
                SELECT MAX(d2.anio) FROM edw.fact_ventas_detalle f2 JOIN edw.dim_fecha d2 ON f2.fecha_sk = d2.fecha_sk
            )
        """)).fetchone()
        if row and row[0]:
            return int(row[0]), int(row[1])
        return None

    def get_commission_report(self, anio: int, mes: int) -> list[dict]:
        rows = self.db.execute(
            text("""
                SELECT
                    MAX(v.nombre_vendedor) AS vendedor, m.monto_meta AS meta_monto,
                    m.comision_base_pct, m.bono_sobrecumplimiento, m.id AS id_meta, m.estado
                FROM public.metas_comerciales_operativas m
                LEFT JOIN edw.dim_vendedor v ON m.id_vendedor_origen = v.codven
                WHERE m.anio = :anio AND m.mes = :mes
                GROUP BY m.id, m.monto_meta, m.comision_base_pct, m.bono_sobrecumplimiento, m.estado
                ORDER BY MAX(v.nombre_vendedor) ASC
            """),
            {"anio": anio, "mes": mes},
        ).fetchall()
        return [
            {
                "id": int(row[4]), "vendedor": str(row[0]),
                "monto_meta": float(row[1]), "comision_base_pct": float(row[2]), "estado": str(row[5]),
            }
            for row in rows
        ]

    # ── Liquidación de comisiones (docs/modulo_metas.md, docs/auditoria/17_/19_...) ────
    def get_commission_tracking_rows(self, anio: int, mes: int) -> list[dict]:
        """Una fila por meta configurada en el período (grano vendedor, ver
        docs/auditoria/19_...md), con su **Venta Neta** real (ventas - devoluciones de
        TODAS las sucursales del vendedor) ya resuelta -- a diferencia de
        `get_commission_report` (que solo trae la meta configurada, sin venta real), esta
        consulta es la que cierra el hallazgo R-1 de `docs/auditoria/14_...md`:
        cumplimiento real, no solo la meta. El cálculo de comisión (tramos, tasa, bono) es
        responsabilidad del servicio (`commission_engine.calcular_comision`), no de esta
        consulta."""
        query = text("""
            WITH VentasBrutas AS (
                SELECT v.codven AS vendedor_origen, SUM(f.subtotal_neto) AS ventas_brutas
                FROM edw.fact_ventas_detalle f
                JOIN edw.dim_fecha d ON f.fecha_sk = d.fecha_sk
                JOIN edw.dim_vendedor v ON f.vendedor_sk = v.vendedor_sk
                JOIN edw.dim_estado_documento ed ON f.estado_documento_sk = ed.estado_documento_sk
                WHERE ed.estado_documento_sk <> -1 AND d.anio = :anio AND d.mes = :mes
                GROUP BY v.codven
            ),
            Devoluciones AS (
                SELECT v.codven AS vendedor_origen, SUM(fd.total_linea_devolucion) AS devoluciones
                FROM edw.fact_devoluciones fd
                JOIN edw.dim_fecha d ON fd.fecha_sk = d.fecha_sk
                JOIN edw.dim_vendedor v ON fd.vendedor_sk = v.vendedor_sk
                WHERE d.anio = :anio AND d.mes = :mes
                GROUP BY v.codven
            )
            SELECT
                m.id, m.id_vendedor_origen,
                COALESCE(MAX(v.nombre_vendedor), m.id_vendedor_origen, 'Sin vendedor') AS vendedor,
                m.monto_meta, m.comision_base_pct, m.bono_sobrecumplimiento, m.estado,
                COALESCE(MAX(vb.ventas_brutas), 0.0) - COALESCE(MAX(dv.devoluciones), 0.0) AS venta_neta
            FROM public.metas_comerciales_operativas m
            LEFT JOIN edw.dim_vendedor v ON m.id_vendedor_origen = v.codven
            LEFT JOIN VentasBrutas vb ON m.id_vendedor_origen = vb.vendedor_origen
            LEFT JOIN Devoluciones dv ON m.id_vendedor_origen = dv.vendedor_origen
            WHERE m.anio = :anio AND m.mes = :mes
            GROUP BY m.id, m.id_vendedor_origen, m.monto_meta, m.comision_base_pct,
                     m.bono_sobrecumplimiento, m.estado
            ORDER BY vendedor ASC
        """)
        rows = self.db.execute(query, {"anio": anio, "mes": mes}).fetchall()
        return [
            {
                "id": int(r[0]), "id_vendedor_origen": r[1], "vendedor": str(r[2]),
                "monto_meta": float(r[3]), "comision_base_pct": float(r[4]), "bono_sobrecumplimiento": float(r[5]),
                "estado": str(r[6]), "venta_neta": float(r[7]),
            }
            for r in rows
        ]

    def get_vendor_net_sales_period(self, vendedor_origen: str, anio: int, mes: int) -> float:
        """Venta Neta (ventas - devoluciones, de TODAS las sucursales del vendedor) en un
        período específico -- usado por el panel del vendedor
        (`CommissionService.get_my_commission`), a diferencia de
        `get_vendor_monthly_history` que trae una serie de varios meses."""
        query = text("""
            WITH VentasBrutas AS (
                SELECT COALESCE(SUM(f.subtotal_neto), 0.0) AS ventas_brutas
                FROM edw.fact_ventas_detalle f
                JOIN edw.dim_fecha d ON f.fecha_sk = d.fecha_sk
                JOIN edw.dim_vendedor v ON f.vendedor_sk = v.vendedor_sk
                JOIN edw.dim_estado_documento ed ON f.estado_documento_sk = ed.estado_documento_sk
                WHERE ed.estado_documento_sk <> -1
                  AND v.codven = :vendedor AND d.anio = :anio AND d.mes = :mes
            ),
            Devoluciones AS (
                SELECT COALESCE(SUM(fd.total_linea_devolucion), 0.0) AS devoluciones
                FROM edw.fact_devoluciones fd
                JOIN edw.dim_fecha d ON fd.fecha_sk = d.fecha_sk
                JOIN edw.dim_vendedor v ON fd.vendedor_sk = v.vendedor_sk
                WHERE v.codven = :vendedor AND d.anio = :anio AND d.mes = :mes
            )
            SELECT (SELECT ventas_brutas FROM VentasBrutas) - (SELECT devoluciones FROM Devoluciones)
        """)
        row = self.db.execute(query, {"vendedor": vendedor_origen, "anio": anio, "mes": mes}).fetchone()
        return float(row[0]) if row and row[0] is not None else 0.0

    def get_goal_for_period(self, vendedor_origen: str, anio: int, mes: int) -> Goal | None:
        return (
            self.db.query(Goal)
            .filter(
                Goal.id_vendedor_origen == vendedor_origen,
                Goal.anio == anio, Goal.mes == mes,
            )
            .first()
        )

    def get_post_goal_invoices(self, vendedor_origen: str, anio: int, mes: int, monto_meta: float) -> list[dict]:
        """Facturas del vendedor (todas sus sucursales) en el período, con Venta Neta
        acumulada (grano de factura, `SUM` por `num_factura` sobre `fact_ventas_detalle`),
        filtradas a las que quedan a partir del punto en que el acumulado cruza la meta --
        "qué está vendiendo después de llegar a la meta" (docs/modulo_metas.md, línea 5).
        Limitación documentada: el acumulado usa venta bruta por factura (no resta
        devoluciones factura por factura, ya que las notas de crédito no referencian
        `num_factura` en `fact_devoluciones`); es una aproximación razonable para
        identificar el punto de cruce, no para el monto exacto de comisión (ese cálculo
        sí usa Venta Neta real, ver `get_vendor_net_sales_period`)."""
        query = text("""
            WITH FacturaAgg AS (
                SELECT f.num_factura, MIN(d.fecha_completa) AS fecha, SUM(f.subtotal_neto) AS monto_factura
                FROM edw.fact_ventas_detalle f
                JOIN edw.dim_fecha d ON f.fecha_sk = d.fecha_sk
                JOIN edw.dim_vendedor v ON f.vendedor_sk = v.vendedor_sk
                JOIN edw.dim_estado_documento ed ON f.estado_documento_sk = ed.estado_documento_sk
                WHERE ed.estado_documento_sk <> -1
                  AND v.codven = :vendedor
                  AND d.anio = :anio AND d.mes = :mes
                GROUP BY f.num_factura
            ),
            Acumulado AS (
                SELECT num_factura, fecha, monto_factura,
                       SUM(monto_factura) OVER (ORDER BY fecha, num_factura) AS acumulado
                FROM FacturaAgg
            )
            SELECT num_factura, fecha, monto_factura, acumulado
            FROM Acumulado
            WHERE acumulado >= :monto_meta AND :monto_meta > 0
            ORDER BY fecha, num_factura
        """)
        rows = self.db.execute(query, {
            "vendedor": vendedor_origen, "anio": anio, "mes": mes, "monto_meta": monto_meta,
        }).fetchall()
        return [
            {
                "num_factura": str(r[0]), "fecha": r[1].isoformat() if hasattr(r[1], "isoformat") else str(r[1]),
                "monto_factura": float(r[2]), "acumulado_venta": float(r[3]),
            }
            for r in rows
        ]

    # ── Integración ML (Metas y Comisiones): histórico, anomalías, top productos ──
    def get_vendor_monthly_history(self, vendedor_origen: str, meses: int = 24) -> list[VendorMonthlySales]:
        """Serie mensual de **Venta Neta** de un vendedor (todas sus sucursales, ver
        docs/auditoria/19_...md) -- insumo del motor estadístico
        (`goal_calculation_engine.IQRGoalCalculationEngine`), que es el generador OFICIAL
        de la meta persistida (`GoalMLService.generate_proposals`, docs/auditoria/20_...md:
        sin ningún modelo ML, `goals_rf` fue decomisionado).

        Venta Neta = SUM(subtotal_neto) de `fact_ventas_detalle` - SUM(total_linea_devolucion)
        de `fact_devoluciones`, agregadas por separado al grano vendedor×mes y
        combinadas con `LEFT JOIN` (patrón de CTEs agregados: las dos facts tienen grano de
        línea distinto -- venta vs. nota de crédito -- así que nunca se JOINean directamente
        entre sí, eso multiplicaría filas). `fact_devoluciones` no tiene `estado_documento_sk`
        (no aplica el filtro de población de `dim_estado_documento`, solo existe en la fact de
        ventas)."""
        query = text("""
            WITH Ventas AS (
                SELECT d.anio, d.mes,
                       COALESCE(SUM(f.subtotal_neto), 0) AS ventas_brutas,
                       COALESCE(SUM(f.cantidad), 0) AS unidades
                FROM edw.fact_ventas_detalle f
                JOIN edw.dim_fecha d ON f.fecha_sk = d.fecha_sk
                JOIN edw.dim_vendedor v ON f.vendedor_sk = v.vendedor_sk
                JOIN edw.dim_estado_documento ed ON f.estado_documento_sk = ed.estado_documento_sk
                WHERE ed.estado_documento_sk <> -1
                  AND v.codven = :vendedor
                GROUP BY d.anio, d.mes
            ),
            Devoluciones AS (
                SELECT d.anio, d.mes,
                       COALESCE(SUM(fd.total_linea_devolucion), 0) AS devoluciones
                FROM edw.fact_devoluciones fd
                JOIN edw.dim_fecha d ON fd.fecha_sk = d.fecha_sk
                JOIN edw.dim_vendedor v ON fd.vendedor_sk = v.vendedor_sk
                WHERE v.codven = :vendedor
                GROUP BY d.anio, d.mes
            )
            SELECT ve.anio, ve.mes,
                   (ve.ventas_brutas - COALESCE(dv.devoluciones, 0)) AS venta_neta,
                   ve.unidades
            FROM Ventas ve
            LEFT JOIN Devoluciones dv ON ve.anio = dv.anio AND ve.mes = dv.mes
            ORDER BY ve.anio DESC, ve.mes DESC
            LIMIT :meses
        """)
        rows = self.db.execute(query, {"vendedor": vendedor_origen, "meses": meses}).fetchall()
        return [VendorMonthlySales(anio=int(r[0]), mes=int(r[1]), ventas=float(r[2]), unidades=float(r[3])) for r in rows]

    def get_vendor_transactions_history(self, vendedor_origen: str, anio_desde: int, mes_desde: int) -> list[VendorTransactionFeatures]:
        """Todas las líneas de transacción de un vendedor (todas sus sucursales) desde
        `(anio_desde, mes_desde)` en adelante, con las mismas 4 columnas y política de
        nulos que `ml/contracts/models/anomalies.json` (excluye `costo_total IS NULL`,
        H-19) -- en un solo batch, para correr `inference.detect_anomalies` una sola vez
        al grano correcto (línea de transacción, no agregado mensual) y luego agrupar
        por mes en el servicio."""
        query = text("""
            SELECT d.anio, d.mes, f.subtotal_neto, f.cantidad, f.costo_total, (f.subtotal_neto - f.costo_total) AS margen
            FROM edw.fact_ventas_detalle f
            JOIN edw.dim_fecha d ON f.fecha_sk = d.fecha_sk
            JOIN edw.dim_vendedor v ON f.vendedor_sk = v.vendedor_sk
            JOIN edw.dim_estado_documento ed ON f.estado_documento_sk = ed.estado_documento_sk
            WHERE ed.estado_documento_sk <> -1
              AND v.codven = :vendedor
              AND (d.anio, d.mes) >= (:anio_desde, :mes_desde)
              AND f.costo_total IS NOT NULL
        """)
        rows = self.db.execute(query, {
            "vendedor": vendedor_origen, "anio_desde": anio_desde, "mes_desde": mes_desde,
        }).fetchall()
        return [
            VendorTransactionFeatures(
                anio=int(r[0]), mes=int(r[1]), subtotal_neto=float(r[2]), cantidad=float(r[3]),
                costo_total=float(r[4]), margen=float(r[5]),
            )
            for r in rows
        ]

    def get_vendor_top_products(self, vendedor_origen: str, limit: int = 10) -> list[str]:
        """`codart` de los productos más vendidos (por monto) del vendedor -- insumo de
        `inference.get_recommendations` (item_history) para sugerir categorías/productos
        complementarios que ayuden a alcanzar la meta."""
        query = text("""
            SELECT p.codart
            FROM edw.fact_ventas_detalle f
            JOIN edw.dim_producto p ON f.producto_sk = p.producto_sk
            JOIN edw.dim_vendedor v ON f.vendedor_sk = v.vendedor_sk
            JOIN edw.dim_estado_documento ed ON f.estado_documento_sk = ed.estado_documento_sk
            WHERE ed.estado_documento_sk <> -1
              AND v.codven = :vendedor AND p.producto_sk <> -1
            GROUP BY p.codart
            ORDER BY SUM(f.subtotal_neto) DESC
            LIMIT :limit
        """)
        rows = self.db.execute(query, {"vendedor": vendedor_origen, "limit": limit}).fetchall()
        return [str(r[0]) for r in rows]

    def get_product_categories(self, codarts: list[str]) -> dict[str, str]:
        """`codart` -> `nombre_clase` (categoría) -- usado para agregar las reglas de
        recomendación por categoría en el panel gerencial (integración ML)."""
        if not codarts:
            return {}
        query = text("""
            SELECT codart, nombre_clase FROM edw.dim_producto
            WHERE codart = ANY(:codarts) AND es_vigente = true
        """)
        rows = self.db.execute(query, {"codarts": codarts}).fetchall()
        return {str(r[0]): (str(r[1]) if r[1] else "Sin categoría") for r in rows}

    # ── ORM: público.metas_comerciales_operativas vía modelo Goal ─────────────
    def get_by_id(self, goal_id: int) -> Goal | None:
        return self.db.query(Goal).filter(Goal.id == goal_id).first()

    def update_review(self, goal: Goal, estado: str, approved_by: int, monto_meta: float | None, comision_base_pct: float | None) -> Goal:
        if monto_meta is not None:
            goal.monto_meta = monto_meta
        if comision_base_pct is not None:
            goal.comision_base_pct = comision_base_pct
        goal.estado = estado
        goal.approved_by = approved_by
        self.db.commit()
        self.db.refresh(goal)
        return goal
