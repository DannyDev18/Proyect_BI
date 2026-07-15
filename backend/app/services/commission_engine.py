# backend/app/services/commission_engine.py
"""Motor de cálculo de comisiones (docs/modulo_metas.md, "PROPUESTA IA" Fase 4; ver
docs/auditoria/17_comisiones_liquidacion.md). Lógica de cálculo pura: no accede a la BD --
recibe la venta real (Venta Neta) y la meta ya resueltas por el llamador (repositorio) y
devuelve el nivel de cumplimiento y la comisión devengada, con trazabilidad completa.

Resolución de una ambigüedad del enunciado (documentada en el reporte de auditoría): la nota
informal del módulo dice "si las ventas son menores a 90% no pagaría la comisión", pero la
sección detallada "PROPUESTA IA" (Fase 4, la versión elaborada del mismo documento) especifica
4 niveles donde el tramo 80-89% sí paga (5% base, sin bono). Se prioriza la versión detallada
por ser la especificación completa del mismo `.md`, no una regla nueva inventada."""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

# Umbrales de cumplimiento (fracción de la meta, no porcentaje) -- docs/modulo_metas.md,
# "PROPUESTA IA" Fase 1 y Fase 4.
UMBRAL_EXCELENTE = 1.0
UMBRAL_META = 0.9
UMBRAL_CERCA = 0.8

# La tasa de comisión configurada por meta (`Goal.comision_base_pct`, ya existente y editable
# por gerencia en `PUT /gerencia/goals/{id}/review`) es la tasa del tramo "Meta" (90-100%).
# Los otros tramos se derivan de ella como fracciones/adicionales, en vez de hardcodear
# porcentajes fijos (7%/5%/2%) que ignorarían la configuración real de cada vendedor/meta:
#   - Excelente (>=100%): tasa base + este adicional en puntos porcentuales, más el bono fijo
#     ya configurado en `Goal.bono_sobrecumplimiento` (docs/modulo_metas.md ejemplo: "7% base
#     + 2% adicional + bono de $500" -> el +2pp es el valor por defecto de esta constante).
BONUS_TASA_EXCELENTE_PP = 2.0
#   - Cerca (80-89%): fracción de la tasa base, sin bono. El enunciado ejemplifica 5% cuando
#     la tasa base es 7% (5/7 ≈ 0.714286); se generaliza esa misma proporción a cualquier
#     tasa base configurada.
FACTOR_TASA_CERCA = 5.0 / 7.0
#   - Lejos (<80%): 0% -- sin comisión, tal como especifica el enunciado sin ambigüedad.


class NivelCumplimiento(str, Enum):
    EXCELENTE = "EXCELENTE"
    META = "META"
    CERCA = "CERCA"
    LEJOS = "LEJOS"


@dataclass(frozen=True)
class ComisionCalculada:
    venta_real: float
    monto_meta: float
    pct_cumplimiento: float
    nivel: NivelCumplimiento
    tasa_aplicada_pct: float
    bono_aplicado: float
    comision_devengada: float


def calcular_nivel(pct_cumplimiento_fraccion: float) -> NivelCumplimiento:
    """`pct_cumplimiento_fraccion` es venta_real/monto_meta (1.0 = 100%), no porcentaje."""
    if pct_cumplimiento_fraccion >= UMBRAL_EXCELENTE:
        return NivelCumplimiento.EXCELENTE
    if pct_cumplimiento_fraccion >= UMBRAL_META:
        return NivelCumplimiento.META
    if pct_cumplimiento_fraccion >= UMBRAL_CERCA:
        return NivelCumplimiento.CERCA
    return NivelCumplimiento.LEJOS


def calcular_comision(
    venta_real: float, monto_meta: float, comision_base_pct: float, bono_sobrecumplimiento: float,
) -> ComisionCalculada:
    """Calcula el nivel de cumplimiento y la comisión devengada de un vendedor en un período.

    Sin meta configurada (`monto_meta <= 0`), no hay base para medir cumplimiento -- se
    devuelve LEJOS/0% en vez de dividir por cero o inventar un 100% arbitrario (ausencia de
    meta no es lo mismo que meta cumplida)."""
    if monto_meta <= 0:
        return ComisionCalculada(
            venta_real=venta_real, monto_meta=monto_meta, pct_cumplimiento=0.0,
            nivel=NivelCumplimiento.LEJOS, tasa_aplicada_pct=0.0, bono_aplicado=0.0,
            comision_devengada=0.0,
        )

    fraccion = venta_real / monto_meta
    nivel = calcular_nivel(fraccion)

    if nivel == NivelCumplimiento.EXCELENTE:
        tasa = comision_base_pct + BONUS_TASA_EXCELENTE_PP
        bono = bono_sobrecumplimiento
    elif nivel == NivelCumplimiento.META:
        tasa = comision_base_pct
        bono = 0.0
    elif nivel == NivelCumplimiento.CERCA:
        tasa = comision_base_pct * FACTOR_TASA_CERCA
        bono = 0.0
    else:
        tasa = 0.0
        bono = 0.0

    comision = max(0.0, venta_real) * (tasa / 100.0) + bono
    return ComisionCalculada(
        venta_real=venta_real, monto_meta=monto_meta, pct_cumplimiento=round(fraccion * 100, 2),
        nivel=nivel, tasa_aplicada_pct=round(tasa, 4), bono_aplicado=bono,
        comision_devengada=round(comision, 2),
    )


# ══════════════════════════════════════════════════════════════════════════════════
# Comisión Variable por Margen/Categoría (docs/features/plan_integracion_comisiones_
# variables.md, docs/auditoria/30_comisiones_variables.md). Función pura adicional que
# CONVIVE con `calcular_comision` (fallback/rollback vía `settings.COMISION_MODO`):
# reutiliza `calcular_nivel` como multiplicador de cumplimiento, no reimplementa tramos.
# ══════════════════════════════════════════════════════════════════════════════════
GRUPO_SERVICIO = "S"
GRUPO_EXCLUIDO = "X"
BASE_MARGEN = "margen"
BASE_VALOR = "valor"


@dataclass(frozen=True)
class LineaComisionable:
    """Una línea de venta ya resuelta por el repositorio (grano `fact_ventas_detalle`),
    con las columnas mínimas que necesita la clasificación (RN-CM1/RN-CM2)."""
    codart: str
    clase: str
    subclase: str | None
    es_servicio: bool
    subtotal_neto: float
    margen_bruto: float | None  # NULL cuando costo_total es NULL (salvaguarda 2)
    valor_descuento: float
    dias_plazo: int
    descuento_aprobado: bool = False


@dataclass(frozen=True)
class ReglaCategoria:
    """Una fila resuelta de `comision_matriz_categorias` (ya filtrada por vigencia)."""
    clase: str
    subclase: str | None
    grupo: str
    tasa_pct: float
    base: str
    factor_estrategico: float


@dataclass(frozen=True)
class RangoCredito:
    """Una fila resuelta de `comision_factores_credito` (ya filtrada por vigencia)."""
    dias_desde: int
    dias_hasta: int | None
    factor: float


@dataclass(frozen=True)
class ConfigComisionVariable:
    """Parámetros globales del motor variable (settings, sin hardcodes -- ver
    `app/core/config.py` §Comisiones Variables)."""
    tope_descuento_pct: float
    tasa_minima_sin_costo_pct: float
    umbral_subtotal_x: float
    mult_excelente: float
    mult_cerca: float
    piso_lejos: float
    grupo_default: str = "C"
    tasa_default_pct: float = 5.0


@dataclass(frozen=True)
class DesgloseLinea:
    codart: str
    grupo: str
    base_comisionable: float
    tasa_pct: float
    factor_estrategico: float
    factor_credito: float
    comision_linea: float
    sin_costo: bool
    pendiente_aprobacion: bool


@dataclass(frozen=True)
class ComisionVariableCalculada:
    comision_base: float          # Σ líneas antes del factor tipo/cumplimiento
    comision_post_tipo: float     # × factor_tipo_vendedor
    nivel: NivelCumplimiento
    multiplicador_cumplimiento: float
    comision_post_cumplimiento: float
    devoluciones_estimadas: float
    bonos_total: float
    comision_final: float
    desglose_lineas: tuple[DesgloseLinea, ...]


def _resolver_regla(clase: str, subclase: str | None, matriz: list[ReglaCategoria]) -> ReglaCategoria | None:
    """Match más específico gana: (clase, subclase) exacto > (clase, NULL) > ('*', NULL)."""
    por_subclase = [r for r in matriz if r.clase == clase and r.subclase == subclase and subclase is not None]
    if por_subclase:
        return por_subclase[0]
    por_clase = [r for r in matriz if r.clase == clase and r.subclase is None]
    if por_clase:
        return por_clase[0]
    comodin = [r for r in matriz if r.clase == "*" and r.subclase is None]
    return comodin[0] if comodin else None


def _factor_credito(dias_plazo: int, rangos: list[RangoCredito]) -> float:
    for r in rangos:
        if dias_plazo >= r.dias_desde and (r.dias_hasta is None or dias_plazo <= r.dias_hasta):
            return r.factor
    return 1.0  # sin rango configurado -> sin penalización (comportamiento neutro, no bloqueante)


def _calcular_linea(
    linea: LineaComisionable, matriz: list[ReglaCategoria], rangos_credito: list[RangoCredito],
    config: ConfigComisionVariable,
) -> DesgloseLinea:
    factor_credito = _factor_credito(linea.dias_plazo, rangos_credito)

    # Salvaguarda 1: descuento excesivo sin aprobación -> línea no comisiona.
    # `subtotal_neto` ya viene post-descuento (RN, ver etl/transformers/fact_transformer.py
    # "subtotal_neto = totren: SAP ya lo calcula post-descuento"); el % de descuento debe
    # medirse sobre el subtotal BRUTO (neto + descuento), no sobre el neto -- dividir por
    # el neto infla el porcentaje (auditoría 34, H-3: ej. 25% de descuento sobre bruto
    # calcula como 33.3% sobre neto, disparando el tope del 30% para descuentos legítimos).
    subtotal_bruto = linea.subtotal_neto + linea.valor_descuento
    pct_descuento = (linea.valor_descuento / subtotal_bruto * 100.0) if subtotal_bruto else 0.0
    if pct_descuento > config.tope_descuento_pct and not linea.descuento_aprobado:
        return DesgloseLinea(
            codart=linea.codart, grupo=GRUPO_EXCLUIDO, base_comisionable=0.0, tasa_pct=0.0,
            factor_estrategico=1.0, factor_credito=factor_credito, comision_linea=0.0,
            sin_costo=False, pendiente_aprobacion=True,
        )

    # RN-CM1/RN-CM3 (auditoría 30, H3): subtotal casi nulo -> grupo X, tasa 0.
    if abs(linea.subtotal_neto) < config.umbral_subtotal_x:
        return DesgloseLinea(
            codart=linea.codart, grupo=GRUPO_EXCLUIDO, base_comisionable=0.0, tasa_pct=0.0,
            factor_estrategico=1.0, factor_credito=factor_credito, comision_linea=0.0,
            sin_costo=False, pendiente_aprobacion=False,
        )

    if linea.es_servicio:
        base = max(0.0, linea.subtotal_neto)
        regla = _resolver_regla(linea.clase, linea.subclase, matriz)
        tasa = regla.tasa_pct if (regla and regla.grupo == GRUPO_SERVICIO) else config.tasa_default_pct
        factor_estrategico = regla.factor_estrategico if regla else 1.0
        comision = base * (tasa / 100.0) * factor_estrategico * factor_credito
        return DesgloseLinea(
            codart=linea.codart, grupo=GRUPO_SERVICIO, base_comisionable=base, tasa_pct=tasa,
            factor_estrategico=factor_estrategico, factor_credito=factor_credito,
            comision_linea=round(comision, 4), sin_costo=False, pendiente_aprobacion=False,
        )

    # Salvaguarda 2: línea sin costo -> margen no calculable, tasa mínima sobre el valor.
    if linea.margen_bruto is None:
        base = max(0.0, linea.subtotal_neto)
        comision = base * (config.tasa_minima_sin_costo_pct / 100.0) * factor_credito
        return DesgloseLinea(
            codart=linea.codart, grupo=config.grupo_default, base_comisionable=base,
            tasa_pct=config.tasa_minima_sin_costo_pct, factor_estrategico=1.0, factor_credito=factor_credito,
            comision_linea=round(comision, 4), sin_costo=True, pendiente_aprobacion=False,
        )

    regla = _resolver_regla(linea.clase, linea.subclase, matriz)
    grupo = regla.grupo if regla else config.grupo_default
    tasa = regla.tasa_pct if regla else config.tasa_default_pct
    factor_estrategico = regla.factor_estrategico if regla else 1.0
    base_config = regla.base if regla else BASE_MARGEN

    if grupo == GRUPO_EXCLUIDO:
        return DesgloseLinea(
            codart=linea.codart, grupo=GRUPO_EXCLUIDO, base_comisionable=0.0, tasa_pct=0.0,
            factor_estrategico=1.0, factor_credito=factor_credito, comision_linea=0.0,
            sin_costo=False, pendiente_aprobacion=False,
        )

    base = max(0.0, linea.subtotal_neto) if base_config == BASE_VALOR else max(0.0, linea.margen_bruto)
    comision = base * (tasa / 100.0) * factor_estrategico * factor_credito
    return DesgloseLinea(
        codart=linea.codart, grupo=grupo, base_comisionable=base, tasa_pct=tasa,
        factor_estrategico=factor_estrategico, factor_credito=factor_credito,
        comision_linea=round(comision, 4), sin_costo=False, pendiente_aprobacion=False,
    )


def calcular_comision_variable(
    lineas: list[LineaComisionable],
    matriz: list[ReglaCategoria],
    rangos_credito: list[RangoCredito],
    factor_tipo_vendedor: float,
    venta_real: float,
    monto_meta: float,
    devoluciones_mes: float,
    bonos_total: float,
    config: ConfigComisionVariable,
) -> ComisionVariableCalculada:
    """Fórmula completa (docs/features/plan_integracion_comisiones_variables.md §3.2):

    Σ líneas(base × tasa × factor_estratégico × factor_crédito) × factor_tipo_vendedor
      × multiplicador_cumplimiento(meta) − devoluciones_estimadas + bonos, piso $0.

    Pura -- sin acceso a BD; el llamador (servicio) resuelve `lineas`/`matriz`/
    `rangos_credito`/`bonos_total` desde los repositorios."""
    desglose = [_calcular_linea(l, matriz, rangos_credito, config) for l in lineas]
    comision_base = sum(d.comision_linea for d in desglose)
    comision_post_tipo = comision_base * factor_tipo_vendedor

    fraccion = (venta_real / monto_meta) if monto_meta > 0 else 0.0
    nivel = calcular_nivel(fraccion) if monto_meta > 0 else NivelCumplimiento.LEJOS

    if nivel == NivelCumplimiento.EXCELENTE:
        multiplicador = config.mult_excelente
    elif nivel == NivelCumplimiento.META:
        multiplicador = 1.0
    elif nivel == NivelCumplimiento.CERCA:
        multiplicador = config.mult_cerca
    else:
        multiplicador = config.piso_lejos

    comision_post_cumplimiento = comision_post_tipo * multiplicador

    # Devoluciones: se estima la comisión asociada con la tasa promedio ponderada real
    # de las líneas del mes (evita reabrir el cálculo línea a línea de las devoluciones,
    # que no comparten grano con `fact_ventas_detalle` -- ver GoalRepository).
    base_total = sum(d.base_comisionable for d in desglose)
    tasa_promedio_ponderada = (comision_base / base_total) if base_total > 0 else 0.0
    devoluciones_estimadas = max(0.0, devoluciones_mes) * tasa_promedio_ponderada

    comision_final = max(0.0, comision_post_cumplimiento - devoluciones_estimadas + bonos_total)

    return ComisionVariableCalculada(
        comision_base=round(comision_base, 4),
        comision_post_tipo=round(comision_post_tipo, 4),
        nivel=nivel,
        multiplicador_cumplimiento=round(multiplicador, 4),
        comision_post_cumplimiento=round(comision_post_cumplimiento, 4),
        devoluciones_estimadas=round(devoluciones_estimadas, 4),
        bonos_total=round(bonos_total, 4),
        comision_final=round(comision_final, 4),
        desglose_lineas=tuple(desglose),
    )
