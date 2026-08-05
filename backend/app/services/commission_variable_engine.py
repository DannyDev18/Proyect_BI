# backend/app/services/commission_variable_engine.py
"""Motor de orquestación de la Comisión Variable COMPLETA (auditoría 44,
docs/features/plan_comisiones_sobre_cobros.md -- corrección de diseño 2026-07-30):
las comisiones variables son UN SOLO TOTAL por vendedor, resultado de SUMAR todos los
componentes configurados (líneas de venta por margen/categoría, cobranza por tramo de
días de cobro, ventas de contado de agencia) -- no dos esquemas alternativos entre los
que gerencia "activa" uno u otro. Hay UNA sola fórmula vigente (`public.comision_formula`,
a lo sumo una fila real hoy); lo que SÍ es configurable es la estructura de esa fórmula
(qué componentes suma/resta/multiplica y en qué orden).

Extraído de `CommissionService`/`CommissionSimulationService` para que ambos usen
EXACTAMENTE el mismo cálculo -- antes el simulador llamaba directo a
`commission_engine.calcular_comision_variable` (solo líneas de venta) y nunca reflejaba
la cobranza ni el contado de agencia, subestimando sistemáticamente lo que gerencia
vería como "argumento decisivo" para ajustar tramos/tasas."""
from __future__ import annotations

import datetime
from dataclasses import dataclass
from typing import NamedTuple

from app.core.config import settings
from app.repositories.commission_config_repository import CommissionConfigRepository
from app.repositories.goal_repository import GoalRepository
from app.services.commission_bonus import calcular_bonos_periodo
from app.services.commission_engine import (
    UMBRAL_CERCA, UMBRAL_EXCELENTE, UMBRAL_META, CobroComisionable, ConfigComisionVariable, DesgloseLinea,
    DesgloseTramoCobranza, LineaComisionable, NivelCumplimiento, PasoFormula, TramoCumplimiento,
    calcular_base_lineas_venta, calcular_comision_cobranza, calcular_contado_agencia, calcular_nivel,
    evaluar_formula, resolver_meta_sin_ajuste_tipo, resolver_tramo_cumplimiento,
)


class _ComponenteDefault(NamedTuple):
    """Fallback defensivo si `public.comision_formula` no tiene ninguna fila activa
    (dato borrado a mano) -- reproduce la estructura mínima histórica (líneas de venta ×
    tipo × cumplimiento − devoluciones + bonos) para no dejar a un vendedor sin comisión
    por un problema de configuración. En operación normal SIEMPRE hay una fila real."""
    orden: int
    componente: str
    operador: str
    activo: bool
    parametros: dict


COMPONENTES_FALLBACK = (
    _ComponenteDefault(1, "base_lineas_venta", "sumar", True, {}),
    _ComponenteDefault(2, "factor_tipo_vendedor", "multiplicar", True, {}),
    _ComponenteDefault(3, "multiplicador_cumplimiento", "multiplicar", True, {}),
    _ComponenteDefault(4, "devoluciones", "restar", True, {}),
    _ComponenteDefault(5, "bonos", "sumar", True, {}),
)


# Fallback defensivo si `public.comision_tramos_cumplimiento` no tiene ninguna fila
# vigente (dato borrado a mano) -- reproduce byte a byte el comportamiento de los 4
# tramos fijos que el motor usaba antes de la auditoría 45 (`UMBRAL_*`/
# `COMISION_MULT_*`), NO el umbral de 90%/escala de sobrecumplimiento nuevos: es una
# red de seguridad para no dejar a un vendedor sin comisión por un problema de
# configuración, no una forma de reintroducir CERCA=0.7x a propósito.
TRAMOS_CUMPLIMIENTO_FALLBACK = (
    TramoCumplimiento(0.0, UMBRAL_CERCA * 100, settings.COMISION_PISO_LEJOS, "Lejos (fallback)"),
    TramoCumplimiento(UMBRAL_CERCA * 100, UMBRAL_META * 100, settings.COMISION_MULT_CERCA, "Cerca (fallback)"),
    TramoCumplimiento(UMBRAL_META * 100, UMBRAL_EXCELENTE * 100, 1.0, "Meta (fallback)"),
    TramoCumplimiento(UMBRAL_EXCELENTE * 100, None, settings.COMISION_MULT_EXCELENTE, "Excelente (fallback)"),
)


@dataclass(frozen=True)
class ResultadoComisionVariable:
    montos: dict[str, float]
    nivel: NivelCumplimiento
    desglose_lineas: tuple[DesgloseLinea, ...]
    desglose_cobranza: tuple[DesgloseTramoCobranza, ...] | None
    comision_final: float
    traza_formula: tuple[dict, ...]
    # Auditoría 45: el tramo de cumplimiento efectivamente aplicado (etiqueta,
    # multiplicador, bono fijo) y el % de cumplimiento sobre el que se resolvió --
    # `nivel`/`NivelCumplimiento` se conservan sin cambios por compatibilidad con
    # `ComisionVariableCalculada`/los snapshots ya congelados; estos campos son la
    # fuente real del multiplicador desde la auditoría 45.
    pct_cumplimiento: float = 0.0
    tramo: TramoCumplimiento | None = None


def resolver_componentes_formula(commission_config_repo: CommissionConfigRepository):
    """La fórmula (a diferencia de la matriz de categorías o los factores de crédito) NO
    tiene vigencia por fecha -- es LA fórmula vigente en este momento, sin importar qué
    período se esté calculando. Los llamadores que iteran sobre muchos vendedores/
    períodos (el simulador) deben resolverla UNA SOLA VEZ y pasarla como
    `formula_componentes` a `calcular_comision_variable_completa`, en vez de dejar que
    cada llamada dispare su propia consulta."""
    formula_activa = commission_config_repo.get_formula_activa()
    return formula_activa[1] if formula_activa is not None else COMPONENTES_FALLBACK


def resolver_tramos_cumplimiento(
    commission_config_repo: CommissionConfigRepository, perfil: str | None, fecha_config: datetime.date,
) -> list[TramoCumplimiento]:
    """Igual que `resolver_componentes_formula` pero para los tramos de cumplimiento
    (auditoría 45): los llamadores que iteran muchos vendedores/períodos (el
    simulador) deben resolverlos UNA vez por período/perfil y pasarlos como
    `tramos_cumplimiento`. A diferencia de la fórmula, los tramos SÍ tienen vigencia
    por fecha (igual que la matriz de categorías) -- se resuelven a `fecha_config`, no
    "hoy"."""
    tramos = commission_config_repo.get_tramos_cumplimiento_as_tramos(perfil, fecha_config)
    return tramos if tramos else list(TRAMOS_CUMPLIMIENTO_FALLBACK)


def calcular_comision_variable_completa(
    *,
    goal_repo: GoalRepository,
    commission_config_repo: CommissionConfigRepository,
    vendedor_origen: str, anio: int, mes: int,
    venta_real: float, monto_meta: float,
    fecha_config: datetime.date,
    fecha_config_vendedor_meta: datetime.date | None = None,
    aplicar_ajuste_meta_por_tipo: bool = True,
    incluir_bonos: bool = True,
    incluir_devoluciones: bool = True,
    formula_componentes=None,
    matriz=None,
    rangos_credito=None,
    tramos_cumplimiento=None,
) -> ResultadoComisionVariable:
    """Resuelve el monto real de CADA componente activo de la fórmula vigente y evalúa
    la tubería declarativa (`evaluar_formula`) -- usado tanto por el cálculo real
    (`CommissionService`) como por el simulador (`CommissionSimulationService`), para que
    ambos calculen exactamente lo mismo.

    `fecha_config`: fecha a la que se resuelven matriz de categorías, factores de
    crédito, tramos de cobranza, tramos de cumplimiento y (salvo que se pase
    `fecha_config_vendedor_meta`) el tipo/factor/agencia del vendedor -- "vigente al
    cierre del período" en el cálculo real, "vigente hoy" en la reconstrucción
    retroactiva de un mes específico.
    `fecha_config_vendedor_meta`: caso especial de `reconstruir_mes_especifico` -- el
    tipo de vendedor para DESHACER el ajuste de la meta debe ser el vigente EN ESE
    período histórico, no el de hoy, aunque el resto de la configuración sí sea la de hoy.
    `aplicar_ajuste_meta_por_tipo`: la proyección hacia adelante fuerza
    `venta_real == monto_meta` para un cumplimiento neutro y NO debe pasar esa meta por
    `resolver_meta_sin_ajuste_tipo` (dividiría por el factor y rompería la neutralidad).
    `incluir_bonos`/`incluir_devoluciones`: la proyección los omite a propósito (eventos
    puntuales del mes ya cerrado, no un patrón proyectable).
    `formula_componentes`/`matriz`/`rangos_credito`/`tramos_cumplimiento`: pre-resueltos
    por el llamador cuando itera muchos vendedores de un mismo período (el simulador) --
    evita repetir la misma consulta de vigencia una vez por vendedor. `None` (el caso de
    `CommissionService`, una sola vez por llamada) los resuelve aquí mismo."""
    componentes = formula_componentes if formula_componentes is not None else resolver_componentes_formula(commission_config_repo)
    activos = [c for c in componentes if c.activo]
    claves_activas = {c.componente for c in activos}

    config_vendedor = commission_config_repo.get_config_vendedor(vendedor_origen, fecha_config)
    perfil = config_vendedor.tipo if config_vendedor else settings.COMISION_PERFIL_COBRANZA_DEFAULT

    montos: dict[str, float] = {}
    desglose_cobranza: tuple[DesgloseTramoCobranza, ...] | None = None
    desglose_lineas: tuple[DesgloseLinea, ...] = ()

    if "base_cobranza" in claves_activas:
        cobros_repo = goal_repo.get_cobros_periodo(vendedor_origen, anio, mes)
        cobros = [CobroComisionable(valor_cobrado=c.valor_cobrado, dias_cobro=c.dias_cobro) for c in cobros_repo]
        tramos = commission_config_repo.get_tramos_cobranza_as_rangos(perfil, fecha_config)
        resultado_cobranza = calcular_comision_cobranza(cobros, tramos)
        montos["base_cobranza"] = resultado_cobranza.comision_total
        desglose_cobranza = resultado_cobranza.desglose_tramos

    if "contado_agencia" in claves_activas:
        agencia = config_vendedor.agencia if config_vendedor else None
        if agencia:
            comp = next(c for c in activos if c.componente == "contado_agencia")
            pct = float((comp.parametros or {}).get("pct", 1.0))
            ventas_contado = goal_repo.get_ventas_contado_agencia(vendedor_origen, agencia, anio, mes)
            montos["contado_agencia"] = calcular_contado_agencia(ventas_contado, pct)
        else:
            # Vendedor sin agencia configurada (no es jefe de agencia, o falta el dato):
            # el componente queda en 0, nunca se inventa una agencia (R-2 del plan).
            montos["contado_agencia"] = 0.0

    if "base_lineas_venta" in claves_activas:
        lineas_repo = goal_repo.get_commission_lines(vendedor_origen, anio, mes)
        lineas = [
            LineaComisionable(
                codart=l.codart, clase=l.clase, subclase=l.subclase, es_servicio=l.es_servicio,
                subtotal_neto=l.subtotal_neto, margen_bruto=l.margen_bruto,
                valor_descuento=l.valor_descuento, dias_plazo=l.dias_plazo,
            )
            for l in lineas_repo
        ]
        matriz_resuelta = matriz if matriz is not None else commission_config_repo.get_matriz_as_reglas(fecha_config)
        # Retirado (Fase 3, R-7, auditoría 30 H4): el factor de plazo de crédito no
        # discrimina nada real (solo hay datos de 0 y 30 días en el EDW) -- ya no se
        # consulta `comision_factores_credito`; `_factor_credito` es neutro (1.0)
        # sin importar qué se pase aquí.
        rangos_credito_resueltos: list = []
        config = ConfigComisionVariable(
            tope_descuento_pct=settings.COMISION_TOPE_DESCUENTO_PCT,
            tasa_minima_sin_costo_pct=settings.COMISION_TASA_MINIMA_SIN_COSTO_PCT,
            umbral_subtotal_x=settings.COMISION_UMBRAL_SUBTOTAL_X,
            mult_excelente=settings.COMISION_MULT_EXCELENTE, mult_cerca=settings.COMISION_MULT_CERCA,
            piso_lejos=settings.COMISION_PISO_LEJOS,
        )
        montos["base_lineas_venta"], desglose_lineas = calcular_base_lineas_venta(
            lineas, matriz_resuelta, rangos_credito_resueltos, config,
        )

    if "factor_tipo_vendedor" in claves_activas:
        montos["factor_tipo_vendedor"] = (
            float(config_vendedor.factor_tipo) if config_vendedor else settings.COMISION_FACTOR_EXTERNO_DEFAULT
        )

    nivel = NivelCumplimiento.LEJOS
    pct_cumplimiento = 0.0
    tramo: TramoCumplimiento | None = None
    if "multiplicador_cumplimiento" in claves_activas:
        if aplicar_ajuste_meta_por_tipo:
            config_vendedor_meta = (
                commission_config_repo.get_config_vendedor(vendedor_origen, fecha_config_vendedor_meta)
                if fecha_config_vendedor_meta is not None else config_vendedor
            )
            meta_cumplimiento = resolver_meta_sin_ajuste_tipo(
                monto_meta, config_vendedor_meta.tipo if config_vendedor_meta else None,
                config_vendedor_meta.fecha_ingreso if config_vendedor_meta else None, anio, mes,
                settings.COMISION_META_FACTOR_EXTERNO, settings.COMISION_META_FACTOR_INTERNO,
                settings.COMISION_VENDEDOR_NUEVO_MESES,
            )
        else:
            meta_cumplimiento = monto_meta
        fraccion = (venta_real / meta_cumplimiento) if meta_cumplimiento > 0 else 0.0
        # `nivel`/`NivelCumplimiento` se conservan sin cambios (compatibilidad con
        # `ComisionVariableCalculada`/snapshots ya congelados) -- el multiplicador
        # REAL desde la auditoría 45 sale de `tramo`, resuelto en % (no fracción).
        nivel = calcular_nivel(fraccion) if meta_cumplimiento > 0 else NivelCumplimiento.LEJOS
        pct_cumplimiento = round(fraccion * 100, 4)
        tramos_resueltos = (
            tramos_cumplimiento if tramos_cumplimiento is not None
            else resolver_tramos_cumplimiento(commission_config_repo, perfil, fecha_config)
        )
        tramo = resolver_tramo_cumplimiento(pct_cumplimiento, tramos_resueltos)
        montos["multiplicador_cumplimiento"] = tramo.multiplicador

    if "devoluciones" in claves_activas:
        if incluir_devoluciones:
            devoluciones_mes = goal_repo.get_vendor_devoluciones_period(vendedor_origen, anio, mes)
            # Sin líneas de venta en la fórmula no hay una tasa ponderada real que
            # escalar (la devolución afecta la VENTA, no el cobro) -- se expone el monto
            # completo, documentado, en vez de inventar una proporción sin base real.
            if "base_lineas_venta" in claves_activas:
                base_total = sum(d.base_comisionable for d in desglose_lineas)
                tasa_prom = (montos["base_lineas_venta"] / base_total) if base_total > 0 else 0.0
                montos["devoluciones"] = round(max(0.0, devoluciones_mes) * tasa_prom, 4)
            else:
                montos["devoluciones"] = round(max(0.0, devoluciones_mes), 4)
        else:
            montos["devoluciones"] = 0.0

    bonos_total = 0.0
    if "bonos" in claves_activas:
        if incluir_bonos:
            # Referencia del bono de cobranza sana ("% ADICIONAL SOBRE LA COMISIÓN"):
            # el acumulado de la tubería justo ANTES del paso 'devoluciones' (no antes de
            # 'bonos') -- generaliza `comision_post_cumplimiento` del motor legacy
            # (Σbases × factor_tipo × multiplicador, previo a restar devoluciones) a
            # cualquier combinación de componentes activos, en el orden configurado.
            pasos_ordenados = sorted(activos, key=lambda c: c.orden)
            idx_devoluciones = next(
                (i for i, c in enumerate(pasos_ordenados) if c.componente == "devoluciones"), None,
            )
            pasos_referencia = (
                pasos_ordenados[:idx_devoluciones] if idx_devoluciones is not None
                else [c for c in pasos_ordenados if c.componente != "bonos"]
            )
            pasos_referencia_formula = [
                PasoFormula(c.orden, c.componente, c.operador, montos.get(c.componente, 0.0)) for c in pasos_referencia
            ]
            referencia_bonos = evaluar_formula(pasos_referencia_formula).comision_final
            bonos_total = calcular_bonos_periodo(goal_repo, vendedor_origen, anio, mes, referencia_bonos)
            # Bono fijo del tramo de cumplimiento alcanzado (auditoría 45, §3.2 punto 2
            # del plan) -- sembrado en $0, se suma aquí solo si gerencia lo activa desde
            # el panel. Se omite en la proyección igual que los demás bonos
            # (`incluir_bonos=False`): es un evento del mes ya cerrado, no proyectable.
            if tramo is not None:
                bonos_total = round(bonos_total + tramo.bono_fijo, 4)
        montos["bonos"] = bonos_total

    pasos = [PasoFormula(c.orden, c.componente, c.operador, montos.get(c.componente, 0.0)) for c in activos]
    resultado = evaluar_formula(pasos)

    # Compuerta de cumplimiento sobre la comisión COMPLETA (docs/features/
    # plan_motor_metas_v3_y_comisiones_unificadas.md, Fase 2, R-2, auditoría 47 §1.3):
    # antes, `bonos` era un paso `sumar` POSTERIOR al `multiplicar` de
    # `multiplicador_cumplimiento` en la tubería -- un vendedor bajo el umbral de pago
    # (tramo con multiplicador 0.0, "Sin comisión") igual cobraba el 100% de sus bonos,
    # dejando RN-CM16 ("no comisiona bajo el 90%") falsa en la práctica para ese
    # componente. La regla de negocio es literal: "si no alcanza la meta, no
    # comisiona" -- sin excepción para bonos. Se aplica como compuerta FINAL sobre el
    # resultado ya acumulado (bonos incluidos), no reordenando la tubería configurable
    # (que sigue calculando exactamente lo mismo para cualquier tramo con
    # multiplicador > 0 -- Meta, Sobrecumplimiento -- donde el gate no cambia nada).
    comision_final = resultado.comision_final
    traza_formula = resultado.pasos
    if "multiplicador_cumplimiento" in claves_activas and tramo is not None and tramo.multiplicador <= 0.0:
        comision_final = 0.0
        # Bug real encontrado en vivo (auditoría 47, continuación de la Fase 2): la
        # compuerta ya forzaba `comision_final=0.0`, pero la TRAZA (`traza_formula`,
        # expuesta al usuario como el desglose "componentes" de cada vendedor) seguía
        # mostrando `evaluar_formula` operando sobre el acumulado sin la compuerta --
        # `devoluciones`/`bonos` posteriores al paso `multiplicador_cumplimiento`
        # aparecían restando/sumando sobre un acumulado que ya debía estar en $0,
        # terminando en un "acumulado_tras_paso" final distinto de cero pese a que
        # `comision_devengada` real era $0 -- gerencia veía un desglose que parecía
        # decir "este vendedor sí cobra $X" contradiciendo el total mostrado. Se
        # reescribe la traza desde el paso `multiplicador_cumplimiento` (inclusive) en
        # adelante para que quede en $0, consistente con la comisión final real.
        pasos_reescritos = []
        compuerta_alcanzada = False
        for paso in traza_formula:
            if paso["componente"] == "multiplicador_cumplimiento":
                compuerta_alcanzada = True
            pasos_reescritos.append({**paso, "acumulado_tras_paso": 0.0} if compuerta_alcanzada else paso)
        traza_formula = tuple(pasos_reescritos)

    return ResultadoComisionVariable(
        montos=montos, nivel=nivel, desglose_lineas=desglose_lineas, desglose_cobranza=desglose_cobranza,
        comision_final=comision_final, traza_formula=traza_formula,
        pct_cumplimiento=pct_cumplimiento, tramo=tramo,
    )
