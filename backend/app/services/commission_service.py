# backend/app/services/commission_service.py
"""Servicio de comisiones (docs/modulo_metas.md, docs/auditoria/17_comisiones_liquidacion.md):
compone `GoalRepository` (venta real vs. meta configurada) con `commission_engine` (cálculo
puro de tramos/tasa/bono). Cierra el hallazgo R-1 de `docs/auditoria/14_...md`:
`GoalsService.get_commission_tracking`/`GoalRepository.get_commission_report` nunca calculaban
cumplimiento real, solo devolvían la meta configurada."""
from __future__ import annotations

import datetime
from dataclasses import asdict, dataclass

from app.core.config import settings
from app.repositories.commission_config_repository import CommissionConfigRepository
from app.repositories.goal_repository import GoalRepository
from app.services.commission_engine import (
    ComisionVariableCalculada, ConfigComisionVariable, LineaComisionable, calcular_comision, calcular_comision_variable,
)

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
    # Comisiones Variables (docs/features/plan_integracion_comisiones_variables.md):
    # poblados solo cuando `settings.COMISION_MODO` in ("sombra", "variable"); None en
    # modo "plana" (comportamiento por defecto, sin cambios de contrato para el resto).
    comision_variable: float | None = None
    nivel_variable: str | None = None


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
    comision_variable: float | None = None
    nivel_variable: str | None = None
    desglose_variable: dict | None = None


@dataclass
class PostGoalInvoiceItem:
    num_factura: str
    fecha: str
    monto_factura: float
    acumulado_venta: float


class CommissionService:
    def __init__(self, goal_repo: GoalRepository, commission_config_repo: CommissionConfigRepository | None = None):
        self.goal_repo = goal_repo
        self.commission_config_repo = commission_config_repo

    # ── Panel gerencial: cumplimiento real de todos los vendedores del período ────
    def get_commission_tracking(self, anio: int, mes: int) -> list[VendorCommissionRow]:
        rows = self.goal_repo.get_commission_tracking_rows(anio, mes)
        modo = settings.COMISION_MODO
        resultado = []
        for r in rows:
            c = calcular_comision(
                venta_real=r["venta_neta"], monto_meta=r["monto_meta"],
                comision_base_pct=r["comision_base_pct"], bono_sobrecumplimiento=r["bono_sobrecumplimiento"],
            )
            comision_variable = None
            nivel_variable = None
            if modo in ("sombra", "variable") and self.commission_config_repo is not None and r.get("id_vendedor_origen"):
                cv = self._calcular_variable(r["id_vendedor_origen"], anio, mes, r["venta_neta"], r["monto_meta"])
                comision_variable = cv.comision_final
                nivel_variable = cv.nivel.value
                self._persistir_snapshot(anio, mes, r["id_vendedor_origen"], cv, modo)

            resultado.append(VendorCommissionRow(
                id=r["id"], vendedor=r["vendedor"], monto_meta=c.monto_meta,
                venta_real=c.venta_real, pct_cumplimiento=c.pct_cumplimiento, nivel=c.nivel.value,
                tasa_aplicada_pct=c.tasa_aplicada_pct, comision_devengada=c.comision_devengada,
                estado=r["estado"], comision_variable=comision_variable, nivel_variable=nivel_variable,
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

        comision_variable = None
        nivel_variable = None
        desglose_variable = None
        if settings.COMISION_MODO in ("sombra", "variable") and self.commission_config_repo is not None:
            cv = self._calcular_variable(vendedor_origen, anio, mes, venta_real, monto_meta)
            comision_variable = cv.comision_final
            nivel_variable = cv.nivel.value
            desglose_variable = self._serializar_desglose(cv)
            self._persistir_snapshot(anio, mes, vendedor_origen, cv, settings.COMISION_MODO)

        return MiComision(
            vendedor_origen=vendedor_origen, anio=anio, mes=mes,
            monto_meta=c.monto_meta, venta_real=c.venta_real, pct_cumplimiento=c.pct_cumplimiento,
            nivel=c.nivel.value, tasa_aplicada_pct=c.tasa_aplicada_pct, bono_aplicado=c.bono_aplicado,
            comision_devengada=c.comision_devengada, dias_restantes_mes=dias_restantes,
            en_alerta_cierre=en_alerta, mensaje_alerta=mensaje,
            comision_variable=comision_variable, nivel_variable=nivel_variable, desglose_variable=desglose_variable,
        )

    # ── Motor variable (Comisiones Variables) ──────────────────────────────────────
    def _calcular_variable(
        self, vendedor_origen: str, anio: int, mes: int, venta_real: float, monto_meta: float,
    ) -> ComisionVariableCalculada:
        assert self.commission_config_repo is not None
        lineas_repo = self.goal_repo.get_commission_lines(vendedor_origen, anio, mes)
        lineas = [
            LineaComisionable(
                codart=l.codart, clase=l.clase, subclase=l.subclase, es_servicio=l.es_servicio,
                subtotal_neto=l.subtotal_neto, margen_bruto=l.margen_bruto, valor_descuento=l.valor_descuento,
                dias_plazo=l.dias_plazo,
            )
            for l in lineas_repo
        ]
        matriz = self.commission_config_repo.get_matriz_as_reglas()
        rangos_credito = self.commission_config_repo.get_factores_credito_as_rangos()
        config_vendedor = self.commission_config_repo.get_config_vendedor(vendedor_origen)
        factor_tipo = (
            float(config_vendedor.factor_tipo) if config_vendedor else settings.COMISION_FACTOR_EXTERNO_DEFAULT
        )
        devoluciones = self.goal_repo.get_vendor_devoluciones_period(vendedor_origen, anio, mes)
        config = ConfigComisionVariable(
            tope_descuento_pct=settings.COMISION_TOPE_DESCUENTO_PCT,
            tasa_minima_sin_costo_pct=settings.COMISION_TASA_MINIMA_SIN_COSTO_PCT,
            umbral_subtotal_x=settings.COMISION_UMBRAL_SUBTOTAL_X,
            mult_excelente=settings.COMISION_MULT_EXCELENTE, mult_cerca=settings.COMISION_MULT_CERCA,
            piso_lejos=settings.COMISION_PISO_LEJOS,
        )

        # Bono 3 (cobranza sana) es "% ADICIONAL SOBRE LA COMISIÓN TOTAL" (§3.4 del plan)
        # -- requiere conocer la comisión antes de sumar bonos, así que se resuelve en
        # dos pasadas: (1) sin bonos, para obtener `comision_post_cumplimiento`; (2) con
        # el total de bonos ya conocido.
        pre_bonos = calcular_comision_variable(
            lineas=lineas, matriz=matriz, rangos_credito=rangos_credito, factor_tipo_vendedor=factor_tipo,
            venta_real=venta_real, monto_meta=monto_meta, devoluciones_mes=devoluciones,
            bonos_total=0.0, config=config,
        )
        bonos_total = self._calcular_bonos(vendedor_origen, anio, mes, pre_bonos.comision_post_cumplimiento)
        if bonos_total == 0.0:
            return pre_bonos

        return calcular_comision_variable(
            lineas=lineas, matriz=matriz, rangos_credito=rangos_credito, factor_tipo_vendedor=factor_tipo,
            venta_real=venta_real, monto_meta=monto_meta, devoluciones_mes=devoluciones,
            bonos_total=bonos_total, config=config,
        )

    def _calcular_bonos(self, vendedor_origen: str, anio: int, mes: int, comision_pre_bonos: float) -> float:
        """Bonos complementarios (§3.4 del plan): venta cruzada aceptada, cliente
        nuevo/reactivado, cobranza sana. El bono 4 (visitas) queda diferido -- brecha B3
        (sin geolocalización en el EDW, auditoría 30)."""
        bono_cross_sell = (
            self.goal_repo.get_cross_sell_accepted_amount(vendedor_origen, anio, mes)
            * (settings.COMISION_BONO_CROSS_SELL_PCT / 100.0)
        )
        clientes_nuevos = self.goal_repo.get_new_or_reactivated_clients(
            vendedor_origen, anio, mes, settings.COMISION_MESES_CLIENTE_REACTIVADO,
        )
        bono_cliente_nuevo = clientes_nuevos * settings.COMISION_BONO_CLIENTE_NUEVO

        perfil_credito = self.goal_repo.get_vendor_credit_profile(vendedor_origen, anio, mes)
        dias_cobro = perfil_credito.get("dias_cobro_promedio")
        bono_cobranza = 0.0
        if dias_cobro is not None and dias_cobro < settings.COMISION_BONO_COBRANZA_DIAS:
            bono_cobranza = max(0.0, comision_pre_bonos) * (settings.COMISION_BONO_COBRANZA_PCT / 100.0)

        return round(bono_cross_sell + bono_cliente_nuevo + bono_cobranza, 4)

    # `settings.COMISION_MODO` ("plana"/"sombra"/"variable") es el mecanismo de rollback
    # del backend; `comision_liquidaciones.modo` es un CHECK constraint de solo
    # ('sombra','oficial') -- son dos vocabularios distintos a propósito (el de la BD
    # describe si la liquidación es un piloto o el cierre oficial, no el modo del
    # backend). Pasar `COMISION_MODO` tal cual violaba el CHECK en modo "variable"
    # (auditoría 34, H-4: toda escritura de snapshot fallaba con IntegrityError en el
    # modo que se supone es el de producción).
    _MODO_BACKEND_A_LIQUIDACION = {"sombra": "sombra", "variable": "oficial"}

    def _persistir_snapshot(
        self, anio: int, mes: int, vendedor_origen: str, cv: ComisionVariableCalculada, modo: str,
    ) -> None:
        """Congela el cálculo variable (salvaguarda 6: transparencia total) -- solo
        para períodos ya cerrados (no el mes en curso, que cambia con cada consulta)."""
        assert self.commission_config_repo is not None
        hoy = datetime.date.today()
        if anio == hoy.year and mes == hoy.month:
            return
        modo_liquidacion = self._MODO_BACKEND_A_LIQUIDACION[modo]
        self.commission_config_repo.save_liquidacion(
            anio=anio, mes=mes, vendedor_origen=vendedor_origen, esquema="variable", modo=modo_liquidacion,
            comision_total=cv.comision_final, detalle_json=self._serializar_desglose(cv),
        )

    @staticmethod
    def _serializar_desglose(cv: ComisionVariableCalculada) -> dict:
        d = asdict(cv)
        d["nivel"] = cv.nivel.value
        return d

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
