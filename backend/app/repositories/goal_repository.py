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
    Comisiones)."""
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


class VendorSalesTrend(NamedTuple):
    vendedor_origen: str
    sucursal: str
    ventas_anterior: float
    unidades_anterior: float
    ventas_anio_anterior: float
    promedio_movil_3m: float
    indice_estacional_relativo: float
    vendedor_sk: int
    sucursal_sk: int


class GoalRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_sales_trend_for_goals(self, anio: int, mes: int) -> list[VendorSalesTrend]:
        """CTE que combina estacionalidad interanual + tendencia del año en curso (sin el
        mes pico) por vendedor/sucursal -- insumo para `GoalsService.generate_proposals`."""
        mes_ant = 12 if mes == 1 else mes - 1
        anio_ant = anio - 1 if mes == 1 else anio

        query = text("""
            WITH VentaMensual AS (
                SELECT
                    v.codven AS vendedor_origen,
                    s.nombre_sucursal AS sucursal,
                    MAX(f.vendedor_sk) AS vendedor_sk,
                    MAX(f.sucursal_sk) AS sucursal_sk,
                    d.anio,
                    d.mes,
                    SUM(f.subtotal_neto) AS net_sales,
                    SUM(f.cantidad) AS net_unidades
                FROM edw.fact_ventas_detalle f
                JOIN edw.dim_fecha d ON f.fecha_sk = d.fecha_sk
                JOIN edw.dim_sucursal s ON f.sucursal_sk = s.sucursal_sk
                JOIN edw.dim_vendedor v ON f.vendedor_sk = v.vendedor_sk
                JOIN edw.dim_estado_documento ed ON f.estado_documento_sk = ed.estado_documento_sk
                WHERE ed.estado_documento_sk <> -1
                GROUP BY v.codven, s.nombre_sucursal, d.anio, d.mes
            ),
            PrevMonth AS (
                SELECT * FROM VentaMensual WHERE anio = :anio_ant AND mes = :mes_ant
            ),
            SameMonthLastYear AS (
                SELECT vendedor_origen, sucursal, net_sales
                FROM VentaMensual WHERE anio = (:anio - 1) AND mes = :mes
            ),
            Seasonality AS (
                SELECT vendedor_origen, sucursal, AVG(net_sales) AS avg_estacional
                FROM VentaMensual
                WHERE mes = :mes AND anio < :anio
                GROUP BY vendedor_origen, sucursal
            ),
            CurrentYearMonths AS (
                SELECT * FROM VentaMensual WHERE anio = :anio AND mes < :mes
            ),
            CurrentYearMax AS (
                SELECT vendedor_origen, sucursal, MAX(net_sales) AS max_sales, COUNT(*) AS num_meses
                FROM CurrentYearMonths
                GROUP BY vendedor_origen, sucursal
            ),
            TrendSinMax AS (
                SELECT m.vendedor_origen, m.sucursal, AVG(m.net_sales) AS avg_tendencia_sin_max
                FROM CurrentYearMonths m
                JOIN CurrentYearMax mx ON m.vendedor_origen = mx.vendedor_origen AND m.sucursal = mx.sucursal
                WHERE m.net_sales < mx.max_sales OR mx.num_meses <= 2
                GROUP BY m.vendedor_origen, m.sucursal
            )
            SELECT
                p.vendedor_origen,
                p.sucursal,
                COALESCE(p.net_sales, 0.0) AS ventas_anterior,
                COALESCE(p.net_unidades, 0.0) AS unidades_anterior,
                COALESCE(yoy.net_sales, 0.0) AS ventas_anio_anterior,
                COALESCE(
                    (s.avg_estacional + t.avg_tendencia_sin_max) / 2.0,
                    s.avg_estacional, t.avg_tendencia_sin_max, p.net_sales, 0.0
                ) AS promedio_movil_3m,
                -- Índice estacional relativo (H-13, docs/auditoria/11_auditoria_tecnica_modelos_ml.md):
                -- mismo concepto que ml/src/data/make_dataset.py::fetch_goals_data
                -- (estacionalidad_mes_objetivo / promedio_movil_3m), aproximado con las
                -- columnas ya disponibles en esta CTE -- s.avg_estacional YA es la
                -- estacionalidad histórica del mes objetivo (:mes/:anio, filtrada a
                -- años anteriores), y se compara contra el mismo promedio_movil_3m
                -- compuesto de esta consulta (no es una réplica línea a línea del SQL
                -- de entrenamiento, que calcula el promedio_movil_3m del mes BASE por
                -- separado; ver docs/ml_contracts.md, known_serving_mismatch de goals).
                COALESCE(
                    s.avg_estacional / NULLIF(
                        COALESCE((s.avg_estacional + t.avg_tendencia_sin_max) / 2.0,
                                 s.avg_estacional, t.avg_tendencia_sin_max, p.net_sales, 0.0),
                        0.0
                    ),
                    1.0
                ) AS indice_estacional_relativo,
                p.vendedor_sk,
                p.sucursal_sk
            FROM PrevMonth p
            LEFT JOIN SameMonthLastYear yoy ON p.vendedor_origen = yoy.vendedor_origen AND p.sucursal = yoy.sucursal
            LEFT JOIN Seasonality s ON p.vendedor_origen = s.vendedor_origen AND p.sucursal = s.sucursal
            LEFT JOIN TrendSinMax t ON p.vendedor_origen = t.vendedor_origen AND p.sucursal = t.sucursal
        """)
        rows = self.db.execute(query, {"anio_ant": anio_ant, "mes_ant": mes_ant, "anio": anio, "mes": mes}).fetchall()
        return [VendorSalesTrend(*row) for row in rows]

    def find_proposal(self, anio: int, mes: int, vendedor: str, sucursal: str) -> tuple[int, str] | None:
        row = self.db.execute(
            text("""
                SELECT id, estado FROM public.metas_comerciales_operativas
                WHERE anio = :anio AND mes = :mes AND id_vendedor_origen = :vendedor AND sucursal = :sucursal
            """),
            {"anio": anio, "mes": mes, "vendedor": vendedor, "sucursal": sucursal},
        ).fetchone()
        return (row[0], row[1]) if row else None

    def insert_proposal(self, anio: int, mes: int, vendedor: str, sucursal: str, monto_meta: float, unidades_meta: float) -> None:
        self.db.execute(
            text("""
                INSERT INTO public.metas_comerciales_operativas
                (anio, mes, id_vendedor_origen, sucursal, monto_meta, unidades_meta, estado, comision_base_pct, bono_sobrecumplimiento)
                VALUES (:anio, :mes, :vendedor, :sucursal, :meta_monto, :meta_unidades, 'PROPUESTA', 0.0, 0.0)
            """),
            {"anio": anio, "mes": mes, "vendedor": vendedor, "sucursal": sucursal,
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
                    MAX(v.nombre_vendedor) AS vendedor, m.sucursal, m.monto_meta AS meta_monto,
                    m.comision_base_pct, m.bono_sobrecumplimiento, m.id AS id_meta, m.estado
                FROM public.metas_comerciales_operativas m
                LEFT JOIN edw.dim_vendedor v ON m.id_vendedor_origen = v.codven
                WHERE m.anio = :anio AND m.mes = :mes
                GROUP BY m.id, m.sucursal, m.monto_meta, m.comision_base_pct, m.bono_sobrecumplimiento, m.estado
                ORDER BY MAX(v.nombre_vendedor) ASC
            """),
            {"anio": anio, "mes": mes},
        ).fetchall()
        return [
            {
                "id": int(row[5]), "vendedor": str(row[0]), "sucursal": str(row[1]),
                "monto_meta": float(row[2]), "comision_base_pct": float(row[3]), "estado": str(row[6]),
            }
            for row in rows
        ]

    # ── Integración ML (Metas y Comisiones): histórico, anomalías, top productos ──
    def get_vendor_monthly_history(self, vendedor_origen: str, sucursal: str, meses: int = 24) -> list[VendorMonthlySales]:
        """Serie mensual agregada de ventas/unidades de un vendedor -- insumo del motor
        estadístico (`goal_calculation_engine.IQRGoalCalculationEngine`), que a su vez
        alimenta la meta sugerida por IA junto con el modelo `goals_rf`."""
        query = text("""
            SELECT d.anio, d.mes,
                   COALESCE(SUM(f.subtotal_neto), 0) AS ventas,
                   COALESCE(SUM(f.cantidad), 0) AS unidades
            FROM edw.fact_ventas_detalle f
            JOIN edw.dim_fecha d ON f.fecha_sk = d.fecha_sk
            JOIN edw.dim_sucursal s ON f.sucursal_sk = s.sucursal_sk
            JOIN edw.dim_vendedor v ON f.vendedor_sk = v.vendedor_sk
            JOIN edw.dim_estado_documento ed ON f.estado_documento_sk = ed.estado_documento_sk
            WHERE ed.estado_documento_sk <> -1
              AND v.codven = :vendedor AND s.nombre_sucursal = :sucursal
            GROUP BY d.anio, d.mes
            ORDER BY d.anio DESC, d.mes DESC
            LIMIT :meses
        """)
        rows = self.db.execute(query, {"vendedor": vendedor_origen, "sucursal": sucursal, "meses": meses}).fetchall()
        return [VendorMonthlySales(anio=int(r[0]), mes=int(r[1]), ventas=float(r[2]), unidades=float(r[3])) for r in rows]

    def get_vendor_transactions_history(self, vendedor_origen: str, sucursal: str, anio_desde: int, mes_desde: int) -> list[VendorTransactionFeatures]:
        """Todas las líneas de transacción de un vendedor desde `(anio_desde, mes_desde)`
        en adelante, con las mismas 4 columnas y política de nulos que
        `ml/contracts/models/anomalies.json` (excluye `costo_total IS NULL`, H-19) --
        en un solo batch, para correr `inference.detect_anomalies` una sola vez al
        grano correcto (línea de transacción, no agregado mensual) y luego agrupar por
        mes en el servicio."""
        query = text("""
            SELECT d.anio, d.mes, f.subtotal_neto, f.cantidad, f.costo_total, (f.subtotal_neto - f.costo_total) AS margen
            FROM edw.fact_ventas_detalle f
            JOIN edw.dim_fecha d ON f.fecha_sk = d.fecha_sk
            JOIN edw.dim_sucursal s ON f.sucursal_sk = s.sucursal_sk
            JOIN edw.dim_vendedor v ON f.vendedor_sk = v.vendedor_sk
            JOIN edw.dim_estado_documento ed ON f.estado_documento_sk = ed.estado_documento_sk
            WHERE ed.estado_documento_sk <> -1
              AND v.codven = :vendedor AND s.nombre_sucursal = :sucursal
              AND (d.anio, d.mes) >= (:anio_desde, :mes_desde)
              AND f.costo_total IS NOT NULL
        """)
        rows = self.db.execute(query, {
            "vendedor": vendedor_origen, "sucursal": sucursal, "anio_desde": anio_desde, "mes_desde": mes_desde,
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
