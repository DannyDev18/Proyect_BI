# backend/app/inventory/engine.py
"""Motor puro de Reabastecimiento Inteligente (docs/features/plan_reabastecimiento_
inteligente.md, auditoría docs/auditoria/50_reabastecimiento_inteligente.md).

Mismo patrón que `commission_variable_engine.py`/`goal_pipeline_stages.py`: funciones
puras sin I/O (nunca acceden a la BD ni a `ModelLoader`), 100% testeables, que reciben
sus insumos ya resueltos por el llamador (`WarehouseService`/un servicio nuevo de
Fase 3) y devuelven el número junto con el MÉTODO usado y su procedencia -- nunca un
valor estocástico fingido cuando no hay historia suficiente para sostenerlo (regla
transversal del plan: "ningún campo se rellena con un valor inventado").

Reemplaza/complementa las fórmulas deterministas de `WarehouseService` (H-3/H-4 de la
auditoría 50): el ROP actual (`_punto_reorden_efectivo`) usa un stock de seguridad fijo
de N días sin considerar variabilidad de demanda ni nivel de servicio; este módulo
implementa la fórmula clásica de Supply Chain (Silver/Pyke/Peterson;
Chopra & Meindl, *Supply Chain Management*) `SS = z(nivel_servicio) × σ_demanda × √LT`,
manteniéndose deliberadamente fuera de `WarehouseService` para no arriesgar las fórmulas
ya validadas en producción (RN-B1/B2) -- ambos motores conviven (Fase 3 del plan).

ABC/XYZ con los umbrales REALES de la auditoría 50 (A-0.3/A-0.4), no con
`BODEGA_CV_ALTA`/`BODEGA_CV_MEDIA` (calibrados para transferencias, confirmado que no
discriminan para este propósito: 96.6% del catálogo caía en una sola clase)."""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Literal

# ── Métodos declarados (procedencia del dato, nunca oculta un default) ────────────────
MetodoDemanda = Literal["ml_demand_rf", "estadistico", "sin_historia"]
MetodoStock = Literal["estocastico", "determinista", "sin_historia"]
OrigenLeadTime = Literal["producto", "categoria", "proveedor", "default"]
ClaseABC = Literal["A", "B", "C"]
ClaseXYZ = Literal["X", "Y", "Z"]
Riesgo = Literal["critico", "alto", "medio", "bajo", "sin_demanda"]

# Cortes ABC estándar (Pareto 80/95) -- confirmados razonables sobre datos reales en la
# auditoría 50 (A-0.3: 2.6% / 13.2% / 84.2% de los SKUs, excluyendo el centinela -1 y la
# clase Z-999 de chatarra, mismo criterio que ya excluye el entrenamiento de `demand_rf`).
CORTE_ABC_A = 0.80
CORTE_ABC_B = 0.95

# Cortes XYZ reales (terciles de CV mensual, 12 meses, auditoría 50 A-0.4) -- NO
# reutilizar BODEGA_CV_ALTA/MEDIA, que están calibrados para otro propósito.
CORTE_XYZ_X = 0.39
CORTE_XYZ_Y = 0.61

# Z de la distribución normal por nivel de servicio objetivo (D-2 del plan: por clase
# ABC -- A exige más disponibilidad que C). Tabla estándar, no una aproximación.
Z_POR_NIVEL_SERVICIO: dict[float, float] = {
    0.90: 1.2816,
    0.95: 1.6449,
    0.975: 1.9600,
    0.99: 2.3263,
}

# Nivel de servicio por defecto por clase ABC (D-2, sembrado en `reabastecimiento_
# politica`; el motor lo acepta como parámetro, esto es solo el default de referencia).
NIVEL_SERVICIO_DEFAULT_POR_ABC: dict[ClaseABC, float] = {"A": 0.975, "B": 0.95, "C": 0.90}

# Bajo este umbral de meses con venta, el motor se niega a calcular una desviación
# estándar creíble -- degrada a determinista o sin_historia (auditoría 50 A-0.5: solo el
# 32.1% del catálogo con venta califica para ≥6 meses de historia).
MESES_MINIMOS_ESTOCASTICO = 6
MESES_MINIMOS_CV = 3


def _z_de_nivel_servicio(nivel_servicio: float) -> float:
    """Interpola en la tabla estándar; si no hay coincidencia exacta usa el más cercano
    (no se inventa un cálculo de la inversa de la normal para 4 valores discretos de
    configuración -- estos son los únicos niveles de servicio que la UI ofrece)."""
    if nivel_servicio in Z_POR_NIVEL_SERVICIO:
        return Z_POR_NIVEL_SERVICIO[nivel_servicio]
    mas_cercano = min(Z_POR_NIVEL_SERVICIO, key=lambda ns: abs(ns - nivel_servicio))
    return Z_POR_NIVEL_SERVICIO[mas_cercano]


# ── Clasificación ABC/XYZ ──────────────────────────────────────────────────────────────
def clasificar_abc(
    valor_consumo: float, valor_acumulado: float, valor_total: float,
    corte_a: float = CORTE_ABC_A, corte_b: float = CORTE_ABC_B,
) -> ClaseABC:
    """`valor_acumulado` = suma de valor_consumo de este SKU y todos los de mayor valor
    (curva de Pareto ya ordenada por el llamador). Puro: no ordena ni agrega."""
    if valor_total <= 0:
        return "C"
    proporcion = valor_acumulado / valor_total
    if proporcion <= corte_a:
        return "A"
    if proporcion <= corte_b:
        return "B"
    return "C"


def clasificar_xyz(
    coeficiente_variacion: float | None, corte_x: float = CORTE_XYZ_X, corte_y: float = CORTE_XYZ_Y,
) -> ClaseXYZ:
    """`None` (sin suficiente historia para CV, ver `MESES_MINIMOS_CV`) se trata como la
    variabilidad más alta -- conservador por diseño: sin evidencia de estabilidad, no se
    asume estabilidad."""
    if coeficiente_variacion is None:
        return "Z"
    if coeficiente_variacion <= corte_x:
        return "X"
    if coeficiente_variacion <= corte_y:
        return "Y"
    return "Z"


# ── Demanda y stock de seguridad ───────────────────────────────────────────────────────
@dataclass
class EstadisticaDemanda:
    media_diaria: float
    sigma_diaria: float
    meses_con_venta: int
    metodo: MetodoStock


def estadistica_demanda(
    valores_diarios: list[float], meses_con_venta: int,
) -> EstadisticaDemanda:
    """Media y desviación estándar de una serie ya resuelta por el llamador (nunca
    consulta el EDW). Degrada explícitamente el método según la historia disponible
    (auditoría 50 A-0.5) -- nunca calcula una sigma sobre 1-2 puntos y la presenta como
    si fuera confiable."""
    if not valores_diarios or meses_con_venta == 0:
        return EstadisticaDemanda(0.0, 0.0, 0, "sin_historia")
    n = len(valores_diarios)
    media = sum(valores_diarios) / n
    if n < 2 or meses_con_venta < MESES_MINIMOS_ESTOCASTICO:
        return EstadisticaDemanda(round(media, 4), 0.0, meses_con_venta, "determinista")
    varianza = sum((v - media) ** 2 for v in valores_diarios) / (n - 1)
    sigma = math.sqrt(varianza)
    return EstadisticaDemanda(round(media, 4), round(sigma, 4), meses_con_venta, "estocastico")


def coeficiente_variacion(media: float, sigma: float, meses_con_venta: int) -> float | None:
    if meses_con_venta < MESES_MINIMOS_CV or media <= 0:
        return None
    return round(sigma / media, 4)


@dataclass
class ResultadoStockSeguridad:
    valor: float
    metodo: MetodoStock
    z_usado: float | None


def stock_seguridad(
    stat: EstadisticaDemanda, lead_time_dias: float, nivel_servicio: float,
    dias_seguridad_fallback: float,
) -> ResultadoStockSeguridad:
    """SS = z(nivel_servicio) × σ_demanda × √LT (Silver/Pyke/Peterson; Chopra & Meindl).
    Degrada a `demanda_media × dias_seguridad_fallback` (mismo criterio que el ROP
    determinista actual de `WarehouseService`) cuando no hay sigma confiable -- nunca
    se inventa una sigma de 0 y se presenta como si fuera "sin riesgo"."""
    if stat.metodo == "sin_historia":
        return ResultadoStockSeguridad(0.0, "sin_historia", None)
    if stat.metodo == "determinista" or lead_time_dias <= 0:
        valor = round(stat.media_diaria * dias_seguridad_fallback, 2)
        return ResultadoStockSeguridad(valor, "determinista", None)
    z = _z_de_nivel_servicio(nivel_servicio)
    valor = round(z * stat.sigma_diaria * math.sqrt(lead_time_dias), 2)
    return ResultadoStockSeguridad(valor, "estocastico", z)


@dataclass
class ResultadoPuntoReorden:
    valor: float
    stock_seguridad: float
    metodo: MetodoStock


def punto_reorden(
    stat: EstadisticaDemanda, lead_time_dias: float, ss: ResultadoStockSeguridad,
) -> ResultadoPuntoReorden:
    """ROP = demanda_media × LT + SS. Sin historia, ROP = 0 (no comprar a ciegas)."""
    if stat.metodo == "sin_historia":
        return ResultadoPuntoReorden(0.0, 0.0, "sin_historia")
    demanda_en_lt = stat.media_diaria * lead_time_dias
    return ResultadoPuntoReorden(round(demanda_en_lt + ss.valor, 2), ss.valor, ss.metodo)


def cobertura_dias(stock_actual: float, demanda_diaria_media: float) -> float | None:
    """`None` = sin demanda medible en la ventana -- inventario "infinito", no divisible
    (mismo criterio que `WarehouseService._dias_inventario`)."""
    if demanda_diaria_media <= 0:
        return None
    return round(stock_actual / demanda_diaria_media, 1)


# ── Riesgo y prioridad ─────────────────────────────────────────────────────────────────
def evaluar_riesgo(
    cobertura: float | None, lead_time_dias: float, stock_actual: float, rop: float,
) -> Riesgo:
    """Clasifica el riesgo de quiebre relativo al lead time real (no a un umbral fijo de
    días como `BODEGA_DIAS_DEFICIT`, que no distingue lead times por proveedor)."""
    if cobertura is None:
        return "sin_demanda" if stock_actual > 0 else "critico"
    if stock_actual <= 0 or cobertura < lead_time_dias * 0.5:
        return "critico"
    if cobertura < lead_time_dias:
        return "alto"
    if stock_actual < rop:
        return "medio"
    return "bajo"


_ORDEN_RIESGO: dict[Riesgo, int] = {"critico": 0, "alto": 1, "medio": 2, "sin_demanda": 3, "bajo": 4}
_ORDEN_ABC: dict[ClaseABC, int] = {"A": 0, "B": 1, "C": 2}


def calcular_prioridad(riesgo: Riesgo, clase_abc: ClaseABC, dias_hasta_quiebre: float | None) -> int:
    """Score ordenable ascendente (0 = máxima prioridad). Combina riesgo (peso
    dominante, es la urgencia real) con la clase ABC (desempate: dos artículos igual de
    críticos, se atiende primero el de mayor valor de consumo) y días hasta el quiebre
    (desempate fino dentro del mismo riesgo/clase)."""
    base = _ORDEN_RIESGO[riesgo] * 1000 + _ORDEN_ABC[clase_abc] * 100
    if dias_hasta_quiebre is not None:
        base += min(round(dias_hasta_quiebre), 99)
    return base


# ── Lead time (resolución por especificidad, D-1 opción (a)) ──────────────────────────
@dataclass
class ResultadoLeadTime:
    dias: float
    origen: OrigenLeadTime


def resolver_lead_time(
    lead_time_producto: float | None, lead_time_categoria: float | None,
    lead_time_proveedor: float | None, lead_time_default: float,
) -> ResultadoLeadTime:
    """Especificidad decreciente: producto > categoría > proveedor > default global.
    Nunca oculta que un valor es el default -- el campo `origen` es obligatorio en el
    contrato expuesto al frontend (regla transversal del plan)."""
    if lead_time_producto is not None and lead_time_producto > 0:
        return ResultadoLeadTime(lead_time_producto, "producto")
    if lead_time_categoria is not None and lead_time_categoria > 0:
        return ResultadoLeadTime(lead_time_categoria, "categoria")
    if lead_time_proveedor is not None and lead_time_proveedor > 0:
        return ResultadoLeadTime(lead_time_proveedor, "proveedor")
    return ResultadoLeadTime(lead_time_default, "default")


# ── Cantidad sugerida ──────────────────────────────────────────────────────────────────
def cantidad_sugerida(
    stock_actual: float, demanda_diaria_media: float, rop: ResultadoPuntoReorden,
    horizonte_dias: float, multiplo_compra: float = 1.0,
) -> float:
    """Repone hasta cubrir el horizonte completo por encima del ROP (no solo hasta el
    ROP): evita comprar exactamente lo mínimo y quedar de inmediato bajo el punto de
    reorden de nuevo. Redondea hacia arriba al múltiplo de compra del proveedor
    (`multiplo_compra`, p.ej. caja de 12) cuando se configura uno > 1."""
    objetivo = rop.valor + demanda_diaria_media * horizonte_dias
    cantidad = max(0.0, objetivo - stock_actual)
    if multiplo_compra > 1:
        cantidad = math.ceil(cantidad / multiplo_compra) * multiplo_compra
    return round(cantidad, 2)


# ── Desglose de explicabilidad (bloque 3 del pedido del usuario) ──────────────────────
@dataclass
class DesgloseRecomendacion:
    codart: str
    clase_abc: ClaseABC
    clase_xyz: ClaseXYZ
    demanda_diaria_media: float
    demanda_diaria_sigma: float
    metodo_demanda: MetodoDemanda
    coeficiente_variacion: float | None
    lead_time_dias: float
    lead_time_origen: OrigenLeadTime
    nivel_servicio: float
    z_usado: float | None
    stock_seguridad: float
    metodo_stock_seguridad: MetodoStock
    punto_reorden: float
    stock_actual: float
    cobertura_dias: float | None
    riesgo: Riesgo
    cantidad_sugerida: float
    razones: list[str] = field(default_factory=list)


def construir_desglose(
    codart: str, clase_abc: ClaseABC, clase_xyz: ClaseXYZ,
    stat: EstadisticaDemanda, cv: float | None, metodo_demanda: MetodoDemanda,
    lt: ResultadoLeadTime, nivel_servicio: float, ss: ResultadoStockSeguridad,
    rop: ResultadoPuntoReorden, stock_actual: float, cantidad: float,
) -> DesgloseRecomendacion:
    """Ensambla el desglose completo y genera las razones en lenguaje de negocio (no
    nombres de variable) -- lo que consume el panel de explicabilidad (bloque 3)."""
    cobertura = cobertura_dias(stock_actual, stat.media_diaria)
    riesgo = evaluar_riesgo(cobertura, lt.dias, stock_actual, rop.valor)
    razones: list[str] = []
    if riesgo == "critico":
        razones.append(f"Cobertura de {cobertura if cobertura is not None else 0} días, por debajo de la mitad del lead time ({lt.dias} días).")
    elif riesgo == "alto":
        razones.append(f"Cobertura de {cobertura} días, menor al lead time del proveedor ({lt.dias} días).")
    if lt.origen == "default":
        razones.append("Lead time usando el valor por defecto de la política -- no configurado para este producto/categoría/proveedor.")
    if stat.metodo == "sin_historia":
        razones.append("Sin historia de ventas suficiente: no se calcula stock de seguridad ni cantidad sugerida.")
    elif stat.metodo == "determinista":
        razones.append(f"Menos de {MESES_MINIMOS_ESTOCASTICO} meses de historia: stock de seguridad estimado como demanda media, sin ajuste por variabilidad.")
    else:
        razones.append(f"Nivel de servicio {nivel_servicio:.1%} (clase {clase_abc}), stock de seguridad calculado con la variabilidad real de la demanda.")
    return DesgloseRecomendacion(
        codart=codart, clase_abc=clase_abc, clase_xyz=clase_xyz,
        demanda_diaria_media=stat.media_diaria, demanda_diaria_sigma=stat.sigma_diaria,
        metodo_demanda=metodo_demanda, coeficiente_variacion=cv,
        lead_time_dias=lt.dias, lead_time_origen=lt.origen,
        nivel_servicio=nivel_servicio, z_usado=ss.z_usado,
        stock_seguridad=ss.valor, metodo_stock_seguridad=ss.metodo,
        punto_reorden=rop.valor, stock_actual=stock_actual, cobertura_dias=cobertura,
        riesgo=riesgo, cantidad_sugerida=cantidad, razones=razones,
    )


# ── Alertas inteligentes (F7, §7.4 del plan) ───────────────────────────────────────
# Umbral mínimo de meses para que un "cambio brusco" o una "tendencia" tengan
# suficiente base estadística -- por debajo, cualquier variación mes a mes es ruido,
# no señal (mismo criterio conservador que MESES_MINIMOS_CV).
MESES_MINIMOS_ALERTA = 3


def detectar_cambio_brusco(
    valor_reciente: float, media_historica: float, sigma_historica: float, meses_con_venta: int,
) -> bool:
    """§7.4 alerta 🔵: demanda del período más reciente fuera de `media ± 2σ` del
    histórico -- regla de control estadístico de proceso clásica (2 desviaciones
    estándar), no un umbral arbitrario. Con `sigma_historica <= 0` (demanda perfectamente
    constante o sin variabilidad medible) o menos de `MESES_MINIMOS_ALERTA` meses de
    historia, no se declara ninguna señal -- 2σ de una muestra casi vacía es ruido, no
    una alerta creíble."""
    if meses_con_venta < MESES_MINIMOS_ALERTA or sigma_historica <= 0:
        return False
    return abs(valor_reciente - media_historica) > 2 * sigma_historica


def detectar_tendencia_decreciente(unidades_mensuales: list[float], periodos: int = 3) -> bool:
    """§7.4 alerta 🟢: demanda decreciente en los últimos `periodos` meses consecutivos
    (estrictamente, sin empates) -- señal de "revisar política / no comprar", no de
    quiebre. Con menos de `periodos` meses de historia no hay suficiente serie para
    declarar una tendencia sostenida (podría ser una sola caída puntual, no sostenida)."""
    if len(unidades_mensuales) < periodos:
        return False
    cola = unidades_mensuales[-periodos:]
    return all(cola[i] > cola[i + 1] for i in range(len(cola) - 1))


# ── Fórmulas deterministas legacy (D-1/D-2 de la auditoría 52) ────────────────────────
# Motor histórico de `WarehouseService` (RN-B1/B2), absorbido aquí en la Fase 2 del
# refactor de módulo (docs/features/plan_modulo_inventario_reabastecimiento.md) SIN
# cambiar su comportamiento -- byte a byte el mismo resultado que antes. Convive a
# propósito con el motor estocástico de arriba: la auditoría 52 (A-0.2) midió que 49.7%
# del catálogo cambia de "Seguro" a riesgo "crítico" al pasar de un motor al otro --
# decisión de negocio pendiente (Fase 5 del plan), no algo que este refactor resuelve.
# Los umbrales (`dias_exceso`/`factor_cerca_reorden`/etc.) siguen viviendo en
# `settings.BODEGA_*`; el motor los recibe por parámetro, nunca los lee directamente
# (regla de frontera: `engine.py` no importa `app.core.config`).
def demanda_diaria_simple(salidas_periodo: float, dias: int = 30) -> float:
    """Ventana fija de `dias` (default 30) sobre salidas ya agregadas por el llamador --
    la fórmula de demanda diaria del motor determinista original."""
    return (salidas_periodo / dias) if dias > 0 else 0.0


def punto_reorden_determinista(
    configurado: float, salida_diaria: float, lead_time_dias: float, dias_seguridad: float,
) -> float:
    """ROP determinista: usa el valor configurado en el ERP si existe (`configurado > 0`),
    si no `salida_diaria × (lead_time + días de seguridad fijos)` -- sin variabilidad de
    demanda ni nivel de servicio (esa es la diferencia con `punto_reorden`, el motor
    estocástico de arriba)."""
    if configurado and configurado > 0:
        return round(float(configurado), 2)
    return round(salida_diaria * (lead_time_dias + dias_seguridad), 2)


def dias_inventario(stock: float, salida_diaria: float) -> float | None:
    """`None` = sin salidas en el período (inventario "infinito", no divisible)."""
    if salida_diaria <= 0:
        return None
    return round(stock / salida_diaria, 1)


def estado_stock(
    stock: float, reorden: float, dias_inv: float | None,
    dias_exceso: float, factor_cerca_reorden: float,
) -> str:
    """Vocabulario del motor determinista (`Crítico`/`Cerca`/`Seguro`/`Exceso`) --
    distinto a propósito del vocabulario de riesgo del motor estocástico
    (`evaluar_riesgo`, arriba): miden cosas diferentes (stock vs. ROP fijo, vs. cobertura
    vs. lead time real), ver auditoría 52 A-0.2. Los literales exactos (`ESTADO_*`) viven
    en `WarehouseService` -- son vocabulario ya expuesto al frontend, no una decisión de
    este motor; `Inmovilizado` (H-2, auditoría 42) no se decide aquí porque depende de
    una ventana de meses distinta a `dias`, resuelta antes de llamar a esta función."""
    if dias_inv is not None and dias_inv > dias_exceso:
        return "Exceso"
    if reorden <= 0:
        return "Seguro"
    if stock < reorden:
        return "Crítico"
    if stock <= reorden * factor_cerca_reorden:
        return "Cerca"
    return "Seguro"
