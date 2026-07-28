# backend/app/services/metricas/comparador.py
"""Comparación temporal transversal (G-04, docs/features/plan_madurez_bi_toma_decisiones.md).

*"Un número solo no es un indicador; lo es cuando se compara."* Antes de esto la comparativa
existía en exactamente 4 campos de Gerencia, contra un solo período de referencia (el
anterior de igual longitud) y solo si el usuario fijaba fechas explícitas.

Este módulo generaliza el patrón `_tendencia_pct` que estaba duplicado en
`analytics_service.py` y `warehouse_service.py`, y agrega los modos que el negocio necesita:

- `periodo_anterior` — ventana previa de igual longitud (comportamiento histórico, default).
- `anio_anterior` — **mismo** período del año anterior. Es el relevante en un negocio
  estacional; el proyecto documenta ~31% de crecimiento 2018→2026 (regla 11), así que
  comparar marzo contra febrero mezcla estacionalidad con tendencia.
- `promedio_n_periodos` — promedio de los N períodos previos de igual longitud, para suavizar
  un mes atípico.

**Criterio de aceptación de G-04:** el `None` (sin base comparable) se comunica
explícitamente en vez de mostrarse como 0% — un 0% se lee como "no cambió", que es una
afirmación distinta a "no hay con qué compararlo".
"""
import datetime
from dataclasses import dataclass
from enum import Enum
from typing import Final

# Número de períodos que promedia el modo `promedio_n_periodos` cuando no se especifica otro.
N_PERIODOS_DEFAULT: Final = 3
# Tope defensivo: cada período extra es una consulta más al EDW.
N_PERIODOS_MAX: Final = 12


class ModoComparacion(str, Enum):
    PERIODO_ANTERIOR = "periodo_anterior"
    ANIO_ANTERIOR = "anio_anterior"
    PROMEDIO_N_PERIODOS = "promedio_n_periodos"


@dataclass(frozen=True)
class Ventana:
    """Un rango de fechas ISO (inclusivo en ambos extremos), como los espera el repositorio."""
    desde: str
    hasta: str

    @property
    def dias(self) -> int:
        return (datetime.date.fromisoformat(self.hasta) - datetime.date.fromisoformat(self.desde)).days + 1


@dataclass(frozen=True)
class Comparacion:
    """Resultado de comparar un valor contra su referencia.

    `variacion_pct` es `None` cuando no hay base de comparación significativa; `motivo_sin_base`
    explica por qué, para que la UI pueda decirlo en vez de pintar un 0%.
    """
    valor: float | None
    referencia: float | None
    variacion_pct: float | None
    modo: ModoComparacion
    ventana_referencia: Ventana | None
    motivo_sin_base: str | None = None


def _restar_anios(fecha_iso: str, anios: int) -> str:
    """Resta años preservando el día. El 29 de febrero de un bisiesto no existe en el año
    anterior: se degrada al 28, que es la convención contable habitual."""
    f = datetime.date.fromisoformat(fecha_iso)
    try:
        return f.replace(year=f.year - anios).isoformat()
    except ValueError:
        return f.replace(year=f.year - anios, day=28).isoformat()


def ventana_anterior(desde: str, hasta: str) -> Ventana:
    """Ventana previa de igual longitud, inmediatamente anterior. Mismo cálculo que el
    `_periodo_anterior` original de `analytics_service.py`, ahora en un solo lugar."""
    d = datetime.date.fromisoformat(desde)
    h = datetime.date.fromisoformat(hasta)
    delta = h - d
    hasta_prev = d - datetime.timedelta(days=1)
    return Ventana((hasta_prev - delta).isoformat(), hasta_prev.isoformat())


def ventana_anio_anterior(desde: str, hasta: str) -> Ventana:
    """Mismo período del año anterior (comparación interanual)."""
    return Ventana(_restar_anios(desde, 1), _restar_anios(hasta, 1))


def ventanas_n_anteriores(desde: str, hasta: str, n: int = N_PERIODOS_DEFAULT) -> list[Ventana]:
    """Las N ventanas previas de igual longitud, de la más reciente a la más antigua."""
    n = max(1, min(n, N_PERIODOS_MAX))
    ventanas: list[Ventana] = []
    cursor_desde, cursor_hasta = desde, hasta
    for _ in range(n):
        v = ventana_anterior(cursor_desde, cursor_hasta)
        ventanas.append(v)
        cursor_desde, cursor_hasta = v.desde, v.hasta
    return ventanas


def ventanas_de_referencia(
    desde: str, hasta: str, modo: ModoComparacion, n: int = N_PERIODOS_DEFAULT,
) -> list[Ventana]:
    """Ventanas del EDW que hay que consultar para construir la referencia del modo dado.
    El caller ejecuta la consulta (este módulo no toca la BD) y pasa los valores a `comparar`."""
    if modo is ModoComparacion.ANIO_ANTERIOR:
        return [ventana_anio_anterior(desde, hasta)]
    if modo is ModoComparacion.PROMEDIO_N_PERIODOS:
        return ventanas_n_anteriores(desde, hasta, n)
    return [ventana_anterior(desde, hasta)]


def variacion_pct(actual: float | None, referencia: float | None) -> float | None:
    """% de cambio contra la referencia, o `None` si no hay base significativa.

    Se exige `referencia > 0`: con una referencia de 0 la variación es infinita, y con una
    negativa el signo del cociente se invierte y un empeoramiento se leería como mejora.
    Es el mismo criterio que ya usaban `AnalyticsService._tendencia_pct` y
    `WarehouseService._tendencia_pct`, ahora unificado.
    """
    if actual is None or referencia is None or referencia <= 0:
        return None
    return round((actual - referencia) / referencia * 100, 1)


def comparar(
    valor: float | None,
    valores_referencia: list[float | None],
    modo: ModoComparacion,
    ventanas: list[Ventana],
) -> Comparacion:
    """Ensambla el resultado a partir de los valores ya consultados al EDW."""
    limpios = [v for v in valores_referencia if v is not None]
    ventana_ref = ventanas[0] if ventanas else None

    if valor is None:
        return Comparacion(None, None, None, modo, ventana_ref,
                           "El período consultado no tiene datos.")
    if not limpios:
        return Comparacion(valor, None, None, modo, ventana_ref,
                           "No hay datos en el período de referencia.")

    referencia = sum(limpios) / len(limpios)
    pct = variacion_pct(valor, referencia)
    motivo = None if pct is not None else "La referencia es cero o negativa: no hay base porcentual."
    return Comparacion(valor, round(referencia, 2), pct, modo, ventana_ref, motivo)
