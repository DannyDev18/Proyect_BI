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
