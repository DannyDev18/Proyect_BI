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
    ComisionVariableCalculada, DesgloseLinea, NivelCumplimiento, calcular_comision, fecha_referencia_periodo,
)
from app.services.commission_variable_engine import calcular_comision_variable_completa

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
    # Auditoría 43 (H43-15, docs/auditoria/43_correcciones_sesion_ventas_y_datos.md): el
    # frontend etiquetaba el panel dual con un texto fijo ("Piloto en sombra", "no afecta
    # tu pago actual") que asumía `COMISION_MODO=sombra` -- se vuelve FALSO en cuanto se
    # activa `variable` (ahí sí se paga sobre el esquema nuevo). Se expone el modo real
    # para que la UI se derive de él en vez de asumirlo.
    modo_comision: str = "plana"


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
    def get_commission_tracking(self, anio: int, mes: int, vendedor: str | None = None) -> list[VendorCommissionRow]:
        rows = self.goal_repo.get_commission_tracking_rows(anio, mes, vendedor=vendedor)
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

            resultado.append(VendorCommissionRow(
                id=r["id"], vendedor=r["vendedor"], monto_meta=c.monto_meta,
                venta_real=c.venta_real, pct_cumplimiento=c.pct_cumplimiento, nivel=c.nivel.value,
                tasa_aplicada_pct=c.tasa_aplicada_pct, comision_devengada=c.comision_devengada,
                estado=r["estado"], comision_variable=comision_variable, nivel_variable=nivel_variable,
            ))
        return resultado

    # ── Fase 2 Gerencia: KPI de cumplimiento vs metas del dashboard principal ──────
    # (docs/features/plan_correcciones_pendientes.md §3) -- agregado company-wide,
    # sin el cálculo de comisión (irrelevante para esta tarjeta), a diferencia de
    # get_commission_tracking (panel de Metas y Comisiones, por vendedor).
    def get_cumplimiento_meta_periodo(self, anio: int, mes: int) -> dict:
        """Solo metas `APROBADA`: una `PROPUESTA` sin aprobar todavía no es un
        compromiso real de gerencia, y una `RECHAZADA` no debe contar como meta."""
        rows = self.goal_repo.get_commission_tracking_rows(anio, mes)
        aprobadas = [r for r in rows if r["estado"] == "APROBADA"]
        monto_meta_total = sum(r["monto_meta"] for r in aprobadas)
        venta_real_total = sum(r["venta_neta"] for r in aprobadas)
        pct_cumplimiento = (venta_real_total / monto_meta_total * 100.0) if monto_meta_total > 0 else 0.0
        return {
            "anio": anio, "mes": mes,
            "monto_meta_total": round(monto_meta_total, 2),
            "venta_real_total": round(venta_real_total, 2),
            "pct_cumplimiento": round(pct_cumplimiento, 2),
            "vendedores_con_meta_aprobada": len(aprobadas),
        }

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

        return MiComision(
            vendedor_origen=vendedor_origen, anio=anio, mes=mes,
            monto_meta=c.monto_meta, venta_real=c.venta_real, pct_cumplimiento=c.pct_cumplimiento,
            nivel=c.nivel.value, tasa_aplicada_pct=c.tasa_aplicada_pct, bono_aplicado=c.bono_aplicado,
            comision_devengada=c.comision_devengada, dias_restantes_mes=dias_restantes,
            en_alerta_cierre=en_alerta, mensaje_alerta=mensaje,
            comision_variable=comision_variable, nivel_variable=nivel_variable, desglose_variable=desglose_variable,
            modo_comision=settings.COMISION_MODO,
        )

    # `settings.COMISION_MODO` ("plana"/"sombra"/"variable") es el mecanismo de rollback
    # del backend; `comision_liquidaciones.modo` es un CHECK constraint de solo
    # ('sombra','oficial') -- son dos vocabularios distintos a propósito (el de la BD
    # describe si la liquidación es un piloto o el cierre oficial, no el modo del
    # backend). Pasar `COMISION_MODO` tal cual violaba el CHECK en modo "variable"
    # (auditoría 34, H-4: toda escritura de snapshot fallaba con IntegrityError en el
    # modo que se supone es el de producción).
    _MODO_BACKEND_A_LIQUIDACION = {"sombra": "sombra", "variable": "oficial"}

    @staticmethod
    def _es_periodo_actual(anio: int, mes: int) -> bool:
        hoy = datetime.date.today()
        return anio == hoy.year and mes == hoy.month

    # ── Motor variable (Comisiones Variables) ──────────────────────────────────────
    def _calcular_variable(
        self, vendedor_origen: str, anio: int, mes: int, venta_real: float, monto_meta: float,
    ) -> ComisionVariableCalculada:
        """Corrección de diseño 2026-07-30 (auditoría 44, petición explícita del
        usuario): las Comisiones Variables son UN SOLO TOTAL por vendedor -- líneas de
        venta (margen/categoría), cobranza (por tramo de días de cobro) y ventas de
        contado de agencia se SUMAN, nunca se elige entre "un esquema u otro". Delega en
        `commission_variable_engine.calcular_comision_variable_completa`, que resuelve
        el monto real de cada componente ACTIVO de la fórmula vigente (hay una sola) y
        evalúa la tubería declarativa configurada -- usado también por
        `CommissionSimulationService` para que el simulador refleje exactamente lo mismo
        que se liquida."""
        assert self.commission_config_repo is not None
        modo_liquidacion = self._MODO_BACKEND_A_LIQUIDACION[settings.COMISION_MODO]

        # Inmutabilidad real de liquidaciones "oficiales" (docs/auditoria/
        # 35_actualizacion_modulo_metas.md, H2): si el período ya cerró y ya existe un
        # snapshot oficial (dinero real, COMISION_MODO=variable), se devuelve TAL CUAL
        # -- nunca se recalcula ni se reescribe. Antes cada vista de un período cerrado
        # recalculaba con la configuración vigente HOY (posiblemente ya cambiada) y
        # sobrescribía el snapshot en `comision_liquidaciones`, pese a que el modelo
        # documenta esa tabla como "snapshot congelado" (salvaguarda 6). El modo
        # "sombra" (piloto, no paga) sigue refrescándose en cada consulta a propósito.
        if modo_liquidacion == "oficial" and not self._es_periodo_actual(anio, mes):
            congelada = self.commission_config_repo.get_liquidacion(
                anio=anio, mes=mes, vendedor_origen=vendedor_origen, esquema="variable", modo="oficial",
            )
            if congelada is not None:
                return self._reconstruir_desde_snapshot(congelada)

        # Configuración vigente AL CIERRE DEL PERÍODO consultado, no "hoy" (docs/auditoria/
        # 35_actualizacion_modulo_metas.md, H1): antes esta llamada no pasaba fecha y
        # siempre resolvía la matriz/crédito vigentes en el momento de la consulta, sin
        # importar qué anio/mes se pedía.
        fecha_periodo = fecha_referencia_periodo(anio, mes)
        resultado = calcular_comision_variable_completa(
            goal_repo=self.goal_repo, commission_config_repo=self.commission_config_repo,
            vendedor_origen=vendedor_origen, anio=anio, mes=mes,
            venta_real=venta_real, monto_meta=monto_meta, fecha_config=fecha_periodo,
        )

        comision_base = (
            resultado.montos.get("base_lineas_venta", 0.0) + resultado.montos.get("base_cobranza", 0.0)
            + resultado.montos.get("contado_agencia", 0.0)
        )
        cv = ComisionVariableCalculada(
            comision_base=round(comision_base, 4),
            comision_post_tipo=round(comision_base * resultado.montos.get("factor_tipo_vendedor", 1.0), 4),
            nivel=resultado.nivel,
            multiplicador_cumplimiento=resultado.montos.get("multiplicador_cumplimiento", 1.0),
            comision_post_cumplimiento=round(
                comision_base * resultado.montos.get("factor_tipo_vendedor", 1.0)
                * resultado.montos.get("multiplicador_cumplimiento", 1.0), 4,
            ),
            devoluciones_estimadas=resultado.montos.get("devoluciones", 0.0),
            bonos_total=resultado.montos.get("bonos", 0.0),
            comision_final=resultado.comision_final,
            desglose_lineas=resultado.desglose_lineas,
            desglose_cobranza=(
                tuple(asdict(d) for d in resultado.desglose_cobranza) if resultado.desglose_cobranza is not None else None
            ),
            traza_formula=resultado.traza_formula,
        )
        # Persiste aquí (no en el llamador): esta es la única rama de cálculo fresco --
        # la rama "congelada" de arriba ya retornó antes de llegar aquí, así que nunca
        # se re-persiste un snapshot ya existente (H2).
        self._persistir_snapshot(anio, mes, vendedor_origen, cv, settings.COMISION_MODO)
        return cv

    def _persistir_snapshot(
        self, anio: int, mes: int, vendedor_origen: str, cv: ComisionVariableCalculada, modo: str,
    ) -> None:
        """Congela el cálculo variable (salvaguarda 6: transparencia total) -- solo
        para períodos ya cerrados (no el mes en curso, que cambia con cada consulta).
        Para modo "oficial" solo se llega aquí cuando `_calcular_variable` NO encontró
        un snapshot previo (primera congelación) -- de lo contrario ya retornó antes."""
        assert self.commission_config_repo is not None
        if self._es_periodo_actual(anio, mes):
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

    @staticmethod
    def _reconstruir_desde_snapshot(row) -> ComisionVariableCalculada:
        """Reconstruye `ComisionVariableCalculada` desde `comision_liquidaciones.detalle_json`
        (mismo shape que produce `_serializar_desglose`) -- sin volver a tocar el motor
        ni la configuración actual, para no romper la inmutabilidad del snapshot."""
        d = dict(row.detalle_json)
        nivel = NivelCumplimiento(d.pop("nivel"))
        desglose = tuple(DesgloseLinea(**dl) for dl in d.pop("desglose_lineas", []))
        return ComisionVariableCalculada(nivel=nivel, desglose_lineas=desglose, **d)
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
