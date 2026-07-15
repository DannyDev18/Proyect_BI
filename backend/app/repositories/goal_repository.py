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


class CommissionLineRow(NamedTuple):
    """Una línea de venta a grano `fact_ventas_detalle` con las columnas mínimas del
    motor variable (`commission_engine.LineaComisionable`), ver
    docs/features/plan_integracion_comisiones_variables.md §3.3.

    `es_servicio` viene de `fact_ventas_detalle.es_linea_servicio` (grano línea, derivado
    de `renglonesfacturas.bienser` en el ETL), NO de `dim_producto.es_servicio` (grano
    producto): auditoría 34 (H-13) confirmó contra Producción que el flag del maestro de
    artículo (`articulos.bienser`) casi no se usa (1 fila en 'S' de 8.152), mientras que
    la línea de transacción sí tiene 58.407 líneas reales en 'S' -- usar el atributo de
    producto dejaba el grupo S del motor de comisiones variables sin datos reales."""
    codart: str
    clase: str
    subclase: str | None
    es_servicio: bool
    subtotal_neto: float
    margen_bruto: float | None
    valor_descuento: float
    dias_plazo: int


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

    def get_vendor_devoluciones_period(self, vendedor_origen: str, anio: int, mes: int) -> float:
        """Monto devuelto por el vendedor (todas sus sucursales) en el período -- insumo
        directo del motor variable (`devoluciones_mes`), separado de `get_vendor_net_sales_period`
        (que ya lo resta de la venta) porque el motor variable lo necesita como valor
        propio para estimar la comisión asociada a la devolución (§3.2 del plan)."""
        query = text("""
            SELECT COALESCE(SUM(fd.total_linea_devolucion), 0.0)
            FROM edw.fact_devoluciones fd
            JOIN edw.dim_fecha d ON fd.fecha_sk = d.fecha_sk
            JOIN edw.dim_vendedor v ON fd.vendedor_sk = v.vendedor_sk
            WHERE v.codven = :vendedor AND d.anio = :anio AND d.mes = :mes
        """)
        row = self.db.execute(query, {"vendedor": vendedor_origen, "anio": anio, "mes": mes}).fetchone()
        return float(row[0]) if row and row[0] is not None else 0.0

    def get_vendors_with_sales_in_period(self, anio: int, mes: int) -> list[str]:
        """Vendedores (código) con al menos una línea de venta válida en el período --
        usado por la simulación retroactiva para no iterar sobre todo `dim_vendedor`."""
        query = text("""
            SELECT DISTINCT v.codven
            FROM edw.fact_ventas_detalle f
            JOIN edw.dim_fecha d ON f.fecha_sk = d.fecha_sk
            JOIN edw.dim_vendedor v ON f.vendedor_sk = v.vendedor_sk
            JOIN edw.dim_estado_documento ed ON f.estado_documento_sk = ed.estado_documento_sk
            WHERE ed.estado_documento_sk <> -1 AND d.anio = :anio AND d.mes = :mes AND v.codven <> '-1'
        """)
        rows = self.db.execute(query, {"anio": anio, "mes": mes}).fetchall()
        return [str(r[0]) for r in rows]

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
        """`codart` -> `clase` (categoría) -- usado para agregar las reglas de
        recomendación por categoría en el panel gerencial (integración ML). RN-CM2
        (auditoría 30, H2): se usa el código `clase`, no `nombre_clase` -- 100% vacío en
        el catálogo vigente, mostraría "Sin categoría" para cada producto."""
        if not codarts:
            return {}
        query = text("""
            SELECT codart, clase FROM edw.dim_producto
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

    # ── Comisiones Variables (docs/features/plan_integracion_comisiones_variables.md,
    # docs/auditoria/30_comisiones_variables.md) ────────────────────────────────────
    def get_commission_lines(self, vendedor_origen: str, anio: int, mes: int) -> list[CommissionLineRow]:
        """Líneas de venta del vendedor (todas sus sucursales) en el período -- grano
        central del motor variable. RN-CM2 (auditoría 30, H2): se trae `clase`/`subclase`
        por código, `nombre_clase` está vacío en el 100% del catálogo vigente."""
        query = text("""
            SELECT p.codart, p.clase, p.subclase, f.es_linea_servicio,
                   f.subtotal_neto, f.margen_bruto, f.valor_descuento, fp.dias_plazo
            FROM edw.fact_ventas_detalle f
            JOIN edw.dim_fecha d ON f.fecha_sk = d.fecha_sk
            JOIN edw.dim_vendedor v ON f.vendedor_sk = v.vendedor_sk
            JOIN edw.dim_producto p ON f.producto_sk = p.producto_sk
            JOIN edw.dim_formapago fp ON f.formapago_sk = fp.formapago_sk
            JOIN edw.dim_estado_documento ed ON f.estado_documento_sk = ed.estado_documento_sk
            WHERE ed.estado_documento_sk <> -1
              AND v.codven = :vendedor AND d.anio = :anio AND d.mes = :mes
        """)
        rows = self.db.execute(query, {"vendedor": vendedor_origen, "anio": anio, "mes": mes}).fetchall()
        return [
            CommissionLineRow(
                codart=str(r[0]), clase=str(r[1] or "*"), subclase=(str(r[2]) if r[2] else None),
                es_servicio=bool(r[3]), subtotal_neto=float(r[4]),
                margen_bruto=(float(r[5]) if r[5] is not None else None),
                valor_descuento=float(r[6] or 0.0), dias_plazo=int(r[7] or 0),
            )
            for r in rows
        ]

    def get_margin_profile_by_category(self, meses: int = 24) -> list[dict]:
        """Perfil de margen por categoría (`clase`/`subclase`), agregado con
        SUM(margen)/SUM(venta) -- RN-CM3 (auditoría 30, H3): un AVG por línea se
        distorsiona por líneas de subtotal casi nulo (cortesías/redondeos). Insumo del
        clasificador automático A/B/C/S/X (Fase 1 del plan). `es_linea_servicio` viene de
        `fact_ventas_detalle` (grano línea, auditoría 34 H-13), no de `dim_producto.es_servicio`
        -- mismo motivo que `get_commission_lines`."""
        query = text("""
            WITH Periodo AS (
                SELECT MAX(d.anio) AS anio_max, MAX(d.mes) AS mes_max FROM edw.dim_fecha d
                JOIN edw.fact_ventas_detalle f ON f.fecha_sk = d.fecha_sk
            ),
            Corte AS (
                SELECT (anio_max * 12 + mes_max - :meses) AS mes_absoluto_desde FROM Periodo
            )
            SELECT p.clase, f.es_linea_servicio,
                   SUM(f.subtotal_neto) AS venta_total,
                   SUM(f.margen_bruto) AS margen_total,
                   COUNT(DISTINCT v.codven) AS num_vendedores,
                   COUNT(*) AS num_lineas,
                   COALESCE(SUM(f.valor_descuento) / NULLIF(SUM(f.subtotal_neto + f.valor_descuento), 0), 0) AS tasa_descuento_prom
            FROM edw.fact_ventas_detalle f
            JOIN edw.dim_fecha d ON f.fecha_sk = d.fecha_sk
            JOIN edw.dim_producto p ON f.producto_sk = p.producto_sk
            JOIN edw.dim_vendedor v ON f.vendedor_sk = v.vendedor_sk
            JOIN edw.dim_estado_documento ed ON f.estado_documento_sk = ed.estado_documento_sk
            CROSS JOIN Corte
            WHERE ed.estado_documento_sk <> -1
              AND (d.anio * 12 + d.mes) >= Corte.mes_absoluto_desde
            GROUP BY p.clase, f.es_linea_servicio
            ORDER BY venta_total DESC
        """)
        rows = self.db.execute(query, {"meses": meses}).fetchall()
        resultado = []
        for r in rows:
            venta_total = float(r[2] or 0.0)
            margen_total = float(r[3] or 0.0)
            resultado.append({
                "clase": str(r[0] or "(sin clase)"), "es_servicio": bool(r[1]),
                "venta_total": venta_total, "margen_total": margen_total,
                "margen_pct": round((margen_total / venta_total * 100), 2) if venta_total else 0.0,
                "num_vendedores": int(r[4]), "num_lineas": int(r[5]),
                "tasa_descuento_prom_pct": round(float(r[6] or 0.0) * 100, 2),
            })
        return resultado

    def get_lines_without_cost(self, anio: int, mes: int, limit: int = 200) -> list[dict]:
        """Salvaguarda 2: líneas del período sin costo registrado (`margen_bruto IS
        NULL`), para el reporte a gerencia (`/gerencia/goals/lineas-sin-costo`)."""
        query = text("""
            SELECT p.codart, v.codven, SUM(f.subtotal_neto) AS venta_afectada, COUNT(*) AS num_lineas
            FROM edw.fact_ventas_detalle f
            JOIN edw.dim_fecha d ON f.fecha_sk = d.fecha_sk
            JOIN edw.dim_producto p ON f.producto_sk = p.producto_sk
            JOIN edw.dim_vendedor v ON f.vendedor_sk = v.vendedor_sk
            JOIN edw.dim_estado_documento ed ON f.estado_documento_sk = ed.estado_documento_sk
            WHERE ed.estado_documento_sk <> -1 AND f.margen_bruto IS NULL
              AND d.anio = :anio AND d.mes = :mes
            GROUP BY p.codart, v.codven
            ORDER BY venta_afectada DESC
            LIMIT :limit
        """)
        rows = self.db.execute(query, {"anio": anio, "mes": mes, "limit": limit}).fetchall()
        return [
            {"codart": str(r[0]), "vendedor_origen": str(r[1]), "venta_afectada": float(r[2]), "num_lineas": int(r[3])}
            for r in rows
        ]

    def get_vendor_credit_profile(self, vendedor_origen: str, anio: int, mes: int) -> dict:
        """% de ventas a crédito, plazo promedio (`dim_formapago.dias_plazo`) y días de
        cobro promedio reales (`fact_cobros_cxc.dias_vencimiento`) del vendedor en el
        período -- insumo del Bono 3 (cobranza sana) y del análisis de Fase 1."""
        query = text("""
            WITH Ventas AS (
                SELECT
                    SUM(f.subtotal_neto) AS venta_total,
                    SUM(f.subtotal_neto) FILTER (WHERE fp.dias_plazo > 0) AS venta_credito,
                    AVG(fp.dias_plazo) FILTER (WHERE fp.dias_plazo > 0) AS plazo_promedio
                FROM edw.fact_ventas_detalle f
                JOIN edw.dim_fecha d ON f.fecha_sk = d.fecha_sk
                JOIN edw.dim_vendedor v ON f.vendedor_sk = v.vendedor_sk
                JOIN edw.dim_formapago fp ON f.formapago_sk = fp.formapago_sk
                JOIN edw.dim_estado_documento ed ON f.estado_documento_sk = ed.estado_documento_sk
                WHERE ed.estado_documento_sk <> -1
                  AND v.codven = :vendedor AND d.anio = :anio AND d.mes = :mes
            ),
            Cobros AS (
                SELECT AVG(cx.dias_vencimiento) AS dias_cobro_promedio
                FROM edw.fact_cobros_cxc cx
                JOIN edw.dim_fecha d ON cx.fecha_sk = d.fecha_sk
                JOIN edw.dim_vendedor v ON cx.vendedor_sk = v.vendedor_sk
                WHERE v.codven = :vendedor AND d.anio = :anio AND d.mes = :mes
            )
            SELECT
                COALESCE(Ventas.venta_total, 0), COALESCE(Ventas.venta_credito, 0),
                Ventas.plazo_promedio, Cobros.dias_cobro_promedio
            FROM Ventas CROSS JOIN Cobros
        """)
        row = self.db.execute(query, {"vendedor": vendedor_origen, "anio": anio, "mes": mes}).fetchone()
        if not row:
            return {"pct_venta_credito": 0.0, "plazo_promedio_dias": None, "dias_cobro_promedio": None}
        venta_total, venta_credito = float(row[0]), float(row[1])
        return {
            "pct_venta_credito": round((venta_credito / venta_total * 100), 2) if venta_total else 0.0,
            "plazo_promedio_dias": (round(float(row[2]), 1) if row[2] is not None else None),
            "dias_cobro_promedio": (round(float(row[3]), 1) if row[3] is not None else None),
        }

    def get_new_or_reactivated_clients(self, vendedor_origen: str, anio: int, mes: int, meses_inactividad: int) -> int:
        """№ de clientes que compraron al vendedor en el período y NO tenían compras
        (de ningún vendedor) en los `meses_inactividad` meses previos -- Bono 2 (cliente
        nuevo/reactivado)."""
        query = text("""
            WITH ClientesDelMes AS (
                SELECT DISTINCT f.cliente_sk
                FROM edw.fact_ventas_detalle f
                JOIN edw.dim_fecha d ON f.fecha_sk = d.fecha_sk
                JOIN edw.dim_vendedor v ON f.vendedor_sk = v.vendedor_sk
                JOIN edw.dim_estado_documento ed ON f.estado_documento_sk = ed.estado_documento_sk
                WHERE ed.estado_documento_sk <> -1
                  AND v.codven = :vendedor AND d.anio = :anio AND d.mes = :mes AND f.cliente_sk <> -1
            ),
            ClientesConHistorial AS (
                SELECT DISTINCT f.cliente_sk
                FROM edw.fact_ventas_detalle f
                JOIN edw.dim_fecha d ON f.fecha_sk = d.fecha_sk
                JOIN edw.dim_estado_documento ed ON f.estado_documento_sk = ed.estado_documento_sk
                WHERE ed.estado_documento_sk <> -1
                  AND f.cliente_sk IN (SELECT cliente_sk FROM ClientesDelMes)
                  AND (d.anio * 12 + d.mes) BETWEEN (:anio * 12 + :mes - :meses_inactividad) AND (:anio * 12 + :mes - 1)
            )
            SELECT COUNT(*) FROM ClientesDelMes
            WHERE cliente_sk NOT IN (SELECT cliente_sk FROM ClientesConHistorial)
        """)
        row = self.db.execute(query, {
            "vendedor": vendedor_origen, "anio": anio, "mes": mes, "meses_inactividad": meses_inactividad,
        }).fetchone()
        return int(row[0]) if row else 0

    def get_cross_sell_accepted_amount(self, vendedor_origen: str, anio: int, mes: int) -> float:
        """Monto de venta del período en productos que fueron sugeridos y ACEPTADOS por
        el asistente de venta cruzada (`public.recomendaciones_eventos`, evento
        `aceptada`) para este vendedor -- Bono 1. Aproximación documentada: la telemetría
        no referencia la línea de venta exacta, así que se suma la venta real del período
        en los `codart` sugeridos-aceptados por usuarios ligados a este vendedor
        (`public.usuarios.id_vendedor_origen`)."""
        query = text("""
            WITH ProductosAceptados AS (
                SELECT DISTINCT re.producto_sugerido_cod
                FROM public.recomendaciones_eventos re
                JOIN public.usuarios u ON re.usuario_id = u.id
                WHERE u.id_vendedor_origen = :vendedor
                  AND re.evento = 'aceptada'
                  AND EXTRACT(YEAR FROM re.fecha) = :anio AND EXTRACT(MONTH FROM re.fecha) = :mes
            )
            SELECT COALESCE(SUM(f.subtotal_neto), 0)
            FROM edw.fact_ventas_detalle f
            JOIN edw.dim_fecha d ON f.fecha_sk = d.fecha_sk
            JOIN edw.dim_vendedor v ON f.vendedor_sk = v.vendedor_sk
            JOIN edw.dim_producto p ON f.producto_sk = p.producto_sk
            JOIN edw.dim_estado_documento ed ON f.estado_documento_sk = ed.estado_documento_sk
            WHERE ed.estado_documento_sk <> -1
              AND v.codven = :vendedor AND d.anio = :anio AND d.mes = :mes
              AND p.codart IN (SELECT producto_sugerido_cod FROM ProductosAceptados)
        """)
        row = self.db.execute(query, {"vendedor": vendedor_origen, "anio": anio, "mes": mes}).fetchone()
        return float(row[0]) if row and row[0] is not None else 0.0
