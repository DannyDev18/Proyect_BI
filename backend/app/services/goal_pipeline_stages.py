# backend/app/services/goal_pipeline_stages.py
"""Etapas del motor de metas v3 (docs/features/plan_motor_metas_v3_y_comisiones_
unificadas.md §18, Fase 5/6) que NO están ya cubiertas por `IQRGoalCalculationEngine`
(E1/E2/E3/E4/E5/E10-banda/E11 siguen resolviéndose ahí -- son la matemática del motor v2,
ya probada y validada en producción; esta fase la hace CONFIGURABLE, no la reescribe).

Este módulo aporta:
- El **catálogo cerrado** de las 14 etapas (`ETAPAS_CATALOGO`): qué métodos existen por
  etapa y cuáles están realmente **implementados** (producen un número) frente a los que
  solo están **declarados** (documentan la arquitectura completa tipo SPM -- SAP/Oracle/
  Anaplan/Xactly -- pero no tienen código de ejecución en esta versión, casi siempre por
  falta de una fuente de datos real en el EDW, nunca por pereza -- ver `implementado` y
  `motivo_no_implementado` de cada método). `MetaConfigModuloService` rechaza guardar un
  método no implementado: nunca se activa en la UI algo que no calcula nada real.
- Las etapas nuevas de esta fase que SÍ están implementadas como función pura,
  independientes del motor v2 (E7 estrategia, E8 tipo de vendedor -- absorbe la lógica que
  antes vivía duplicada en `GoalMLService._ajustar_meta_por_tipo`, E9 capacidad instalada,
  E13 factor cartera, E15 cumplimiento histórico, E16 penalización por volatilidad,
  E11 redondeo). Todas reciben sus parámetros ya resueltos (nunca acceden a la BD) y
  devuelven el valor ajustado + una nota de trazabilidad, siguiendo el mismo patrón de
  función pura que ya usa `ajustar_meta_por_madurez` (E6, `goal_calculation_engine.py`).

Todas las etapas opcionales (E7/E9/E13/E15/E16) están **desactivadas en la
semilla** (migración `0014_metas_config_modular`): con la configuración semilla, el
pipeline v3 reproduce el motor v2 dentro de tolerancia numérica (§19 del plan) -- activar
cualquiera de ellas es una decisión explícita de gerencia, nunca un cambio de
comportamiento por defecto de esta migración.

**E12 (distribución corporativa) y E14 (potencial de mercado) se retiraron del catálogo
por completo** (migración `0015_metas_pipeline_ajustes.py`, petición explícita del
usuario: "quitar todo lo que no tiene un efecto en la regla de las metas"). Ninguna de
las dos tenía nunca un método `implementado=True` -- E12 requiere `public.
metas_corporativas` (inexistente) y E14 requiere una fuente de mercado total que ningún
ERP transaccional propio puede proveer -- así que dejarlas en el catálogo/UI era mostrar
una tarjeta que NUNCA podía activarse, un mockup sin efecto real. Si en el futuro
gerencia define un objetivo corporativo real (E12), se reintroduce con su propia
migración cuando la tabla exista.

`parametros` (por etapa, no por método): la lista cerrada de parámetros numéricos que
esa etapa acepta -- fuente única para que el frontend genere un formulario dinámico
(campo por campo, con su rango) en vez de un editor de JSON crudo. Mismo rango que
`MetaConfigModuloService.RANGOS_PARAMETROS` (duplicado deliberado: ese diccionario es la
autoridad de VALIDACIÓN del backend; esta lista es la autoridad de PRESENTACIÓN del
formulario -- ambas deben coincidir, verificado por `test_goal_pipeline_stages.py`)."""
from __future__ import annotations

import statistics
from dataclasses import dataclass, field

# ── Catálogo cerrado de etapas y métodos (fuente de verdad de validación + UI) ─────────
# `implementado=False` documenta la arquitectura completa (requisito de tesis: motor
# modular tipo SPM) sin fingir que un método sin código real puede activarse.
ETAPAS_CATALOGO: dict[str, dict] = {
    "E1_limpieza": {
        "orden": 1, "nombre": "Limpieza de datos (outliers)",
        "metodos": {
            "ninguna": {"implementado": True, "descripcion": "Paso a través, sin excluir ningún mes."},
            "tukey": {"implementado": True, "descripcion": "Bandas de Tukey sobre la ventana de referencia (semilla, motor v2)."},
            "zscore": {"implementado": False, "descripcion": "Excluye |z| > z_max.", "motivo": "Declarado en la arquitectura, sin implementación de ejecución en esta versión."},
            "isolation_forest": {"implementado": False, "descripcion": "IsolationForest sobre la serie, ≥24 meses.", "motivo": "Declarado en la arquitectura, sin implementación de ejecución en esta versión."},
            "umbral_absoluto": {"implementado": False, "descripcion": "Excluye meses no representativos (Fase 10, R-14).", "motivo": "Factor opcional de la Fase 10, pendiente de auditoría de calibración."},
        },
        "parametros": [
            {"clave": "k", "label": "Sensibilidad IQR (multiplicador)", "tipo": "float", "min": 0.5, "max": 3.0, "paso": 0.1, "default": 1.5},
            {"clave": "ventana_referencia", "label": "Meses de la ventana de referencia", "tipo": "int", "min": 4, "max": 36, "paso": 1, "default": 12},
            {"clave": "meses_minimos_para_iqr", "label": "Mínimo de meses para aplicar IQR", "tipo": "int", "min": 2, "max": 12, "paso": 1, "default": 4},
        ],
    },
    "E2_nivel_base": {
        "orden": 2, "nombre": "Nivel base",
        "metodos": {
            "mixto": {"implementado": True, "descripcion": "Promedio ponderado con atenuación de meses atípicos ML (semilla, motor v2)."},
            "mediana": {"implementado": False, "descripcion": "Mediana pura de la serie.", "motivo": "Declarado en la arquitectura, sin implementación de ejecución en esta versión."},
            "promedio": {"implementado": False, "descripcion": "Media aritmética pura.", "motivo": "Declarado en la arquitectura, sin implementación de ejecución en esta versión."},
            "ponderado": {"implementado": False, "descripcion": "Media ponderada por recencia.", "motivo": "Declarado en la arquitectura, sin implementación de ejecución en esta versión."},
            "forecast_ml": {"implementado": False, "descripcion": "Modelo ML de nivel base.", "motivo": "`goals_rf` fue decomisionado (auditoría 20); no se reintroduce sin una competencia formal documentada."},
        },
        "parametros": [],
    },
    "E3_estacionalidad": {
        "orden": 3, "nombre": "Estacionalidad",
        "metodos": {
            "cascada": {"implementado": True, "descripcion": "Índice propio del vendedor, con respaldo del índice de empresa mes a mes (semilla, motor v2)."},
            "sucursal": {"implementado": False, "descripcion": "Índice por sucursal.", "motivo": "`sucursal` no es un agrupador válido para vendedores (auditoría 42)."},
            "region": {"implementado": False, "descripcion": "Índice por región.", "motivo": "`edw.dim_geografia` está vacía (auditoría 05)."},
        },
        "parametros": [
            {"clave": "min_anios_estacional", "label": "Años mínimos de histórico para índice propio", "tipo": "int", "min": 1, "max": 5, "paso": 1, "default": 2},
        ],
    },
    "E4_tendencia": {
        "orden": 4, "nombre": "Tendencia",
        "metodos": {
            "ninguna": {"implementado": True, "descripcion": "Factor de tendencia neutro (1.0)."},
            "promedio_movil": {"implementado": True, "descripcion": "Mediana de variaciones intermensuales relativas (semilla, motor v2)."},
            "regresion_lineal": {"implementado": False, "descripcion": "Pendiente OLS proyectada.", "motivo": "Declarado en la arquitectura, sin implementación de ejecución en esta versión."},
            "suavizado_exponencial": {"implementado": False, "descripcion": "Holt simple.", "motivo": "Declarado en la arquitectura, sin implementación de ejecución en esta versión."},
            "holt_winters": {"implementado": False, "descripcion": "Holt-Winters completo, ≥24 meses.", "motivo": "Declarado en la arquitectura, sin implementación de ejecución en esta versión."},
        },
        "parametros": [
            {"clave": "ventana", "label": "Meses recientes para calcular la tendencia", "tipo": "int", "min": 2, "max": 12, "paso": 1, "default": 4},
            {"clave": "factor_tendencia_min", "label": "Tope inferior del factor de tendencia", "tipo": "float", "min": 0.5, "max": 1.0, "paso": 0.05, "default": 0.85},
            {"clave": "factor_tendencia_max", "label": "Tope superior del factor de tendencia", "tipo": "float", "min": 1.0, "max": 2.0, "paso": 0.05, "default": 1.20},
        ],
    },
    "E5_estabilidad": {
        "orden": 5, "nombre": "Peso de estabilidad",
        "metodos": {"estandar": {"implementado": True, "descripcion": "Atenúa la tendencia según el coeficiente de variación (semilla, motor v2)."}},
        "parametros": [
            {"clave": "cv_alto", "label": "Coeficiente de variación considerado alto", "tipo": "float", "min": 0.1, "max": 2.0, "paso": 0.05, "default": 0.5},
            {"clave": "peso_estabilidad_min", "label": "Peso mínimo de la tendencia (serie muy errática)", "tipo": "float", "min": 0.0, "max": 1.0, "paso": 0.05, "default": 0.3},
        ],
    },
    "E6_madurez": {
        "orden": 6, "nombre": "Madurez del vendedor",
        "metodos": {
            "mezcla_gradual": {"implementado": True, "descripcion": "Transición gradual 0/1-5/6-23/≥24 meses (auditoría 47, Fase 7)."},
        },
        "parametros": [
            {"clave": "umbral_nuevo_meses", "label": "Meses de historia bajo los cuales se considera 'nuevo'", "tipo": "int", "min": 1, "max": 12, "paso": 1, "default": 6},
            {"clave": "umbral_maduro_meses", "label": "Meses de historia desde los cuales se considera 'maduro'", "tipo": "int", "min": 12, "max": 60, "paso": 1, "default": 24},
            {"clave": "peso_benchmark_intermedio", "label": "Peso del benchmark del equipo en la etapa intermedia", "tipo": "float", "min": 0.0, "max": 1.0, "paso": 0.05, "default": 0.20},
        ],
    },
    "E7_estrategia": {
        "orden": 7, "nombre": "Objetivo estratégico de la empresa",
        "metodos": {"crecimiento_pct": {"implementado": True, "descripcion": "meta × (1 + crecimiento_pct/100)."}},
        "parametros": [
            {"clave": "crecimiento_pct", "label": "% de crecimiento objetivo (puede ser negativo)", "tipo": "float", "min": -50.0, "max": 100.0, "paso": 1.0, "default": 0.0},
        ],
    },
    "E8_tipo_vendedor": {
        "orden": 8, "nombre": "Factor por tipo de vendedor",
        "metodos": {"tabla": {"implementado": True, "descripcion": "Factor externo/interno (absorbe COMISION_META_FACTOR_*, auditoría 46 H-10)."}},
        "parametros": [
            {"clave": "externo", "label": "Factor para vendedor externo", "tipo": "float", "min": 0.5, "max": 2.0, "paso": 0.05, "default": 1.10},
            {"clave": "interno", "label": "Factor para vendedor interno", "tipo": "float", "min": 0.5, "max": 2.0, "paso": 0.05, "default": 0.95},
        ],
    },
    "E9_capacidad": {
        "orden": 9, "nombre": "Capacidad instalada",
        "metodos": {"clientes_ticket_frecuencia": {"implementado": True, "descripcion": "Tope duro = clientes_activos × ticket_promedio × frecuencia_mensual × holgura, usando la cartera real del vendedor (últimos 6 meses de fact_ventas_detalle)."}},
        "parametros": [
            {"clave": "holgura", "label": "Holgura sobre la capacidad calculada", "tipo": "float", "min": 1.0, "max": 2.0, "paso": 0.05, "default": 1.10},
        ],
    },
    "E10_restricciones": {
        "orden": 10, "nombre": "Restricciones finales (banda de alcanzabilidad)",
        "metodos": {"banda": {"implementado": True, "descripcion": "clamp(meta, banda_min·ref, banda_max·ref) (semilla, motor v2)."}},
        "parametros": [
            {"clave": "banda_alcanzabilidad_min", "label": "Piso de la banda (× referencia reciente)", "tipo": "float", "min": 0.5, "max": 1.0, "paso": 0.05, "default": 0.85},
            {"clave": "banda_alcanzabilidad_max", "label": "Techo de la banda (× referencia reciente)", "tipo": "float", "min": 1.0, "max": 2.0, "paso": 0.05, "default": 1.20},
            {"clave": "meses_referencia_alcanzable", "label": "Meses recientes para calcular la referencia", "tipo": "int", "min": 2, "max": 24, "paso": 1, "default": 6},
        ],
    },
    "E11_redondeo": {
        "orden": 11, "nombre": "Redondeo",
        "metodos": {
            "cercano": {"implementado": True, "descripcion": "Redondeo al múltiplo más cercano."},
            "arriba": {"implementado": True, "descripcion": "Redondeo al múltiplo superior."},
            "abajo": {"implementado": True, "descripcion": "Redondeo al múltiplo inferior."},
        },
        "parametros": [
            {"clave": "multiplo", "label": "Redondear al múltiplo de", "tipo": "int", "min": 1, "max": 10000, "paso": 10, "default": 100},
        ],
    },
    "E13_cartera": {
        "orden": 13, "nombre": "Factor cartera activa",
        "metodos": {"clientes_activos_vs_ventana": {"implementado": True, "descripcion": "clientes_activos_mes / promedio_clientes_activos_ventana, acotado (cartera real del vendedor, últimos 6 meses)."}},
        "parametros": [
            {"clave": "min", "label": "Factor mínimo (cartera reducida)", "tipo": "float", "min": 0.5, "max": 1.0, "paso": 0.05, "default": 0.85},
            {"clave": "max", "label": "Factor máximo (cartera ampliada)", "tipo": "float", "min": 1.0, "max": 2.0, "paso": 0.05, "default": 1.15},
        ],
    },
    "E15_cumplimiento": {
        "orden": 15, "nombre": "Factor de cumplimiento histórico",
        "metodos": {"promedio_ponderado": {"implementado": True, "descripcion": "1 + (cumplimiento_promedio − 1) × peso, acotado (cumplimiento real de los últimos 6 meses del vendedor)."}},
        "parametros": [
            {"clave": "peso", "label": "Peso del cumplimiento histórico sobre la meta", "tipo": "float", "min": 0.0, "max": 1.0, "paso": 0.05, "default": 0.2},
        ],
    },
    "E16_volatilidad": {
        "orden": 16, "nombre": "Penalización por volatilidad",
        "metodos": {"umbral_cv": {"implementado": True, "descripcion": "Reduce el componente de crecimiento si el coeficiente de variación del vendedor supera un umbral."}},
        "parametros": [
            {"clave": "umbral_cv", "label": "Coeficiente de variación a partir del cual penaliza", "tipo": "float", "min": 0.1, "max": 2.0, "paso": 0.05, "default": 0.40},
            {"clave": "factor_reduccion", "label": "Fracción del crecimiento que se recorta", "tipo": "float", "min": 0.0, "max": 1.0, "paso": 0.05, "default": 0.5},
        ],
    },
}

ETAPAS_VALIDAS = frozenset(ETAPAS_CATALOGO)


def metodo_implementado(etapa: str, metodo: str | None) -> tuple[bool, str | None]:
    """`(True, None)` si el método existe y está implementado; si no, `(False, motivo)`
    con el texto explicativo del catálogo (nunca un `KeyError` silencioso -- el llamador
    decide si eso es un error de validación o solo informativo)."""
    info = ETAPAS_CATALOGO.get(etapa)
    if info is None:
        return False, f"Etapa desconocida: {etapa}."
    metodos = info["metodos"]
    if metodo is None:
        return (True, None) if len(metodos) == 1 else (False, "Esta etapa requiere un método explícito.")
    m = metodos.get(metodo)
    if m is None:
        return False, f"Método '{metodo}' no existe para la etapa {etapa}."
    if not m["implementado"]:
        return False, m.get("motivo", "Método declarado en la arquitectura, sin implementación de ejecución en esta versión.")
    return True, None


# ── E7 -- objetivo estratégico de la empresa ────────────────────────────────────────────
def aplicar_estrategia(meta: float, crecimiento_pct: float) -> float:
    """`crecimiento_pct` puede ser negativo (contracción deliberada de la meta). No
    incluye guardarraíl propio -- lo acota E10 (banda), que ya actúa sobre la meta FINAL."""
    return meta * (1.0 + crecimiento_pct / 100.0)


# ── E8 -- factor por tipo de vendedor (absorbe COMISION_META_FACTOR_EXTERNO/_INTERNO) ──
def aplicar_factor_tipo(meta: float, tipo: str, factores: dict[str, float]) -> float:
    """`factores` es la tabla configurable de la etapa (ej. `{"externo": 1.10, "interno":
    0.95}`); un tipo sin entrada en la tabla no se penaliza (factor 1.0, nunca un
    `KeyError` sobre un catálogo que puede crecer con nuevos tipos de vendedor)."""
    return meta * factores.get(tipo, 1.0)


# ── E9 -- capacidad instalada (tope duro) ───────────────────────────────────────────────
@dataclass(frozen=True)
class ResultadoCapacidad:
    meta_ajustada: float
    aplico: bool
    capacidad: float | None


def aplicar_capacidad_instalada(
    meta: float, clientes_activos: float | None, ticket_promedio: float | None,
    frecuencia_compra_mensual: float | None, holgura: float = 1.10,
) -> ResultadoCapacidad:
    """Tope duro `meta = min(meta, capacidad × holgura)`. Sin cartera medible (vendedor
    nuevo, mostrador sin clientes identificados) la etapa se OMITE -- nunca se aplica una
    capacidad de 0, que anularía la meta por falta de dato, no por diseño."""
    if not clientes_activos or not ticket_promedio or not frecuencia_compra_mensual:
        return ResultadoCapacidad(meta, False, None)
    capacidad = clientes_activos * ticket_promedio * frecuencia_compra_mensual
    if capacidad <= 0:
        return ResultadoCapacidad(meta, False, None)
    techo = capacidad * holgura
    return ResultadoCapacidad(min(meta, techo), meta > techo, capacidad)


# ── E11 -- redondeo (siempre el último paso) ────────────────────────────────────────────
def redondear_meta(meta: float, multiplo: int = 100, modo: str = "cercano") -> float:
    if multiplo <= 0:
        return meta
    cociente = meta / multiplo
    if modo == "arriba":
        import math
        return math.ceil(cociente) * multiplo
    if modo == "abajo":
        import math
        return math.floor(cociente) * multiplo
    return round(cociente) * multiplo


# ── E13 -- factor cartera activa (Fase 10, R-14) ────────────────────────────────────────
def aplicar_factor_cartera(
    meta: float, clientes_activos_mes: float | None, promedio_clientes_activos_ventana: float | None,
    factor_min: float = 0.85, factor_max: float = 1.15,
) -> float:
    """Un cambio de cartera puede ser una reasignación administrativa, no desempeño --
    por eso se acota a un rango estrecho (`[factor_min, factor_max]`, semilla 0.85-1.15),
    nunca deja que la cartera por sí sola duplique o anule la meta."""
    if not clientes_activos_mes or not promedio_clientes_activos_ventana or promedio_clientes_activos_ventana <= 0:
        return meta
    factor = max(factor_min, min(clientes_activos_mes / promedio_clientes_activos_ventana, factor_max))
    return meta * factor


# ── E15 -- factor de cumplimiento histórico (Fase 9.B) ──────────────────────────────────
def aplicar_factor_cumplimiento_historico(meta: float, cumplimiento_promedio: float | None, peso: float = 0.2) -> float:
    """Premia al vendedor que sistemáticamente supera su cuota con una cuota mayor --
    `cumplimiento_promedio` es un ratio (1.0 = 100%). Sin histórico de cumplimiento
    medible (`None`), la etapa es neutra."""
    if cumplimiento_promedio is None:
        return meta
    return meta * (1.0 + (cumplimiento_promedio - 1.0) * peso)


# ── E16 -- penalización por volatilidad ─────────────────────────────────────────────────
def aplicar_penalizacion_volatilidad(
    factor_crecimiento: float, coeficiente_variacion: float, umbral_cv: float = 0.40, factor_reduccion: float = 0.5,
) -> float:
    """Reduce el componente de CRECIMIENTO (la parte de `factor_crecimiento` por encima
    de 1.0) cuando la serie es muy errática -- nunca penaliza un factor ya `<= 1.0`
    (una tendencia a la baja no se "penaliza" hacia abajo dos veces)."""
    if coeficiente_variacion <= umbral_cv or factor_crecimiento <= 1.0:
        return factor_crecimiento
    exceso = factor_crecimiento - 1.0
    return 1.0 + exceso * factor_reduccion


@dataclass(frozen=True)
class PipelineConfigV3:
    """Configuración modular ya resuelta (`MetaConfigModuloService.get_pipeline_config`),
    lista para que `GoalMLService` la aplique sin volver a tocar la BD por vendedor."""
    aplicar_limpieza: bool = True
    aplicar_estacionalidad: bool = True
    aplicar_tendencia: bool = True
    aplicar_estabilidad: bool = True
    aplicar_banda: bool = True
    # E6 -- madurez
    umbral_nuevo_meses: int = 6
    umbral_maduro_meses: int = 24
    peso_propio_intermedio: float = 0.80
    # E7 -- estrategia
    estrategia_activa: bool = False
    crecimiento_pct: float = 0.0
    # E8 -- tipo de vendedor
    factores_tipo_vendedor: dict[str, float] = field(default_factory=lambda: {"externo": 1.10, "interno": 0.95})
    # E9 -- capacidad instalada
    capacidad_activa: bool = False
    capacidad_holgura: float = 1.10
    # E11 -- redondeo
    redondeo_multiplo: int = 100
    redondeo_modo: str = "cercano"
    # E13 -- cartera
    cartera_activa: bool = False
    cartera_factor_min: float = 0.85
    cartera_factor_max: float = 1.15
    # E15 -- cumplimiento histórico
    cumplimiento_activo: bool = False
    cumplimiento_peso: float = 0.2
    # E16 -- volatilidad
    volatilidad_activa: bool = False
    volatilidad_umbral_cv: float = 0.40
    volatilidad_factor_reduccion: float = 0.5
    # Trazabilidad: snapshot de la configuración TAL COMO ESTABA al generar (§20 del plan)
    config_snapshot: dict = field(default_factory=dict)
