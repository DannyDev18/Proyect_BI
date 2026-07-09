# backend/app/repositories/goal_repository.py
"""Acceso a datos de metas comerciales: histórico de ventas para el cálculo de
propuestas (edw.*, solo lectura) y CRUD de `public.metas_comerciales_operativas`
(ORM vía el modelo `Goal`, lectura/escritura normal)."""
import datetime
from typing import NamedTuple

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.models.goal import Goal


class VendorSalesTrend(NamedTuple):
    vendedor_origen: str
    sucursal: str
    ventas_anterior: float
    unidades_anterior: float
    ventas_anio_anterior: float
    promedio_movil_3m: float
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
                WHERE f.estado_factura = 'P'
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
