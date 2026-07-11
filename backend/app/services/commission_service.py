# backend/app/services/commission_service.py
"""Servicio de comisiones (docs/modulo_metas.md, docs/auditoria/17_comisiones_liquidacion.md):
compone `GoalRepository` (venta real vs. meta configurada) con `commission_engine` (cálculo
puro de tramos/tasa/bono). Cierra el hallazgo R-1 de `docs/auditoria/14_...md`:
`GoalsService.get_commission_tracking`/`GoalRepository.get_commission_report` nunca calculaban
cumplimiento real, solo devolvían la meta configurada."""
from __future__ import annotations

import datetime
from dataclasses import dataclass

from app.repositories.goal_repository import GoalRepository
from app.services.commission_engine import calcular_comision

# Alerta de cierre (docs/modulo_metas.md, Fase 3 "PROPUESTA IA"): última semana del mes,
# vendedor por debajo del umbral de riesgo -> mensaje destacado.
DIAS_ALERTA_CIERRE = 7
UMBRAL_ALERTA_PCT = 70.0


@dataclass
class VendorCommissionRow:
    id: int
    vendedor: str
    monto_meta: float
    venta_real: float
    pct_cumplimiento: float
    nivel: str
    tasa_aplicada_pct: float
    comision_devengada: float
    estado: str


@dataclass
class MiComision:
    vendedor_origen: str
    anio: int
    mes: int
    monto_meta: float
    venta_real: float
    pct_cumplimiento: float
    nivel: str
    tasa_aplicada_pct: float
    bono_aplicado: float
    comision_devengada: float
    dias_restantes_mes: int
    en_alerta_cierre: bool
    mensaje_alerta: str | None


@dataclass
class PostGoalInvoiceItem:
    num_factura: str
    fecha: str
    monto_factura: float
    acumulado_venta: float


class CommissionService:
    def __init__(self, goal_repo: GoalRepository):
        self.goal_repo = goal_repo

    # ── Panel gerencial: cumplimiento real de todos los vendedores del período ────
    def get_commission_tracking(self, anio: int, mes: int) -> list[VendorCommissionRow]:
        rows = self.goal_repo.get_commission_tracking_rows(anio, mes)
        resultado = []
        for r in rows:
            c = calcular_comision(
                venta_real=r["venta_neta"], monto_meta=r["monto_meta"],
                comision_base_pct=r["comision_base_pct"], bono_sobrecumplimiento=r["bono_sobrecumplimiento"],
            )
            resultado.append(VendorCommissionRow(
                id=r["id"], vendedor=r["vendedor"], monto_meta=c.monto_meta,
                venta_real=c.venta_real, pct_cumplimiento=c.pct_cumplimiento, nivel=c.nivel.value,
                tasa_aplicada_pct=c.tasa_aplicada_pct, comision_devengada=c.comision_devengada,
                estado=r["estado"],
            ))
        return resultado

    # ── Panel del vendedor: su propia comisión del mes en curso ───────────────────
    def get_my_commission(self, vendedor_origen: str, anio: int, mes: int) -> MiComision:
        goal = self.goal_repo.get_goal_for_period(vendedor_origen, anio, mes)
        monto_meta = float(goal.monto_meta) if goal else 0.0
        comision_base_pct = float(goal.comision_base_pct) if goal else 0.0
        bono = float(goal.bono_sobrecumplimiento) if goal else 0.0

        venta_real = self.goal_repo.get_vendor_net_sales_period(vendedor_origen, anio, mes)
        c = calcular_comision(venta_real, monto_meta, comision_base_pct, bono)

        dias_restantes, en_ultima_semana = self._dias_restantes_mes(anio, mes)
        en_alerta = en_ultima_semana and c.pct_cumplimiento < UMBRAL_ALERTA_PCT

        mensaje: str | None = None
        if c.pct_cumplimiento >= 100:
            mensaje = "¡Meta superada este período!"
        elif en_alerta:
            faltante = max(0.0, monto_meta - venta_real)
            mensaje = f"¡Última semana! Necesitas vender {faltante:,.2f} más para alcanzar tu meta."

        return MiComision(
            vendedor_origen=vendedor_origen, anio=anio, mes=mes,
            monto_meta=c.monto_meta, venta_real=c.venta_real, pct_cumplimiento=c.pct_cumplimiento,
            nivel=c.nivel.value, tasa_aplicada_pct=c.tasa_aplicada_pct, bono_aplicado=c.bono_aplicado,
            comision_devengada=c.comision_devengada, dias_restantes_mes=dias_restantes,
            en_alerta_cierre=en_alerta, mensaje_alerta=mensaje,
        )

    # ── Facturas emitidas después de alcanzar la meta ──────────────────────────────
    def get_post_goal_invoices(self, vendedor_origen: str, anio: int, mes: int) -> list[PostGoalInvoiceItem]:
        goal = self.goal_repo.get_goal_for_period(vendedor_origen, anio, mes)
        if not goal or float(goal.monto_meta) <= 0:
            return []
        rows = self.goal_repo.get_post_goal_invoices(vendedor_origen, anio, mes, float(goal.monto_meta))
        return [PostGoalInvoiceItem(**r) for r in rows]

    @staticmethod
    def _dias_restantes_mes(anio: int, mes: int) -> tuple[int, bool]:
        """Días restantes del mes SOLO si `anio`/`mes` es el mes en curso -- un período
        cerrado o futuro no tiene "días restantes" reales (0, sin alerta de cierre)."""
        hoy = datetime.date.today()
        if hoy.year != anio or hoy.month != mes:
            return 0, False
        ultimo_dia = datetime.date(anio + (mes == 12), (mes % 12) + 1, 1) - datetime.timedelta(days=1)
        dias_restantes = (ultimo_dia - hoy).days
        return dias_restantes, dias_restantes <= DIAS_ALERTA_CIERRE
