# backend/app/services/goal_calculation_engine.py
"""Motor de cálculo estadístico de metas comerciales (docs/auditoria/14_fase0_analisis_
modulo_metas_comisiones.md). Complementa -- no reemplaza -- a `GoalsService`/`goals_rf_model`:
calcula una meta "base" robusta a partir del histórico crudo del vendedor, sin depender de
ningún modelo ML, filtrando eventos extraordinarios (picos de un solo mes) para que no
distorsionen el promedio. Es lógica de cálculo pura: no accede a la BD ni al EDW -- recibe el
histórico ya resuelto por el llamador (repositorio) y devuelve un resultado serializable con
la trazabilidad completa del cálculo (método, factores, histórico usado).

`GoalCalculationStrategy` es el punto de extensión: un futuro modelo ML puede implementar la
misma interfaz (`calcular(...) -> ResultadoCalculoMeta`) y sustituir a `IQRGoalCalculationEngine`
sin que el consumidor cambie."""
from __future__ import annotations

import statistics
from dataclasses import dataclass, field
from typing import Protocol

from app.core.exceptions import ValidationError

METODO_ESTADISTICO_IQR = "estadistico_iqr_v1"
# Integración ML (Metas y Comisiones): cuando el detector de anomalías (IsolationForest,
# ml/contracts/models/anomalies.json) señala meses con transacciones atípicas, ese mes
# NO se elimina del histórico (a diferencia de un outlier IQR) -- solo pesa menos en el
# promedio. METODO_ESTADISTICO_IQR_ML identifica los resultados calculados con esa señal.
METODO_ESTADISTICO_IQR_ML = "estadistico_iqr_ml_v1"
PESO_MES_ATIPICO_ML = 0.5

# Ventana de histórico: mínimo exigido por reglas de negocio del enunciado (12-24 meses).
MESES_VENTANA_MIN = 12
MESES_VENTANA_MAX = 24
# Multiplicador estándar de Tukey para las bandas del IQR.
IQR_MULTIPLICADOR = 1.5
# Umbral de cobertura acumulada (regla 80/20) para marcar productos como "estratégicos".
UMBRAL_PARTICIPACION_ESTRATEGICA = 0.80


@dataclass(frozen=True)
class RegistroMensual:
    """Un mes de histórico de un vendedor, opcionalmente desagregado por categoría/producto.
    `categoria`/`producto` en `None` representan el registro agregado del mes (usado para el
    cálculo del total); si se quiere desglose, el llamador entrega además una fila por
    categoría/producto para ese mismo `(anio, mes)`."""
    anio: int
    mes: int
    ventas: float
    unidades: float
    categoria: str | None = None
    producto: str | None = None


@dataclass(frozen=True)
class DesgloseCalculado:
    clave: str
    meta_ventas: float
    meta_unidades: float
    participacion_historica_pct: float


@dataclass(frozen=True)
class ResultadoCalculoMeta:
    """Resultado completo del cálculo, con la trazabilidad exigida por el enunciado
    ("guardar método utilizado, factores aplicados, histórico usado") lista para que un
    caller la persista (ej. como JSON en una columna de auditoría) sin recalcular nada."""
    vendedor_origen: str
    sucursal: str
    meta_ventas_total: float
    meta_unidades_total: float
    metodo: str
    factor_estacional_aplicado: float
    factor_crecimiento_aplicado: float
    meses_historico_usados: int
    valores_atipicos_excluidos: int
    promedio_historico_limpio: float
    mediana_historico: float
    historico_usado: list[RegistroMensual]
    metas_por_categoria: list[DesgloseCalculado] = field(default_factory=list)
    metas_por_producto: list[DesgloseCalculado] = field(default_factory=list)
    productos_estrategicos: list[str] = field(default_factory=list)
    meses_atipicos_ml_detectados: int = 0


class GoalCalculationStrategy(Protocol):
    """Interfaz de estrategia de cálculo de metas. `IQRGoalCalculationEngine` es la
    implementación estadística actual; un futuro modelo ML (fuera de este alcance) puede
    implementar esta misma interfaz sin tocar a los consumidores del motor."""

    def calcular(
        self,
        vendedor_origen: str,
        sucursal: str,
        historico: list[RegistroMensual],
        factor_estacional: float = 1.0,
        factor_crecimiento: float = 1.0,
    ) -> ResultadoCalculoMeta: ...


class IQRGoalCalculationEngine:
    """Calcula `meta_base = promedio(histórico limpio de outliers vía IQR)`, luego aplica
    `factor_estacional` y `factor_crecimiento`. Un outlier es un mes cuya venta cae fuera de
    `[Q1 - 1.5*IQR, Q3 + 1.5*IQR]` (regla de Tukey) sobre la ventana de los últimos
    12-24 meses -- así un mes extraordinario (liquidación, evento puntual) no arrastra la meta
    del resto del año."""

    def calcular(
        self,
        vendedor_origen: str,
        sucursal: str,
        historico: list[RegistroMensual],
        factor_estacional: float = 1.0,
        factor_crecimiento: float = 1.0,
        meses_atipicos_ml: frozenset[tuple[int, int]] | None = None,
    ) -> ResultadoCalculoMeta:
        if factor_estacional <= 0 or factor_crecimiento <= 0:
            raise ValidationError("factor_estacional y factor_crecimiento deben ser positivos.")

        # El registro agregado del mes es el que no trae categoría/producto -- es la serie
        # base para calcular meta_base. Las filas con categoría/producto son el desglose.
        mensual = [r for r in historico if r.categoria is None and r.producto is None]
        if not mensual:
            raise ValidationError(
                "Histórico insuficiente: se requiere al menos un registro mensual agregado "
                "(sin categoría/producto) para calcular la meta base."
            )

        ventana = self._tomar_ultimos_meses(mensual, MESES_VENTANA_MAX)
        if len(ventana) < 3:
            raise ValidationError(
                f"Histórico insuficiente: se requieren al menos 3 meses de datos, se recibieron {len(ventana)}."
            )

        ventas_serie = [r.ventas for r in ventana]
        unidades_serie = [r.unidades for r in ventana]

        indices_limpios = self._indices_sin_outliers(ventas_serie)
        ventas_limpias = [ventas_serie[i] for i in indices_limpios]
        unidades_limpias = [unidades_serie[i] for i in indices_limpios]

        # Señal ML (IsolationForest, integración Metas y Comisiones): los meses con
        # transacciones anómalas NO se excluyen (a diferencia de un outlier IQR) -- solo
        # pesan menos en el promedio, exactamente lo que pide el enunciado ("reducir su
        # influencia", no eliminar).
        meses_atipicos_ml = meses_atipicos_ml or frozenset()
        pesos = [
            PESO_MES_ATIPICO_ML if (ventana[i].anio, ventana[i].mes) in meses_atipicos_ml else 1.0
            for i in indices_limpios
        ]
        meses_atipicos_en_ventana = sum(1 for i in indices_limpios if (ventana[i].anio, ventana[i].mes) in meses_atipicos_ml)

        promedio_ventas_limpio = self._promedio_ponderado(ventas_limpias, pesos)
        promedio_unidades_limpio = self._promedio_ponderado(unidades_limpias, pesos) if unidades_limpias else 0.0
        mediana_ventas = statistics.median(ventas_serie)

        factor_total = factor_estacional * factor_crecimiento
        meta_ventas_total = max(0.0, promedio_ventas_limpio * factor_total)
        meta_unidades_total = max(0.0, promedio_unidades_limpio * factor_total)

        detalle_categoria = [r for r in historico if r.categoria is not None]
        detalle_producto = [r for r in historico if r.producto is not None]

        metas_por_categoria = self._distribuir_por_participacion(
            detalle_categoria, key=lambda r: r.categoria, meta_ventas_total=meta_ventas_total,
            meta_unidades_total=meta_unidades_total,
        )
        metas_por_producto = self._distribuir_por_participacion(
            detalle_producto, key=lambda r: r.producto, meta_ventas_total=meta_ventas_total,
            meta_unidades_total=meta_unidades_total,
        )
        productos_estrategicos = self._productos_estrategicos(metas_por_producto)

        return ResultadoCalculoMeta(
            vendedor_origen=vendedor_origen,
            sucursal=sucursal,
            meta_ventas_total=meta_ventas_total,
            meta_unidades_total=meta_unidades_total,
            metodo=METODO_ESTADISTICO_IQR_ML if meses_atipicos_ml else METODO_ESTADISTICO_IQR,
            factor_estacional_aplicado=factor_estacional,
            factor_crecimiento_aplicado=factor_crecimiento,
            meses_historico_usados=len(ventana),
            valores_atipicos_excluidos=len(ventana) - len(indices_limpios),
            promedio_historico_limpio=promedio_ventas_limpio,
            mediana_historico=mediana_ventas,
            historico_usado=ventana,
            metas_por_categoria=metas_por_categoria,
            metas_por_producto=metas_por_producto,
            productos_estrategicos=productos_estrategicos,
            meses_atipicos_ml_detectados=meses_atipicos_en_ventana,
        )

    @staticmethod
    def _promedio_ponderado(valores: list[float], pesos: list[float]) -> float:
        suma_pesos = sum(pesos)
        if suma_pesos <= 0:
            return statistics.fmean(valores)
        return sum(v * w for v, w in zip(valores, pesos)) / suma_pesos

    @staticmethod
    def _tomar_ultimos_meses(mensual: list[RegistroMensual], max_meses: int) -> list[RegistroMensual]:
        ordenado = sorted(mensual, key=lambda r: (r.anio, r.mes))
        return ordenado[-max_meses:]

    @staticmethod
    def _indices_sin_outliers(serie: list[float]) -> list[int]:
        """Devuelve los índices de `serie` que caen dentro de las bandas de Tukey. Con menos
        de 4 puntos no hay suficiente resolución estadística para cuartiles -- se usan todos."""
        if len(serie) < 4:
            return list(range(len(serie)))

        q1, _, q3 = statistics.quantiles(serie, n=4, method="inclusive")
        iqr = q3 - q1
        limite_inferior = q1 - IQR_MULTIPLICADOR * iqr
        limite_superior = q3 + IQR_MULTIPLICADOR * iqr

        indices = [i for i, v in enumerate(serie) if limite_inferior <= v <= limite_superior]
        # Si el IQR es 0 (serie casi constante) o el filtro deja la serie vacía por algún
        # borde numérico, no dejar la meta sin datos: usar la serie completa.
        return indices if indices else list(range(len(serie)))

    @staticmethod
    def _distribuir_por_participacion(
        detalle: list[RegistroMensual],
        key,
        meta_ventas_total: float,
        meta_unidades_total: float,
    ) -> list[DesgloseCalculado]:
        """Reparte la meta total entre categorías/productos según su participación histórica
        en ventas dentro de `detalle` (ya filtrado a la ventana relevante por el llamador)."""
        if not detalle:
            return []

        totales: dict[str, float] = {}
        for r in detalle:
            k = key(r)
            totales[k] = totales.get(k, 0.0) + r.ventas
        suma_total = sum(totales.values())
        if suma_total <= 0:
            return []

        return sorted(
            (
                DesgloseCalculado(
                    clave=k,
                    meta_ventas=meta_ventas_total * (v / suma_total),
                    meta_unidades=meta_unidades_total * (v / suma_total),
                    participacion_historica_pct=v / suma_total,
                )
                for k, v in totales.items()
            ),
            key=lambda d: d.participacion_historica_pct,
            reverse=True,
        )

    @staticmethod
    def _productos_estrategicos(metas_por_producto: list[DesgloseCalculado]) -> list[str]:
        """Regla 80/20: los productos que acumulan hasta el 80% de la participación
        histórica (ya vienen ordenados desc.) se consideran estratégicos para la meta."""
        acumulado = 0.0
        estrategicos = []
        for d in metas_por_producto:
            if acumulado >= UMBRAL_PARTICIPACION_ESTRATEGICA:
                break
            estrategicos.append(d.clave)
            acumulado += d.participacion_historica_pct
        return estrategicos
