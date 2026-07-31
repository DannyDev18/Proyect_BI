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

import datetime
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


def ultimo_dia_mes(anio: int, mes: int) -> datetime.date:
    siguiente = datetime.date(anio + (mes == 12), (mes % 12) + 1, 1)
    return siguiente - datetime.timedelta(days=1)


def fecha_referencia_periodo(anio: int, mes: int) -> datetime.date:
    """Fecha a la que debe resolverse la configuración VIGENTE (matriz de categorías,
    factores de crédito) al calcular la comisión de un período dado -- docs/auditoria/
    35_actualizacion_modulo_metas.md, H1: el cierre de un mes usa la configuración
    vigente hasta el último día de ESE mes, no la vigente "hoy"; de lo contrario un
    cambio de configuración posterior reescribiría retroactivamente lo que un período
    ya cerrado habría pagado. Para el mes en curso (`ultimo_dia_mes` en el futuro), se
    usa "hoy" -- el período abierto sí debe reflejar la configuración vigente ahora
    mismo. Antes esta lógica solo existía en `CommissionSimulationService` (auditoría
    34, H-8) y no en el cálculo real de `CommissionService`, que siempre usaba "hoy"
    sin importar el período consultado."""
    return min(ultimo_dia_mes(anio, mes), datetime.date.today())


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
    # Poblados solo cuando la fórmula VIGENTE (auditoría 44) incluye 'base_cobranza' /
    # cualquier componente -- None para la fórmula 'actual' (comportamiento legacy
    # intacto). `desglose_cobranza` es el detalle por tramo (mismo formato que el reporte
    # del ERP); `traza_formula` es el paso a paso de `evaluar_formula` (transparencia
    # total, salvaguarda 6, ahora también sobre la ESTRUCTURA de la fórmula, no solo los
    # valores).
    desglose_cobranza: tuple[dict, ...] | None = None
    traza_formula: tuple[dict, ...] | None = None


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


# ══════════════════════════════════════════════════════════════════════════════════
# Comisión sobre COBROS (docs/auditoria/44_comisiones_sobre_cobros.md,
# docs/features/plan_comisiones_sobre_cobros.md). La regla realmente vigente en la
# empresa: tasa por tramo de DÍAS DE COBRO (banfec - fecemi, RN-CM8/RN-CM9), no sobre
# venta facturada. Convive con el motor por margen/categoría de arriba -- cuál de los dos
# es la base de la comisión lo decide la FÓRMULA configurada (ver `evaluar_formula`), no
# esta función.
# ══════════════════════════════════════════════════════════════════════════════════
PERFIL_EXTERNO = "externo"
PERFIL_INTERNO = "interno"
PERFIL_JEFE_AGENCIA = "jefe_agencia"


@dataclass(frozen=True)
class TramoCobranza:
    """Una fila resuelta de `comision_tramos_cobranza` (ya filtrada por vigencia)."""
    dias_hasta: int | None  # None = sin tope superior (equivalente al remanente > 365)
    tasa_pct: float


@dataclass(frozen=True)
class CobroComisionable:
    """Un cobro ya resuelto por el repositorio (grano `fact_cobros_cuotas`)."""
    valor_cobrado: float
    dias_cobro: int  # ya con piso en 0 (auditoría 44, H-9) -- materializado en el ETL


@dataclass(frozen=True)
class DesgloseTramoCobranza:
    dias_hasta: int | None
    tasa_pct: float
    base_cobrada: float
    comision_tramo: float


@dataclass(frozen=True)
class ComisionCobranzaCalculada:
    comision_total: float
    total_cobrado: float
    desglose_tramos: tuple[DesgloseTramoCobranza, ...]


def resolver_tramo_cobranza(dias_cobro: int, tramos: list[TramoCobranza]) -> float:
    """Tasa del primer tramo (ordenado por `dias_hasta` ascendente, `None` al final) cuyo
    techo cubre `dias_cobro`. Sin tramo que lo cubra (p.ej. > 365 sin fila `dias_hasta=None`
    configurada) -> 0.0, igual que el cuadro de negocio original ("365 días: 0.00%")."""
    dias_cobro = max(0, dias_cobro)  # defensivo: el ETL ya aplica el piso (H-9)
    ordenados = sorted(tramos, key=lambda t: (t.dias_hasta is None, t.dias_hasta or 0))
    for t in ordenados:
        if t.dias_hasta is None or dias_cobro <= t.dias_hasta:
            return t.tasa_pct
    return 0.0


def calcular_comision_cobranza(
    cobros: list[CobroComisionable], tramos: list[TramoCobranza],
) -> ComisionCobranzaCalculada:
    """Σ cobros × tasa del tramo de sus días de cobro, con desglose POR TRAMO -- el mismo
    formato que el reporte "Comisión sobre cobros" del ERP (auditoría 44 §3), para que el
    vendedor pueda auditar su comisión tramo a tramo."""
    ordenados = sorted(tramos, key=lambda t: (t.dias_hasta is None, t.dias_hasta or 0))
    acumulado: dict[int, list[float]] = {i: [0.0, 0.0] for i in range(len(ordenados))}  # [base, comision]

    for c in cobros:
        dias = max(0, c.dias_cobro)
        for i, t in enumerate(ordenados):
            if t.dias_hasta is None or dias <= t.dias_hasta:
                acumulado[i][0] += c.valor_cobrado
                acumulado[i][1] += c.valor_cobrado * (t.tasa_pct / 100.0)
                break

    desglose = tuple(
        DesgloseTramoCobranza(
            dias_hasta=t.dias_hasta, tasa_pct=t.tasa_pct,
            base_cobrada=round(acumulado[i][0], 4), comision_tramo=round(acumulado[i][1], 4),
        )
        for i, t in enumerate(ordenados)
    )
    return ComisionCobranzaCalculada(
        comision_total=round(sum(d.comision_tramo for d in desglose), 4),
        total_cobrado=round(sum(c.valor_cobrado for c in cobros), 4),
        desglose_tramos=desglose,
    )


def calcular_contado_agencia(ventas_contado_agencia: float, pct: float) -> float:
    """Componente "1% de ventas de contado de la agencia" de los jefes de agencia
    (auditoría 44 §1). `ventas_contado_agencia` ya viene filtrada por el repositorio a
    las ventas con `conpag='E'` (contado -- verificado contra Producción, RN-CM11:
    contraintuitivo, 'E' es contado y 'C' es crédito) del vendedor en SU agencia."""
    return round(max(0.0, ventas_contado_agencia) * (pct / 100.0), 4)


# ══════════════════════════════════════════════════════════════════════════════════
# Fórmula como configuración persistida (auditoría 44, pedido explícito del usuario: la
# fórmula debe ser editable sin tocar código). `evaluar_formula` ejecuta una tubería
# ORDENADA de componentes de un catálogo CERRADO -- nunca evalúa una expresión arbitraria
# (superficie de ejecución inaceptable en un módulo que mueve dinero real). Cada
# componente aporta un monto ya resuelto por el llamador (servicio); esta función solo
# decide CÓMO se combinan (sumar/restar/multiplicar) y en qué orden, con piso $0 final.
# ══════════════════════════════════════════════════════════════════════════════════
OPERADOR_SUMAR = "sumar"
OPERADOR_RESTAR = "restar"
OPERADOR_MULTIPLICAR = "multiplicar"

# Catálogo cerrado de componentes soportados por el motor (validado por el servicio antes
# de guardar una fórmula -- ver CommissionConfigService). Documentado aquí porque es la
# única fuente de verdad de qué aporta cada clave.
COMPONENTES_FORMULA = frozenset({
    "base_lineas_venta", "base_cobranza", "contado_agencia",
    "factor_tipo_vendedor", "multiplicador_cumplimiento", "devoluciones", "bonos",
})


@dataclass(frozen=True)
class PasoFormula:
    orden: int
    componente: str
    operador: str
    monto: float  # ya resuelto por el servicio antes de llamar a evaluar_formula


@dataclass(frozen=True)
class ResultadoFormula:
    comision_final: float
    pasos: tuple[dict, ...]  # traza: {orden, componente, operador, monto, acumulado_tras_paso}


def evaluar_formula(pasos: list[PasoFormula]) -> ResultadoFormula:
    """Ejecuta la tubería en orden de `orden` ascendente. `sumar`/`restar` operan sobre el
    acumulado; `multiplicar` reemplaza el acumulado por `acumulado × monto` (monto es un
    FACTOR en ese caso, p.ej. 1.2 para +20%, no un monto en dinero -- lo resuelve el
    servicio según el componente). Piso $0 al final, igual que el motor anterior."""
    acumulado = 0.0
    traza = []
    for p in sorted(pasos, key=lambda x: x.orden):
        if p.operador == OPERADOR_SUMAR:
            acumulado += p.monto
        elif p.operador == OPERADOR_RESTAR:
            acumulado -= p.monto
        elif p.operador == OPERADOR_MULTIPLICAR:
            acumulado *= p.monto
        else:
            raise ValueError(f"Operador de fórmula no soportado: {p.operador!r}")
        traza.append({
            "orden": p.orden, "componente": p.componente, "operador": p.operador,
            "monto": round(p.monto, 4), "acumulado_tras_paso": round(acumulado, 4),
        })
    return ResultadoFormula(comision_final=round(max(0.0, acumulado), 4), pasos=tuple(traza))


def calcular_base_lineas_venta(
    lineas: list[LineaComisionable], matriz: list[ReglaCategoria], rangos_credito: list[RangoCredito],
    config: ConfigComisionVariable,
) -> tuple[float, tuple[DesgloseLinea, ...]]:
    """Componente `base_lineas_venta` de la fórmula (auditoría 44 §2.2): la Σ de líneas
    por margen/categoría que YA calculaba `calcular_comision_variable`, expuesta como
    pieza reutilizable de la tubería declarativa en vez de estar sólo embebida en esa
    función. `calcular_comision_variable` sigue siendo la ruta legacy (fórmula 'actual')
    y no se modifica -- esta función se usa desde el motor de fórmula genérico
    (`CommissionService._calcular_variable_formula`) cuando la fórmula vigente sea otra."""
    desglose = tuple(_calcular_linea(l, matriz, rangos_credito, config) for l in lineas)
    return round(sum(d.comision_linea for d in desglose), 4), desglose


def es_vendedor_nuevo(fecha_ingreso: datetime.date | None, anio: int, mes: int, meses_umbral: int) -> bool:
    """Mismo criterio que `GoalMLService._ajustar_meta_por_tipo`: un vendedor dentro de
    sus primeros `meses_umbral` meses (`COMISION_VENDEDOR_NUEVO_MESES`) recibe una meta
    sustituida por el promedio del equipo, no un múltiplo de su propio histórico -- por
    eso no hay factor de tipo que revertir para él (ver `resolver_meta_sin_ajuste_tipo`)."""
    if fecha_ingreso is None:
        return False
    meses_antiguedad = (anio - fecha_ingreso.year) * 12 + (mes - fecha_ingreso.month)
    return 0 <= meses_antiguedad < meses_umbral


def resolver_meta_sin_ajuste_tipo(
    monto_meta_persistido: float,
    tipo_vendedor: str | None,
    fecha_ingreso: datetime.date | None,
    anio: int,
    mes: int,
    meta_factor_externo: float,
    meta_factor_interno: float,
    vendedor_nuevo_meses: int,
) -> float:
    """Recupera la meta ANTES del ajuste por tipo de vendedor (auditoría: doble ajuste
    por tipo en Comisiones Variables).

    `GoalMLService._ajustar_meta_por_tipo` ya multiplicó la meta base por
    `meta_factor_externo` (más dura, +10% por defecto) o `meta_factor_interno` (más
    floja, -5% por defecto) al generarla -- ese es `monto_meta_persistido`. Si el
    % de cumplimiento de la comisión variable (`venta_real / meta`) se calcula contra
    ESA misma meta ya ajustada, el ajuste por tipo se aplica una SEGUNDA vez: un externo
    con meta más dura cae más fácil al tramo "Lejos" (comisión en 0%, `piso_lejos`) y un
    interno con meta más floja llega más fácil a "Excelente" (bono +20%,
    `mult_excelente`) -- sumándose al descuento/premio que YA le aplica `factor_tipo`
    sobre cada línea. Reportado en producción: en un mes reconstruido, todos los
    externos con comisión en $0.00 y todos los internos con comisión elevada, aunque
    su venta real no fuera tan distinta.

    Esta función deshace el ajuste multiplicativo para que el tramo de cumplimiento se
    decida sobre una vara neutral (la meta estadística real, sin favorecer ni castigar
    por tipo). Un vendedor "nuevo" no tiene factor que revertir -- su meta fue
    SUSTITUIDA por el promedio del equipo, no multiplicada por un factor de tipo."""
    if monto_meta_persistido <= 0 or es_vendedor_nuevo(fecha_ingreso, anio, mes, vendedor_nuevo_meses):
        return monto_meta_persistido
    factor = meta_factor_interno if tipo_vendedor == "interno" else meta_factor_externo
    return monto_meta_persistido / factor if factor > 0 else monto_meta_persistido


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
