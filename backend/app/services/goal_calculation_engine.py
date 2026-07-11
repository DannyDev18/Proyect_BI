# backend/app/services/goal_calculation_engine.py
"""Motor de cálculo estadístico de metas comerciales (docs/auditoria/14_fase0_analisis_
modulo_metas_comisiones.md, docs/auditoria/20_decomision_goals_rf.md). Es el generador
OFICIAL de la meta (`GoalMLService.generate_proposals`) -- estadística pura, sin ningún
modelo ML (el modelo `goals_rf` fue decomisionado): calcula una meta "base" robusta a
partir del histórico crudo del vendedor, filtrando eventos extraordinarios (picos de un
solo mes) para que no distorsionen el promedio. Es lógica de cálculo pura: no accede a la
BD ni al EDW -- recibe el histórico ya resuelto por el llamador (repositorio) y devuelve
un resultado serializable con la trazabilidad completa del cálculo (método, factores,
histórico usado).

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

# Tendencia de crecimiento/decrecimiento del vendedor (mediana de las variaciones
# intermensuales del segmento de tendencia -- ver `_factor_tendencia_bruto`): se acota igual
# que el capping ya validado de `GoalsService.predict_goal_amount` (0.8-1.2), pero un poco
# más conservador (0.85-1.20) porque aquí no hay un segundo capping posterior contra el
# promedio móvil -- este es el único filtro de sanidad de este método.
FACTOR_TENDENCIA_MIN = 0.85
FACTOR_TENDENCIA_MAX = 1.20
# Variabilidad del desempeño histórico (coeficiente de variación = desviación estándar /
# media del histórico limpio): a partir de este CV el vendedor se considera "errático" y su
# factor de tendencia se atenúa hacia 1.0 (no se le exige el mismo crecimiento que a un
# vendedor estable con la misma tendencia nominal).
CV_ALTO = 0.5
# Piso del peso de estabilidad: incluso con variabilidad extrema, se conserva al menos este
# 30% del efecto de la tendencia (nunca se anula del todo, solo se atenúa).
PESO_ESTABILIDAD_MIN = 0.3

# Ventana de tendencia reciente (docs/auditoria/20_...md): "meses recientes" son SIEMPRE
# los últimos N meses completos anteriores al mes objetivo, sin importar en qué mes del
# año calendario cae -- antes se usaban "los meses del año en curso", lo que en enero da 0
# meses de tendencia y en diciembre da 11, una ventana inconsistente que además diluye la
# tendencia real con meses muy viejos cuando el mes objetivo cae tarde en el año.
RECENT_TREND_MONTHS = 4
# Techo de sanidad de la meta final contra la tendencia reciente real (`componente_tendencia`):
# la estacionalidad (histórico de años previos, potencialmente con regímenes de venta muy
# distintos al actual -- ej. una tienda que redujo su volumen desde 2024) NUNCA debe poder
# empujar la meta muy por encima o muy por debajo de lo que el vendedor está vendiendo
# realmente ahora. Mismo espíritu que el capping 0.8-1.2 de `GoalsService.predict_goal_amount`
# contra el promedio móvil, aplicado aquí contra la tendencia reciente.
LIMITE_VS_TENDENCIA_MIN = 0.7
LIMITE_VS_TENDENCIA_MAX = 1.3

# Ventana de REFERENCIA para calcular los cuartiles de Tukey (docs/auditoria/20_...md):
# se calculan solo sobre los últimos 12 meses (el régimen de venta actual), no sobre toda
# la ventana de hasta 24 meses. Verificado contra un caso real del EDW: un vendedor con 2+
# años de ventas casi nulas (~$300-900/mes) y una recuperación sostenida real desde enero
# (~$5.000-9.000/mes, 6 meses seguidos) -- calcular Q1/Q3 sobre los 24 meses completos
# clasifica TODA la recuperación como "outlier alto" frente al pasado muerto y la excluye
# por completo, dejando la meta anclada al régimen viejo ya no representativo. Con la
# ventana de referencia acotada a 12 meses, una recuperación sostenida (varios meses)
# define sus propios cuartiles y no se autoexcluye; un pico de UN SOLO mes dentro de esos
# 12 meses sigue detectándose igual.
VENTANA_RECIENTE_OUTLIERS = 12


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
    # Trazabilidad de la propuesta para el siguiente mes (ver `_calcular_base_siguiente_mes`):
    # componente_estacional=None cuando no hay al menos un año previo con el mismo mes objetivo
    # (vendedor nuevo o histórico corto) -- en ese caso la meta se apoya solo en la tendencia.
    componente_estacional: float | None = None
    componente_tendencia: float = 0.0
    factor_tendencia_aplicado: float = 1.0
    coeficiente_variacion: float = 0.0


class GoalCalculationStrategy(Protocol):
    """Interfaz de estrategia de cálculo de metas. `IQRGoalCalculationEngine` es la
    implementación estadística actual; un futuro modelo ML (fuera de este alcance) puede
    implementar esta misma interfaz sin tocar a los consumidores del motor."""

    def calcular(
        self,
        vendedor_origen: str,
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
        if not ventana:
            raise ValidationError("Histórico insuficiente: no se recibió ningún mes de datos.")

        ventas_serie = [r.ventas for r in ventana]
        unidades_serie = [r.unidades for r in ventana]

        # Con menos de 4 puntos no hay resolución para cuartiles (`_indices_sin_outliers` ya
        # lo maneja devolviendo todos los índices); un vendedor nuevo con 1-2 meses de
        # histórico no debe romper el flujo (caso "vendedores nuevos" del enunciado) -- se
        # calcula igual, sin limpieza de outliers ni tendencia (ver `_factor_tendencia_bruto`).
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

        registros_limpios = [ventana[i] for i in indices_limpios]

        # Meta del "siguiente mes" (el que sigue al último dato disponible), combinando
        # estacionalidad (mismo mes de años anteriores) + tendencia (meses del año en curso),
        # con una corrección de tendencia de crecimiento/decrecimiento acotada y atenuada por
        # la variabilidad histórica -- ver `_calcular_base_siguiente_mes`.
        base_ventas, componente_estacional, componente_tendencia, factor_tendencia = self._calcular_base_siguiente_mes(
            registros_limpios, pesos, valor=lambda r: r.ventas,
        )
        base_unidades, _, componente_tendencia_unidades, _ = self._calcular_base_siguiente_mes(
            registros_limpios, pesos, valor=lambda r: r.unidades,
        ) if unidades_limpias else (promedio_unidades_limpio, None, 0.0, 1.0)

        coeficiente_variacion = self._coeficiente_variacion(ventas_limpias)

        # Techo/piso de sanidad contra la tendencia reciente real (docs/auditoria/20_...md):
        # la estacionalidad puede venir de un régimen de venta muy distinto al actual (ej.
        # un vendedor/almacén que vendía mucho más -o mucho menos- hace 1-2 años) y arrastrar
        # la base muy lejos de lo que el vendedor está vendiendo AHORA -- eso perjudica al
        # vendedor (meta inalcanzable) o desmotiva (meta trivial). Se acota la base estadística
        # (antes de aplicar los factores de negocio de estacionalidad/presión comercial, que sí
        # son un ajuste deliberado de gerencia y no deben recortarse) dentro de una banda
        # razonable alrededor de la tendencia reciente.
        base_ventas_sana = self._limitar_contra_tendencia(base_ventas * factor_tendencia, componente_tendencia)
        base_unidades_sana = self._limitar_contra_tendencia(base_unidades * factor_tendencia, componente_tendencia_unidades)

        factor_total = factor_estacional * factor_crecimiento
        meta_ventas_total = max(0.0, base_ventas_sana * factor_total)
        meta_unidades_total = max(0.0, base_unidades_sana * factor_total)

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
            componente_estacional=componente_estacional,
            componente_tendencia=componente_tendencia,
            factor_tendencia_aplicado=factor_tendencia,
            coeficiente_variacion=coeficiente_variacion,
        )

    @classmethod
    def _calcular_base_siguiente_mes(
        cls, registros_limpios: list[RegistroMensual], pesos: list[float], valor,
    ) -> tuple[float, float | None, float, float]:
        """Meta base para el mes siguiente al último dato disponible, combinando:

        - **Estacionalidad** (mismo mes en años anteriores dentro de la ventana, ya limpio
          de outliers): el promedio ponderado de esos meses. `None` si el vendedor no tiene
          al menos un año previo con ese mes (vendedor nuevo / histórico corto).
        - **Tendencia** (ventana RODANTE de los últimos `RECENT_TREND_MONTHS` meses
          completos, sin importar en qué mes calendario caiga -- antes eran "los meses del
          año en curso", inconsistente entre enero -0 meses previos- y diciembre -11-, y
          además diluía la tendencia real con meses viejos cuando el mes objetivo cae tarde
          en el año): captura si el vendedor viene creciendo o cayendo AHORA, no su nivel
          histórico plano.

        Si hay señal estacional, la base es el promedio de ambos componentes (peso 50/50);
        si no la hay, la base es puramente la tendencia reciente (fallback natural para
        vendedores nuevos, sin necesitar una rama de código aparte).

        Devuelve `(base, componente_estacional, componente_tendencia, factor_tendencia)`.
        El `factor_tendencia` solo se calcula sobre la serie de ventas (`valor=ventas`); para
        unidades se reutiliza el mismo factor en el llamador -- no tiene sentido una
        tendencia de crecimiento distinta para $ y unidades del mismo vendedor/mes."""
        if not registros_limpios:
            return 0.0, None, 0.0, 1.0

        ultimo = max(registros_limpios, key=lambda r: (r.anio, r.mes))
        mes_objetivo = 1 if ultimo.mes == 12 else ultimo.mes + 1

        pares_estacional = [(r, w) for r, w in zip(registros_limpios, pesos) if r.mes == mes_objetivo]
        componente_estacional = cls._promedio_ponderado([valor(r) for r, _ in pares_estacional], [w for _, w in pares_estacional]) if pares_estacional else None

        pares_tendencia = sorted(
            zip(registros_limpios, pesos), key=lambda rw: (rw[0].anio, rw[0].mes),
        )[-RECENT_TREND_MONTHS:]
        componente_tendencia = cls._promedio_ponderado([valor(r) for r, _ in pares_tendencia], [w for _, w in pares_tendencia])

        serie_tendencia_cronologica = [valor(r) for r, _ in sorted(pares_tendencia, key=lambda rw: (rw[0].anio, rw[0].mes))]
        factor_tendencia_bruto = cls._factor_tendencia_bruto(serie_tendencia_cronologica)
        peso_estabilidad = cls._peso_estabilidad([valor(r) for r in registros_limpios])
        factor_tendencia = 1.0 + (factor_tendencia_bruto - 1.0) * peso_estabilidad

        base = (componente_estacional + componente_tendencia) / 2.0 if componente_estacional is not None else componente_tendencia
        return base, componente_estacional, componente_tendencia, factor_tendencia

    @staticmethod
    def _factor_tendencia_bruto(serie_cronologica: list[float]) -> float:
        """Mediana de las variaciones intermensuales relativas (robusta a un mes puntual
        raro dentro del propio segmento de tendencia), acotada a
        `[FACTOR_TENDENCIA_MIN, FACTOR_TENDENCIA_MAX]`. Con menos de 2 puntos, o si todos los
        pares tienen un valor base 0 (mes sin ventas), no hay señal de tendencia -> neutro."""
        if len(serie_cronologica) < 2:
            return 1.0
        razones = [b / a for a, b in zip(serie_cronologica, serie_cronologica[1:]) if a > 0]
        if not razones:
            return 1.0
        return max(FACTOR_TENDENCIA_MIN, min(statistics.median(razones), FACTOR_TENDENCIA_MAX))

    @staticmethod
    def _peso_estabilidad(valores: list[float]) -> float:
        """Cuánto se deja actuar al factor de tendencia según la variabilidad del histórico
        (coeficiente de variación): un vendedor errático (CV alto) no debe recibir el mismo
        empuje de crecimiento que uno estable con la misma tendencia nominal -- se atenúa
        hacia 1.0 (neutro), nunca se anula del todo (piso `PESO_ESTABILIDAD_MIN`)."""
        cv = IQRGoalCalculationEngine._coeficiente_variacion(valores)
        if cv <= CV_ALTO:
            return 1.0
        exceso = min(cv - CV_ALTO, CV_ALTO)  # satura en 2x el umbral
        return max(PESO_ESTABILIDAD_MIN, 1.0 - exceso / CV_ALTO * (1.0 - PESO_ESTABILIDAD_MIN))

    @staticmethod
    def _limitar_contra_tendencia(meta: float, componente_tendencia: float) -> float:
        """Acota `meta` a `[LIMITE_VS_TENDENCIA_MIN, LIMITE_VS_TENDENCIA_MAX] * componente_tendencia`
        -- sin este techo/piso, un componente estacional muy alto o muy bajo (histórico de un
        régimen de venta distinto al actual) puede dominar la meta pese a que la tendencia
        reciente diga otra cosa. Sin tendencia positiva (vendedor sin histórico reciente
        limpio), no hay contra qué acotar -- se deja la meta tal cual."""
        if componente_tendencia <= 0:
            return meta
        piso = componente_tendencia * LIMITE_VS_TENDENCIA_MIN
        techo = componente_tendencia * LIMITE_VS_TENDENCIA_MAX
        return min(max(meta, piso), techo)

    @staticmethod
    def _coeficiente_variacion(valores: list[float]) -> float:
        if len(valores) < 2:
            return 0.0
        media = statistics.fmean(valores)
        if media <= 0:
            return 0.0
        return statistics.pstdev(valores) / media

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
        """Devuelve los índices de `serie` (orden cronológico ascendente) que caen dentro
        de las bandas de Tukey. Los cuartiles se calculan SOLO sobre los últimos
        `VENTANA_RECIENTE_OUTLIERS` meses -- ver la constante para el caso real que motivó
        esto. Con menos de 4 puntos de referencia no hay suficiente resolución estadística
        para cuartiles -- se usan todos los meses sin filtrar."""
        referencia = serie[-VENTANA_RECIENTE_OUTLIERS:] if len(serie) > VENTANA_RECIENTE_OUTLIERS else serie
        if len(referencia) < 4:
            return list(range(len(serie)))

        q1, _, q3 = statistics.quantiles(referencia, n=4, method="inclusive")
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
