# backend/app/services/goal_calculation_engine.py
"""Motor de cálculo estadístico de metas comerciales (docs/auditoria/14_fase0_analisis_
modulo_metas_comisiones.md, docs/auditoria/20_decomision_goals_rf.md, docs/auditoria/
46_motor_metas_configurable.md, docs/features/plan_motor_metas_configurable.md). Es el
generador OFICIAL de la meta (`GoalMLService.generate_proposals`) -- estadística pura,
sin ningún modelo ML (el modelo `goals_rf` fue decomisionado): calcula una meta "base"
robusta a partir del histórico crudo del vendedor, filtrando eventos extraordinarios
(picos de un solo mes) para que no distorsionen el promedio. Es lógica de cálculo pura:
no accede a la BD ni al EDW -- recibe el histórico ya resuelto por el llamador
(repositorio) y devuelve un resultado serializable con la trazabilidad completa del
cálculo (método, factores, histórico usado).

**Motor v2 (auditoría 46, RN-MT1..RN-MT6):** reemplaza el diseño anterior ("promedio del
mismo mes de años previos" + "promedio de los últimos 4 meses", combinados 50/50) por la
descomposición clásica de series de tiempo -- nivel × índice estacional × tendencia
(Hyndman & Athanasopoulos, *Forecasting: Principles and Practice*) -- con una banda de
alcanzabilidad explícita sobre la meta FINAL (Zoltners, Sinha & Lorimer, *The Complete
Guide to Sales Force Incentive Compensation*, quota setting bottom-up). Corrige 3
defectos confirmados en la auditoría 46: (H-1) el mes objetivo ya no se infiere como
"el que sigue al último dato" sino que lo determina el llamador explícitamente (el
período que Gerencia realmente pidió); (H-3) el único techo/piso del diseño anterior se
aplicaba ANTES de los factores de negocio (presión comercial, tipo de vendedor), dejando
la meta final sin ningún guardarraíl -- ahora la banda se aplica sobre el resultado
completo; (H-4) la tendencia se calculaba sobre la serie CRUDA (mezclando estacionalidad
real con el efecto de un mes extraordinario) -- ahora se calcula sobre la serie
DESESTACIONALIZADA, y además la propia meta queda acotada contra una referencia robusta
(mediana reciente), no solo contra su propia tendencia.

`GoalCalculationStrategy` es el punto de extensión: un futuro modelo ML puede implementar la
misma interfaz (`calcular(...) -> ResultadoCalculoMeta`) y sustituir a `IQRGoalCalculationEngine`
sin que el consumidor cambie."""
from __future__ import annotations

import statistics
from dataclasses import dataclass, field
from typing import Protocol

from app.core.exceptions import ValidationError

# ── Etiquetas de método (persistidas en `metodo`, mostradas en la UI) ──────────────────
# Legado (histórico, se conserva para no romper metas ya generadas con el motor v1):
METODO_ESTADISTICO_IQR = "estadistico_iqr_v1"
METODO_ESTADISTICO_IQR_ML = "estadistico_iqr_ml_v1"

# Escalera de degradación del motor v2 (docs/features/plan_motor_metas_configurable.md
# §5.3): explícita y visible, en vez de tres fallbacks silenciosos indistinguibles entre
# sí (H-6). Cada etiqueta le dice al gerente EXACTAMENTE con qué respaldo estadístico se
# calculó esa meta puntual.
METODO_ESTACIONAL_PROPIO = "estacional_propio_v2"
METODO_ESTACIONAL_EMPRESA = "estacional_empresa_v2"
METODO_TENDENCIA_ROBUSTA = "tendencia_robusta_v2"
METODO_EQUIPO_PRORRATEADO = "equipo_prorrateado_v2"
METODO_SIN_HISTORICO = "sin_historico"

# Integración ML (Metas y Comisiones): cuando `meses_atipicos_ml` señala meses con
# comportamiento atípico, ese mes NO se elimina del histórico (a diferencia de un outlier
# IQR) -- solo pesa menos en el promedio (regla de negocio: "reducir su influencia", no
# eliminar). El único emisor real de esa señal era el modelo `anomaly` (IsolationForest),
# decomisionado por completo (docs/auditoria/51_decomision_anomaly_y_churn_unico.md) --
# `GoalMLService` ya no llama a este parámetro con nada más que el default vacío, así
# que este peso queda inerte hasta que otra fuente de meses atípicos lo alimente. Se
# conserva (no se retira el parámetro del motor) porque es un mecanismo genérico del
# motor v2, no exclusivo de ese modelo -- retirarlo habría sido un cambio de contrato
# más amplio que decomisionar el modelo en sí.
PESO_MES_ATIPICO_ML = 0.5


@dataclass(frozen=True)
class MetaMotorParametros:
    """Parámetros configurables del motor v2 (docs/features/plan_motor_metas_configurable.md
    §5.5): el gerente los edita vía `public.metas_config_parametros` (CRUD con vigencia,
    mismo patrón ya probado en Comisiones Variables -- auditoría 44/45); esta clase es la
    representación en memoria que consume el motor puro, con los valores por defecto =
    semilla inicial validada en la auditoría 46 (A-0.3/A-0.5)."""

    # Ventana de histórico (docs/auditoria/46_..., A-0.3: con 36 meses el 80.6% de los
    # pares (vendedor, mes-calendario) ya tienen >=2 años de ese mismo mes -- suficiente
    # para un índice estacional propio en la mayoría de vendedores activos).
    ventana_meses: int = 36
    # Ventana de REFERENCIA para calcular los cuartiles de Tukey (sobre la serie ya
    # desestacionalizada) -- no toda la ventana completa, para no diluir un pico reciente
    # entre años de historia ya irrelevante.
    ventana_referencia_outliers: int = 12
    iqr_multiplicador: float = 1.5
    # Años mínimos de observaciones del mismo mes calendario para construir un índice
    # estacional PROPIO del vendedor para ese mes puntual; si no alcanza, ese mes cae al
    # índice de empresa (mezcla parcial mes a mes, no todo-o-nada).
    min_anios_estacional: int = 2
    # Ventana rodante para el factor de tendencia: los últimos N meses (desestacionalizados)
    # inmediatamente anteriores al mes objetivo, sin importar en qué mes calendario caen.
    meses_tendencia_reciente: int = 4
    factor_tendencia_min: float = 0.85
    factor_tendencia_max: float = 1.20
    # Variabilidad histórica (CV) a partir de la cual se atenúa el efecto de la tendencia.
    cv_alto: float = 0.5
    peso_estabilidad_min: float = 0.3
    # Banda de alcanzabilidad (RN-MT3, corrige H-3): la meta FINAL (tras todos los
    # factores de negocio) se acota a [banda_min, banda_max] × referencia_alcanzable.
    banda_alcanzabilidad_min: float = 0.85
    banda_alcanzabilidad_max: float = 1.20
    # Referencia_alcanzable = mediana desestacionalizada de los últimos N meses (sin
    # ponderar por señales ML -- una referencia de alcanzabilidad debe ser conservadora,
    # no artificialmente reducida) × índice estacional del mes objetivo.
    meses_referencia_alcanzable: int = 6
    # Con menos meses que este mínimo no hay resolución estadística para cuartiles.
    meses_minimos_para_iqr: int = 4
    umbral_participacion_estrategica: float = 0.80


DEFAULT_PARAMETROS = MetaMotorParametros()

# ── Etapa E6 -- madurez del vendedor (docs/features/plan_motor_metas_v3_y_comisiones_
# unificadas.md §10/§18-E6, R-8; auditoría 47 A-0.4: 42% de los vendedores activos
# tiene < 6 meses de historia, 4 de 24 con 0 meses -- más severo que lo estimado en el
# plan original). Reemplaza el escalón único que tenía `GoalMLService.
# _ajustar_meta_por_tipo` ("< COMISION_VENDEDOR_NUEVO_MESES -> benchmark puro, si no ->
# 100% propio") por una transición GRADUAL de 4 tramos, evitando el salto brusco que un
# vendedor sufría al cruzar el umbral de un mes a otro.
METODO_MADUREZ_BENCHMARK_PURO = "benchmark_puro_v3"
METODO_MADUREZ_MEZCLA_GRADUAL = "mezcla_gradual_v3"
METODO_MADUREZ_MEZCLA_ESTABLE = "mezcla_estable_v3"
METODO_MADUREZ_PROPIO = "propio_v3"


@dataclass(frozen=True)
class ResultadoMadurez:
    meta_ajustada: float
    metodo: str
    peso_propio: float


def ajustar_meta_por_madurez(
    meta_propia: float,
    benchmark_equipo: float,
    meses_antiguedad: int | None,
    umbral_nuevo_meses: int = 6,
    umbral_maduro_meses: int = 24,
    peso_propio_intermedio: float = 0.80,
) -> ResultadoMadurez:
    """`meses_antiguedad=None` (sin `fecha_ingreso` registrada, dato de catálogo
    incompleto) se trata como vendedor maduro -- ausencia de dato no es lo mismo que
    "vendedor nuevo", y penalizar con benchmark a alguien solo porque falta un campo
    administrativo sería un efecto colateral no deseado (RN-MT9: nunca se inventa un
    factor por falta de datos, se degrada explícitamente o se usa el propio histórico
    si es lo único disponible).

    - `0` meses -> benchmark puro (sin histórico propio que promediar).
    - `1..umbral_nuevo_meses-1` -> mezcla lineal `w·propio + (1-w)·benchmark`,
      `w = meses/umbral_nuevo_meses` (transición gradual, no un escalón).
    - `umbral_nuevo_meses..umbral_maduro_meses-1` -> mezcla fija (`peso_propio_intermedio`).
    - `>= umbral_maduro_meses` (o `None`) -> propio puro."""
    if meses_antiguedad is None or meses_antiguedad >= umbral_maduro_meses:
        return ResultadoMadurez(meta_propia, METODO_MADUREZ_PROPIO, 1.0)
    if meses_antiguedad <= 0:
        return ResultadoMadurez(benchmark_equipo, METODO_MADUREZ_BENCHMARK_PURO, 0.0)
    if meses_antiguedad < umbral_nuevo_meses:
        peso = meses_antiguedad / umbral_nuevo_meses
        return ResultadoMadurez(
            peso * meta_propia + (1 - peso) * benchmark_equipo, METODO_MADUREZ_MEZCLA_GRADUAL, peso,
        )
    return ResultadoMadurez(
        peso_propio_intermedio * meta_propia + (1 - peso_propio_intermedio) * benchmark_equipo,
        METODO_MADUREZ_MEZCLA_ESTABLE, peso_propio_intermedio,
    )


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
    # Trazabilidad de la propuesta para el período objetivo (ver `_indice_estacional_mes`
    # / `_factor_tendencia_bruto`): componente_estacional=None cuando no hay ninguna señal
    # estacional (propia ni de empresa) para el mes objetivo -- vendedor nuevo o histórico
    # corto, empresa entera sin datos de ese mes en la ventana.
    componente_estacional: float | None = None
    componente_tendencia: float = 0.0
    factor_tendencia_aplicado: float = 1.0
    coeficiente_variacion: float = 0.0
    # Campos nuevos del motor v2 (auditoría 46, RN-MT1..RN-MT4):
    anio_objetivo: int = 0
    mes_objetivo: int = 0
    indice_estacional_aplicado: float = 1.0
    fuente_indice_estacional: str = "neutro"  # "propio" | "empresa" | "neutro"
    referencia_alcanzable: float = 0.0
    banda_actuo: bool = False
    meta_pre_banda: float = 0.0


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
    """Motor v2: `meta = clamp(nivel_base × índice_estacional(mes_objetivo) ×
    factor_tendencia × factor_presion × factor_tipo, banda_min×ref, banda_max×ref)`,
    donde `nivel_base` es el promedio ponderado (tras excluir outliers de Tukey y
    atenuar meses atípicos ML) de la serie histórica ya DESESTACIONALIZADA, y `ref`
    (`referencia_alcanzable`) es la mediana desestacionalizada reciente × el mismo
    índice estacional -- "lo que este vendedor vende realmente en un mes como este"."""

    def calcular(
        self,
        vendedor_origen: str,
        historico: list[RegistroMensual],
        anio_objetivo: int | None = None,
        mes_objetivo: int | None = None,
        factor_estacional: float = 1.0,
        factor_crecimiento: float = 1.0,
        meses_atipicos_ml: frozenset[tuple[int, int]] | None = None,
        indice_estacional_empresa: dict[int, float] | None = None,
        parametros: MetaMotorParametros = DEFAULT_PARAMETROS,
        aplicar_limpieza: bool = True,
        aplicar_estacionalidad: bool = True,
        aplicar_tendencia: bool = True,
        aplicar_estabilidad: bool = True,
        aplicar_banda: bool = True,
    ) -> ResultadoCalculoMeta:
        """`aplicar_*` (docs/features/plan_motor_metas_v3_y_comisiones_unificadas.md §9,
        Fase 6): interruptores de las etapas E1/E3/E4/E5/E10 del pipeline v3 -- todos
        `True` por defecto, reproduce exactamente el motor v2 (comportamiento sin cambios
        para cualquier llamador que no los pase explícitamente). `False` en cualquiera de
        ellos hace que esa etapa sea neutra (sin excluir outliers, sin desestacionalizar,
        sin tendencia, sin atenuar por estabilidad, sin banda de alcanzabilidad),
        controlado por `MetaConfigModuloService` vía `metas_config_modulos.activo`."""
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

        # H-1 (auditoría 46): el período objetivo lo determina el LLAMADOR (el mes que
        # Gerencia efectivamente pidió), nunca "el mes siguiente al último dato" -- ese
        # comportamiento legado solo se conserva si el caller no pasa el período
        # explícito (compatibilidad de la función pura para pruebas/comparación).
        if anio_objetivo is None or mes_objetivo is None:
            ultimo = max(mensual, key=lambda r: (r.anio, r.mes))
            mes_objetivo = 1 if ultimo.mes == 12 else ultimo.mes + 1
            anio_objetivo = ultimo.anio + 1 if ultimo.mes == 12 else ultimo.anio

        # Ventana: los últimos `ventana_meses` ESTRICTAMENTE ANTERIORES al objetivo --
        # nunca se usa el propio mes objetivo (o meses posteriores) como insumo, evita
        # fugas si el histórico llegara a incluir un mes parcial en curso.
        anteriores = sorted(
            (r for r in mensual if (r.anio, r.mes) < (anio_objetivo, mes_objetivo)),
            key=lambda r: (r.anio, r.mes),
        )
        ventana = anteriores[-parametros.ventana_meses:]
        if not ventana:
            raise ValidationError("Histórico insuficiente: no se recibió ningún mes de datos anterior al período objetivo.")

        # ── Índice estacional (propio del vendedor, con respaldo de empresa mes a mes) ──
        indices_propios = self._indice_estacional_propio(ventana, parametros.min_anios_estacional)
        indice_estacional_empresa = indice_estacional_empresa or {}

        def indice_de(mes: int) -> tuple[float, str]:
            if not aplicar_estacionalidad:
                return 1.0, "neutro"
            if mes in indices_propios:
                return indices_propios[mes], "propio"
            if mes in indice_estacional_empresa and indice_estacional_empresa[mes] > 0:
                return indice_estacional_empresa[mes], "empresa"
            return 1.0, "neutro"

        indice_objetivo, fuente_objetivo = indice_de(mes_objetivo)

        # ── Desestacionalizar la ventana completa (ventas y unidades) ───────────────────
        ventas_deseason = [r.ventas / indice_de(r.mes)[0] for r in ventana]
        unidades_deseason = [r.unidades / indice_de(r.mes)[0] for r in ventana]

        # Con menos puntos que `meses_minimos_para_iqr` no hay resolución para cuartiles
        # (`_indices_sin_outliers` ya lo maneja devolviendo todos los índices); un
        # vendedor nuevo con 1-2 meses de histórico no debe romper el flujo.
        indices_limpios = (
            self._indices_sin_outliers(
                ventas_deseason, parametros.ventana_referencia_outliers, parametros.iqr_multiplicador, parametros.meses_minimos_para_iqr,
            )
            if aplicar_limpieza else list(range(len(ventas_deseason)))
        )

        meses_atipicos_ml = meses_atipicos_ml or frozenset()
        pesos = [
            PESO_MES_ATIPICO_ML if (ventana[i].anio, ventana[i].mes) in meses_atipicos_ml else 1.0
            for i in indices_limpios
        ]
        meses_atipicos_en_ventana = sum(1 for i in indices_limpios if (ventana[i].anio, ventana[i].mes) in meses_atipicos_ml)

        ventas_deseason_limpias = [ventas_deseason[i] for i in indices_limpios]
        unidades_deseason_limpias = [unidades_deseason[i] for i in indices_limpios]
        ventana_limpia = [ventana[i] for i in indices_limpios]

        nivel_base_ventas = self._promedio_ponderado(ventas_deseason_limpias, pesos)
        nivel_base_unidades = self._promedio_ponderado(unidades_deseason_limpias, pesos) if unidades_deseason_limpias else 0.0
        promedio_ventas_limpio = statistics.fmean([ventana[i].ventas for i in indices_limpios]) if indices_limpios else 0.0
        mediana_ventas = statistics.median([r.ventas for r in ventana])

        # ── Tendencia reciente, sobre la serie YA desestacionalizada (RN-MT4, corrige H-4:
        # antes se calculaba sobre la serie cruda, y un mes extraordinario reciente podía
        # empujar tendencia Y factor de tendencia a la vez) ────────────────────────────
        pares_tendencia = list(zip(ventana_limpia, ventas_deseason_limpias))[-parametros.meses_tendencia_reciente:]
        serie_tendencia = [v for _, v in pares_tendencia]
        factor_tendencia_bruto = (
            self._factor_tendencia_bruto(serie_tendencia, parametros.factor_tendencia_min, parametros.factor_tendencia_max)
            if aplicar_tendencia else 1.0
        )
        peso_estabilidad = (
            self._peso_estabilidad(ventas_deseason_limpias, parametros.cv_alto, parametros.peso_estabilidad_min)
            if aplicar_estabilidad else 1.0
        )
        factor_tendencia = 1.0 + (factor_tendencia_bruto - 1.0) * peso_estabilidad

        coeficiente_variacion = self._coeficiente_variacion(ventas_deseason_limpias)

        # ── Fórmula v2: nivel × índice_estacional × tendencia × negocio ─────────────────
        componente_estacional = nivel_base_ventas * indice_objetivo if fuente_objetivo != "neutro" or nivel_base_ventas > 0 else None
        componente_estacional_monto = nivel_base_ventas * indice_objetivo
        componente_tendencia_monto = componente_estacional_monto * factor_tendencia

        meta_pre_banda = componente_tendencia_monto * factor_estacional * factor_crecimiento
        meta_unidades_pre_banda = (nivel_base_unidades * indice_objetivo * factor_tendencia) * factor_estacional * factor_crecimiento

        # ── Banda de alcanzabilidad sobre la meta FINAL (RN-MT3, corrige H-3) ───────────
        referencia_alcanzable = self._mediana(
            ventas_deseason_limpias[-parametros.meses_referencia_alcanzable:]
        ) * indice_objetivo

        if aplicar_banda:
            meta_ventas_total, banda_actuo = self._aplicar_banda(
                meta_pre_banda, referencia_alcanzable, parametros.banda_alcanzabilidad_min, parametros.banda_alcanzabilidad_max,
            )
        else:
            meta_ventas_total, banda_actuo = meta_pre_banda, False
        # Unidades: misma banda relativa (proporcional a su propia referencia).
        referencia_alcanzable_unidades = self._mediana(
            unidades_deseason_limpias[-parametros.meses_referencia_alcanzable:]
        ) * indice_objetivo if unidades_deseason_limpias else 0.0
        if aplicar_banda:
            meta_unidades_total, _ = self._aplicar_banda(
                meta_unidades_pre_banda, referencia_alcanzable_unidades, parametros.banda_alcanzabilidad_min, parametros.banda_alcanzabilidad_max,
            )
        else:
            meta_unidades_total = meta_unidades_pre_banda
        meta_ventas_total = max(0.0, meta_ventas_total)
        meta_unidades_total = max(0.0, meta_unidades_total)

        # ── Escalera de degradación (RN-MT2, corrige H-6): etiqueta explícita según el
        # respaldo estadístico real disponible para ESTE mes objetivo puntual ──────────
        metodo = self._determinar_metodo(
            meses_historico_usados=len(ventana), fuente_indice=fuente_objetivo,
            meses_atipicos_ml=meses_atipicos_ml, meses_minimos_para_iqr=parametros.meses_minimos_para_iqr,
        )

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
        productos_estrategicos = self._productos_estrategicos(metas_por_producto, parametros.umbral_participacion_estrategica)

        return ResultadoCalculoMeta(
            vendedor_origen=vendedor_origen,
            meta_ventas_total=meta_ventas_total,
            meta_unidades_total=meta_unidades_total,
            metodo=metodo,
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
            componente_tendencia=componente_tendencia_monto,
            factor_tendencia_aplicado=factor_tendencia,
            coeficiente_variacion=coeficiente_variacion,
            anio_objetivo=anio_objetivo,
            mes_objetivo=mes_objetivo,
            indice_estacional_aplicado=indice_objetivo,
            fuente_indice_estacional=fuente_objetivo,
            referencia_alcanzable=referencia_alcanzable,
            banda_actuo=banda_actuo,
            meta_pre_banda=meta_pre_banda,
        )

    @staticmethod
    def _determinar_metodo(
        meses_historico_usados: int, fuente_indice: str, meses_atipicos_ml: frozenset, meses_minimos_para_iqr: int,
    ) -> str:
        if meses_historico_usados < meses_minimos_para_iqr:
            return METODO_EQUIPO_PRORRATEADO
        if fuente_indice == "propio":
            base = METODO_ESTACIONAL_PROPIO
        elif fuente_indice == "empresa":
            base = METODO_ESTACIONAL_EMPRESA
        else:
            base = METODO_TENDENCIA_ROBUSTA
        return base

    @staticmethod
    def _indice_estacional_propio(ventana: list[RegistroMensual], min_anios: int) -> dict[int, float]:
        """Ratio-to-moving-average clásico: por cada mes calendario con >= `min_anios`
        observaciones de años distintos dentro de la ventana, `índice(mes) = promedio(ventas
        de ese mes) / promedio general de la ventana`. Se calcula mes a mes (no todo-o-nada):
        un vendedor puede tener índice propio confiable para unos meses y no para otros --
        los meses sin señal propia caen al índice de empresa en el llamador. Los índices
        calculados se normalizan para que su propio promedio sea 1.0 (evita que el índice
        general de la ventana quede sesgado si solo hay señal para unos pocos meses)."""
        por_mes: dict[int, list[tuple[int, float]]] = {}
        for r in ventana:
            por_mes.setdefault(r.mes, []).append((r.anio, r.ventas))

        todas_las_ventas = [v for pares in por_mes.values() for _, v in pares]
        if not todas_las_ventas:
            return {}
        promedio_general = statistics.fmean(todas_las_ventas)
        if promedio_general <= 0:
            return {}

        crudos: dict[int, float] = {}
        for mes, pares in por_mes.items():
            anios_distintos = {a for a, _ in pares}
            if len(anios_distintos) >= min_anios:
                promedio_mes = statistics.fmean(v for _, v in pares)
                crudos[mes] = promedio_mes / promedio_general

        if not crudos:
            return {}
        escala = 1.0 / statistics.fmean(crudos.values())
        return {mes: indice * escala for mes, indice in crudos.items()}

    @staticmethod
    def _factor_tendencia_bruto(serie_cronologica: list[float], factor_min: float, factor_max: float) -> float:
        """Mediana de las variaciones intermensuales relativas (robusta a un mes puntual
        raro dentro del propio segmento de tendencia), acotada a `[factor_min, factor_max]`.
        Con menos de 2 puntos, o si todos los pares tienen un valor base 0 (mes sin
        ventas), no hay señal de tendencia -> neutro."""
        if len(serie_cronologica) < 2:
            return 1.0
        razones = [b / a for a, b in zip(serie_cronologica, serie_cronologica[1:]) if a > 0]
        if not razones:
            return 1.0
        return max(factor_min, min(statistics.median(razones), factor_max))

    @staticmethod
    def _peso_estabilidad(valores: list[float], cv_alto: float, peso_min: float) -> float:
        """Cuánto se deja actuar al factor de tendencia según la variabilidad del histórico
        (coeficiente de variación): un vendedor errático (CV alto) no debe recibir el mismo
        empuje de crecimiento que uno estable con la misma tendencia nominal -- se atenúa
        hacia 1.0 (neutro), nunca se anula del todo (piso `peso_min`)."""
        cv = IQRGoalCalculationEngine._coeficiente_variacion(valores)
        if cv <= cv_alto:
            return 1.0
        exceso = min(cv - cv_alto, cv_alto)  # satura en 2x el umbral
        return max(peso_min, 1.0 - exceso / cv_alto * (1.0 - peso_min))

    @staticmethod
    def _aplicar_banda(meta: float, referencia_alcanzable: float, banda_min: float, banda_max: float) -> tuple[float, bool]:
        """Acota `meta` a `[banda_min, banda_max] * referencia_alcanzable` -- el
        guardarraíl final del motor v2 (RN-MT3): sin él, los factores de negocio
        (presión comercial, tipo de vendedor) se multiplican sin ningún techo posterior
        (H-3). Sin una referencia positiva (histórico nulo tras desestacionalizar), no
        hay contra qué acotar -- se deja la meta tal cual."""
        if referencia_alcanzable <= 0:
            return meta, False
        piso = referencia_alcanzable * banda_min
        techo = referencia_alcanzable * banda_max
        acotada = min(max(meta, piso), techo)
        return acotada, acotada != meta

    @staticmethod
    def _coeficiente_variacion(valores: list[float]) -> float:
        if len(valores) < 2:
            return 0.0
        media = statistics.fmean(valores)
        if media <= 0:
            return 0.0
        return statistics.pstdev(valores) / media

    @staticmethod
    def _mediana(valores: list[float]) -> float:
        return statistics.median(valores) if valores else 0.0

    @staticmethod
    def _promedio_ponderado(valores: list[float], pesos: list[float]) -> float:
        suma_pesos = sum(pesos)
        if suma_pesos <= 0:
            return statistics.fmean(valores) if valores else 0.0
        return sum(v * w for v, w in zip(valores, pesos)) / suma_pesos

    @staticmethod
    def _indices_sin_outliers(
        serie: list[float], ventana_referencia: int, multiplicador: float, meses_minimos: int,
    ) -> list[int]:
        """Devuelve los índices de `serie` (orden cronológico ascendente, ya
        desestacionalizada) que caen dentro de las bandas de Tukey. Los cuartiles se
        calculan SOLO sobre los últimos `ventana_referencia` meses. Con menos de
        `meses_minimos` puntos de referencia no hay suficiente resolución estadística
        para cuartiles -- se usan todos los meses sin filtrar."""
        referencia = serie[-ventana_referencia:] if len(serie) > ventana_referencia else serie
        if len(referencia) < meses_minimos:
            return list(range(len(serie)))

        q1, _, q3 = statistics.quantiles(referencia, n=4, method="inclusive")
        iqr = q3 - q1
        limite_inferior = q1 - multiplicador * iqr
        limite_superior = q3 + multiplicador * iqr

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
    def _productos_estrategicos(metas_por_producto: list[DesgloseCalculado], umbral: float) -> list[str]:
        """Regla 80/20: los productos que acumulan hasta el umbral de participación
        histórica (ya vienen ordenados desc.) se consideran estratégicos para la meta."""
        acumulado = 0.0
        estrategicos = []
        for d in metas_por_producto:
            if acumulado >= umbral:
                break
            estrategicos.append(d.clave)
            acumulado += d.participacion_historica_pct
        return estrategicos
