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
from app.repositories.catalog_repository import CatalogRepository
from app.repositories.commission_config_repository import CommissionConfigRepository
from app.repositories.goal_repository import GoalRepository
from app.services.commission_engine import (
    ComisionVariableCalculada, DesgloseLinea, NivelCumplimiento, fecha_referencia_periodo,
)
from app.services.commission_variable_engine import (
    calcular_comision_variable_completa, resolver_componentes_formula, resolver_tramos_cumplimiento,
)

# Alerta de cierre (docs/modulo_metas.md, Fase 3 "PROPUESTA IA"): última semana del mes,
# vendedor por debajo del umbral de riesgo -> mensaje destacado.
DIAS_ALERTA_CIERRE = 7
UMBRAL_ALERTA_PCT = 70.0


@dataclass
class VendorCommissionRow:
    """Fase 1 del plan de Metas v3 y Comisiones Unificadas (docs/features/
    plan_motor_metas_v3_y_comisiones_unificadas.md, R-1/R-3): la comisión del sistema
    es única y variable -- el esquema plano (`commission_engine.calcular_comision`)
    queda retirado de esta ruta de servicio. `comision_devengada`/`pct_cumplimiento`/
    `nivel`/`tasa_aplicada_pct` ya NO son el esquema plano legacy: son la comisión
    variable, sus tramos configurables (auditoría 45) y su tasa efectiva
    (`comision_devengada / venta_real`). No hay dos columnas de comisión que puedan
    contradecirse entre sí."""
    id: int
    vendedor: str
    monto_meta: float
    venta_real: float
    pct_cumplimiento: float
    nivel: str
    tasa_aplicada_pct: float
    comision_devengada: float
    estado: str
    # Desglose completo de los 7 componentes de la fórmula (traza de
    # `evaluar_formula`) -- lo que el panel expande al hacer clic en el vendedor.
    componentes: tuple[dict, ...] = ()


@dataclass
class MiComision:
    """Fase 1 (docs/features/plan_motor_metas_v3_y_comisiones_unificadas.md, R-1):
    igual que `VendorCommissionRow`, esta es la comisión ÚNICA y variable del
    vendedor -- ya no hay un cálculo plano paralelo. `bono_aplicado` se conserva por
    compatibilidad de nombre de campo pero ahora refleja `bonos_total` de la comisión
    variable (los 3 bonos ya sumados, con techo relativo aplicado -- Fase 2)."""
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
    desglose_variable: dict | None = None


@dataclass
class PostGoalInvoiceItem:
    num_factura: str
    fecha: str
    monto_factura: float
    acumulado_venta: float


class CommissionService:
    def __init__(
        self, goal_repo: GoalRepository, commission_config_repo: CommissionConfigRepository | None = None,
        catalog_repo: CatalogRepository | None = None,
    ):
        self.goal_repo = goal_repo
        self.commission_config_repo = commission_config_repo
        self.catalog_repo = catalog_repo

    # ── Panel gerencial: cumplimiento real de todos los vendedores del período ────
    def get_commission_tracking(self, anio: int, mes: int, vendedor: str | None = None) -> list[VendorCommissionRow]:
        """Comisión ÚNICA y variable (docs/features/plan_motor_metas_v3_y_comisiones_
        unificadas.md, Fase 1, R-1/R-3): el esquema plano (`calcular_comision`) ya no
        alimenta esta tabla -- `comision_devengada` es siempre la comisión variable, con
        el gate de cumplimiento (Fase 2: $0 bajo el tramo "Sin comisión", bonos
        incluidos) y el techo de bonos ya aplicados.

        Configuración (fórmula/matriz/tramos de cumplimiento) resuelta UNA VEZ para
        todo el período -- mismo patrón de pre-resolución que
        `CommissionSimulationService`, en vez de una consulta por vendedor.

        Solo vendedores activos (petición explícita del usuario, mismo criterio que
        `GoalsService.get_commission_tracking`): `edw.dim_vendedor.activo` se resuelve
        en lote (nunca N+1) y las filas de vendedores dados de baja se excluyen -- no
        tiene sentido mostrar "Cumplimiento real y comisión por vendedor" de alguien que
        ya no vende."""
        rows = self.goal_repo.get_commission_tracking_rows(anio, mes, vendedor=vendedor)
        if self.catalog_repo is not None and rows:
            activos = self.catalog_repo.get_vendedores_activo_bulk(
                [r["id_vendedor_origen"] for r in rows if r.get("id_vendedor_origen")],
            )
            rows = [r for r in rows if activos.get(r.get("id_vendedor_origen"), False)]
        assert self.commission_config_repo is not None
        config_periodo = self._resolver_config_variable_periodo(anio, mes)
        resultado = []
        for r in rows:
            if r.get("id_vendedor_origen"):
                cv = self._calcular_variable(
                    r["id_vendedor_origen"], anio, mes, r["venta_neta"], r["monto_meta"], config_periodo=config_periodo,
                )
                tasa_efectiva = round(cv.comision_final / r["venta_neta"] * 100, 4) if r["venta_neta"] > 0 else 0.0
                # `cv.pct_cumplimiento` puede ser `None` en un snapshot congelado ANTES
                # de la auditoría 45 -- se deriva de venta/meta como respaldo.
                pct_cumplimiento = cv.pct_cumplimiento if cv.pct_cumplimiento is not None else (
                    round(r["venta_neta"] / r["monto_meta"] * 100, 4) if r["monto_meta"] > 0 else 0.0
                )
                resultado.append(VendorCommissionRow(
                    id=r["id"], vendedor=r["vendedor"], monto_meta=round(r["monto_meta"], 2),
                    venta_real=round(r["venta_neta"], 2), pct_cumplimiento=pct_cumplimiento,
                    nivel=cv.tramo_etiqueta or cv.nivel.value, tasa_aplicada_pct=tasa_efectiva,
                    comision_devengada=cv.comision_final, estado=r["estado"],
                    componentes=cv.traza_formula or (),
                ))
            else:
                # Sin código SAP resuelto (dato de catálogo incompleto): no hay forma de
                # calcular el motor variable para esta fila -- se expone en $0 en vez de
                # ocultarla, con el mismo criterio defensivo que ya usaba `calcular_comision`
                # sin meta configurada.
                resultado.append(VendorCommissionRow(
                    id=r["id"], vendedor=r["vendedor"], monto_meta=round(r["monto_meta"], 2),
                    venta_real=round(r["venta_neta"], 2), pct_cumplimiento=0.0, nivel="Sin comisión",
                    tasa_aplicada_pct=0.0, comision_devengada=0.0, estado=r["estado"],
                ))
        return resultado

    def _resolver_config_variable_periodo(self, anio: int, mes: int) -> dict:
        """Resuelve fórmula/matriz/crédito/tramos de cumplimiento vigentes AL CIERRE DEL
        PERÍODO consultado (docs/auditoria/35_actualizacion_modulo_metas.md, H1 -- nunca
        "hoy", que puede ya haber cambiado desde entonces) -- una sola vez por llamada a
        `get_commission_tracking`, reutilizado por todos los vendedores del período
        (mismo patrón que `CommissionSimulationService.reconstruir_mes_especifico`)."""
        assert self.commission_config_repo is not None
        fecha_config = fecha_referencia_periodo(anio, mes)
        return {
            "formula_componentes": resolver_componentes_formula(self.commission_config_repo),
            "matriz": self.commission_config_repo.get_matriz_as_reglas(fecha_config),
            # Retirado (Fase 3, R-7, auditoría 30 H4): factor de crédito sin datos
            # discriminantes reales. Lista vacía = factor neutro 1.0 en todo el motor
            # (ver `commission_engine._factor_credito`), sin consultar la tabla.
            "rangos_credito": [],
            "tramos_cumplimiento": resolver_tramos_cumplimiento(self.commission_config_repo, None, fecha_config),
        }

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
        """Fase 1 (R-1): calcula la comisión variable SIEMPRE, sin condicionar a
        `COMISION_MODO` -- antes esta ruta (a diferencia de `get_commission_tracking`
        desde la auditoría 46) solo la calculaba en modo "sombra"/"variable", dejando
        al vendedor sin ninguna cifra real mientras la empresa operaba en "plana"."""
        goal = self.goal_repo.get_goal_for_period(vendedor_origen, anio, mes)
        monto_meta = float(goal.monto_meta) if goal else 0.0
        venta_real = self.goal_repo.get_vendor_net_sales_period(vendedor_origen, anio, mes)

        assert self.commission_config_repo is not None
        cv = self._calcular_variable(vendedor_origen, anio, mes, venta_real, monto_meta)
        tasa_efectiva = round(cv.comision_final / venta_real * 100, 4) if venta_real > 0 else 0.0
        # `cv.pct_cumplimiento` puede ser `None` en un snapshot congelado ANTES de la
        # auditoría 45 (campo nuevo, dataclass con default `None`) -- se deriva
        # directamente de venta/meta como respaldo, nunca se compara `None >= 100`.
        pct_cumplimiento = cv.pct_cumplimiento if cv.pct_cumplimiento is not None else (
            round(venta_real / monto_meta * 100, 4) if monto_meta > 0 else 0.0
        )

        dias_restantes, en_ultima_semana = self._dias_restantes_mes(anio, mes)
        en_alerta = en_ultima_semana and pct_cumplimiento < UMBRAL_ALERTA_PCT

        mensaje: str | None = None
        if pct_cumplimiento >= 100:
            mensaje = "¡Meta superada este período!"
        elif en_alerta:
            faltante = max(0.0, monto_meta - venta_real)
            mensaje = f"¡Última semana! Necesitas vender {faltante:,.2f} más para alcanzar tu meta."

        return MiComision(
            vendedor_origen=vendedor_origen, anio=anio, mes=mes,
            monto_meta=round(monto_meta, 2), venta_real=round(venta_real, 2), pct_cumplimiento=pct_cumplimiento,
            nivel=cv.tramo_etiqueta or cv.nivel.value, tasa_aplicada_pct=tasa_efectiva, bono_aplicado=cv.bonos_total,
            comision_devengada=cv.comision_final, dias_restantes_mes=dias_restantes,
            en_alerta_cierre=en_alerta, mensaje_alerta=mensaje,
            desglose_variable=self._serializar_desglose(cv),
        )

    # `settings.COMISION_MODO` ("sombra"/"variable") es el mecanismo de rollback del
    # backend -- desde la Fase 1 del plan de Metas v3 y Comisiones Unificadas (R-1) el
    # esquema plano ya no es un modo válido (la comisión mostrada/calculada es siempre
    # la variable); lo único que `COMISION_MODO` sigue controlando es si el cálculo
    # además se PERSISTE como snapshot OFICIAL (dinero real) o solo como piloto en
    # "sombra". `comision_liquidaciones.modo` es un CHECK constraint de solo
    # ('sombra','oficial') -- vocabulario distinto a propósito del de `COMISION_MODO`
    # (la BD describe si la liquidación es un piloto o el cierre oficial, no el modo
    # del backend). El rollback de emergencia de R-1 (volver a no pagar nada mientras
    # se decide) es `COMISION_MODO=sombra`: calcula y muestra en todos los paneles,
    # nunca escribe un snapshot oficial.
    _MODO_BACKEND_A_LIQUIDACION = {"sombra": "sombra", "variable": "oficial"}

    @staticmethod
    def _es_periodo_actual(anio: int, mes: int) -> bool:
        hoy = datetime.date.today()
        return anio == hoy.year and mes == hoy.month

    # ── Motor variable (Comisiones Variables) ──────────────────────────────────────
    def _calcular_variable(
        self, vendedor_origen: str, anio: int, mes: int, venta_real: float, monto_meta: float,
        config_periodo: dict | None = None,
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
        config_periodo = config_periodo or {}
        resultado = calcular_comision_variable_completa(
            goal_repo=self.goal_repo, commission_config_repo=self.commission_config_repo,
            vendedor_origen=vendedor_origen, anio=anio, mes=mes,
            venta_real=venta_real, monto_meta=monto_meta, fecha_config=fecha_periodo,
            formula_componentes=config_periodo.get("formula_componentes"),
            matriz=config_periodo.get("matriz"), rangos_credito=config_periodo.get("rangos_credito"),
            tramos_cumplimiento=config_periodo.get("tramos_cumplimiento"),
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
            pct_cumplimiento=resultado.pct_cumplimiento,
            tramo_etiqueta=resultado.tramo.etiqueta if resultado.tramo else None,
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
        if modo_liquidacion is None:
            return
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
