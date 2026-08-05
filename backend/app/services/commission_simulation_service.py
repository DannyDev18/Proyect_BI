# backend/app/services/commission_simulation_service.py
"""Simulación retroactiva del esquema de Comisiones Variables (docs/features/
plan_integracion_comisiones_variables.md §3.4, Fase 2: "el argumento decisivo" para
gerencia). Solo lectura del EDW -- no persiste nada, a diferencia de
`CommissionService` (que sí congela snapshots del piloto en sombra).

Dos usos distintos conviven en esta clase, deliberadamente separados:
  - `simular()`: comparación retroactiva plano vs. variable de meses YA CERRADOS, con
    la configuración vigente al cierre de cada mes -- lo usa internamente
    `NotificationService._generar_divergencia_comisiones` (alerta de divergencia del
    piloto en sombra, docs/auditoria/31_modulo_notificaciones.md). NO tocar su forma de
    retorno sin revisar ese generador.
  - `proyectar_comision_variable()`: proyección hacia adelante, solo del esquema
    variable (sin comparar contra el plano), la que consume el panel "Simulación" de
    gerencia -- ver docs/manual_metas_y_comisiones.md §1.3.3."""
from __future__ import annotations

import datetime
from dataclasses import dataclass

from app.core.exceptions import ValidationError
from app.repositories.catalog_repository import CatalogRepository
from app.repositories.commission_config_repository import CommissionConfigRepository
from app.repositories.goal_repository import GoalRepository
from app.services.commission_engine import (
    ETIQUETAS_COMPONENTES_FORMULA, GRUPO_EXCLUIDO, OPERADOR_MULTIPLICAR, PasoFormula, calcular_comision,
    evaluar_formula, fecha_referencia_periodo,
)
from app.services.commission_variable_engine import (
    calcular_comision_variable_completa, resolver_componentes_formula, resolver_tramos_cumplimiento,
)

MESES_PROYECCION_VALIDOS = (3, 6)


@dataclass
class ComponenteComisionDetalle:
    """Un paso de la tubería de la fórmula, con etiqueta legible -- auditoría 45
    (docs/features/plan_comisiones_sobrecumplimiento_umbral_y_desglose.md §3.3): "cómo
    se construye la comisión, cuánto gané de cada cosa". `monto` es dinero ($) para
    `sumar`/`restar`, o un FACTOR adimensional para `multiplicar` (`es_factor=True`,
    la UI no debe formatearlo como moneda)."""
    orden: int
    componente: str
    etiqueta: str
    operador: str
    monto: float
    es_factor: bool
    acumulado_tras_paso: float


def _detalle_desde_traza(traza: tuple[dict, ...]) -> list[ComponenteComisionDetalle]:
    return [
        ComponenteComisionDetalle(
            orden=p["orden"], componente=p["componente"],
            etiqueta=ETIQUETAS_COMPONENTES_FORMULA.get(p["componente"], p["componente"]),
            operador=p["operador"], monto=p["monto"], es_factor=(p["operador"] == OPERADOR_MULTIPLICAR),
            acumulado_tras_paso=p["acumulado_tras_paso"],
        )
        for p in traza
    ]


@dataclass
class SimulacionVendedorMes:
    vendedor_origen: str
    anio: int
    mes: int
    venta_neta: float
    comision_plana: float
    comision_variable: float
    diferencia: float
    diferencia_pct: float | None


@dataclass
class ResumenSimulacion:
    meses_simulados: int
    vendedores_simulados: int
    costo_total_plana: float
    costo_total_variable: float
    margen_bruto_total: float
    pct_comision_sobre_margen_plana: float
    pct_comision_sobre_margen_variable: float
    detalle: list[SimulacionVendedorMes]


@dataclass
class ProyeccionVendedor:
    vendedor_origen: str
    nombre_vendedor: str | None
    periodo_proyectado: str
    meses_historico_usados: int
    venta_neta_promedio: float
    margen_bruto_promedio: float
    comision_variable_proyectada: float
    tasa_efectiva_pct: float
    # Auditoría 45: desglose de cómo se construyó la comisión (cuánto de cada
    # componente) + el tramo de cumplimiento efectivamente aplicado.
    pct_cumplimiento: float | None = None
    nivel: str | None = None  # etiqueta del tramo de cumplimiento alcanzado
    multiplicador_cumplimiento: float = 1.0
    comisiona: bool = True  # False cuando el tramo alcanzado paga con multiplicador 0
    componentes: list[ComponenteComisionDetalle] = None  # type: ignore[assignment]

    def __post_init__(self):
        if self.componentes is None:
            self.componentes = []


@dataclass
class ResumenProyeccionComision:
    meses_historico: int
    periodo_proyectado: str
    vendedores_proyectados: int
    comision_variable_total_proyectada: float
    margen_bruto_total_promedio: float
    tasa_efectiva_pct_global: float
    detalle: list[ProyeccionVendedor]
    # Fase 4 (docs/features/plan_motor_metas_v3_y_comisiones_unificadas.md, R-4,
    # auditoría 47 A-0.6): antes `reconstruir_mes_especifico` SIEMPRE usaba la
    # configuración vigente HOY para un mes ya cerrado, sin distinguirlo en la
    # respuesta -- confuso frente al cálculo real (`CommissionService`), que usa la
    # configuración vigente AL CIERRE de ese período. Se etiqueta explícitamente qué
    # modo produjo este resultado: `"reconstruccion_fiel"` (config al cierre, debe
    # coincidir centavo a centavo con lo que `CommissionService` calcularía/liquidaría
    # para ese período), `"config_actual"` (config de hoy, "qué pagaría si aplicara
    # hoy la config vigente a un mes pasado" -- puede diferir a propósito) o
    # `"proyeccion"` (meses futuros, siempre con la config de hoy, sin equivalente
    # real todavía).
    modo: str = "proyeccion"


def _meses_anteriores(anio: int, mes: int, cantidad: int) -> list[tuple[int, int]]:
    periodos = []
    a, m = anio, mes
    for _ in range(cantidad):
        periodos.append((a, m))
        m -= 1
        if m == 0:
            m = 12
            a -= 1
    return periodos


class CommissionSimulationService:
    def __init__(
        self, goal_repo: GoalRepository, commission_config_repo: CommissionConfigRepository,
        catalog_repo: CatalogRepository,
    ):
        self.goal_repo = goal_repo
        self.commission_config_repo = commission_config_repo
        self.catalog_repo = catalog_repo

    def simular(self, meses: int = 12, anio_desde: int | None = None, mes_desde: int | None = None) -> ResumenSimulacion:
        """Simula los últimos `meses` (o desde `anio_desde`/`mes_desde` si se especifica)
        comparando el esquema plano vigente (tasas configuradas por meta, ya
        persistidas) contra el TOTAL de Comisiones Variables (líneas de venta por
        margen/categoría + cobranza por tramo de días de cobro + ventas de contado de
        agencia, sumadas -- auditoría 44, corrección de diseño 2026-07-30: no son dos
        esquemas entre los que se elige, es un solo total). Delega en
        `commission_variable_engine.calcular_comision_variable_completa` -- el mismo
        cálculo que usa `CommissionService`, para que el simulador refleje exactamente
        lo que se liquidaría."""
        hoy = datetime.date.today()
        ancla_anio, ancla_mes = (anio_desde, mes_desde) if anio_desde and mes_desde else (hoy.year, hoy.month)
        periodos = _meses_anteriores(ancla_anio, ancla_mes, meses)

        # La fórmula (a diferencia de la matriz/crédito, que sí tienen vigencia por
        # fecha) es una sola resolución para toda la simulación -- ver
        # `resolver_componentes_formula`.
        formula_componentes = resolver_componentes_formula(self.commission_config_repo)

        detalle: list[SimulacionVendedorMes] = []
        costo_total_plana = 0.0
        costo_total_variable = 0.0
        margen_bruto_total = 0.0
        vendedores_vistos: set[str] = set()

        for anio, mes in periodos:
            fecha_periodo = fecha_referencia_periodo(anio, mes)
            # Matriz/crédito vigentes de ESTE período: una sola resolución por período,
            # reutilizada para todos los vendedores de ese mes (no una consulta por
            # vendedor).
            matriz_periodo = self.commission_config_repo.get_matriz_as_reglas(fecha_periodo)
            # Retirado (Fase 3, R-7, auditoría 30 H4): sin datos discriminantes reales.
            rangos_credito_periodo: list = []
            # Tramos de cumplimiento GENÉRICOS (perfil=None) del período -- una sola
            # resolución reutilizada por todos los vendedores, igual que matriz/crédito
            # (auditoría 45). Correcto mientras la única fuente real de tramos sea la
            # genérica (la semilla no diferencia por perfil); si en el futuro gerencia
            # configura tramos específicos por perfil, este pre-fetch dejaría de
            # reflejarlos para el simulador -- documentado, no silencioso.
            tramos_cumplimiento_periodo = resolver_tramos_cumplimiento(self.commission_config_repo, None, fecha_periodo)

            vendedores = self.goal_repo.get_vendors_with_sales_in_period(anio, mes)
            for vendedor in vendedores:
                vendedores_vistos.add(vendedor)
                goal = self.goal_repo.get_goal_for_period(vendedor, anio, mes)
                venta_neta = self.goal_repo.get_vendor_net_sales_period(vendedor, anio, mes)

                monto_meta = float(goal.monto_meta) if goal else 0.0
                comision_base_pct = float(goal.comision_base_pct) if goal else 0.0
                bono = float(goal.bono_sobrecumplimiento) if goal else 0.0
                c_plana = calcular_comision(venta_neta, monto_meta, comision_base_pct, bono)

                resultado = calcular_comision_variable_completa(
                    goal_repo=self.goal_repo, commission_config_repo=self.commission_config_repo,
                    vendedor_origen=vendedor, anio=anio, mes=mes,
                    venta_real=venta_neta, monto_meta=monto_meta, fecha_config=fecha_periodo,
                    formula_componentes=formula_componentes, matriz=matriz_periodo, rangos_credito=rangos_credito_periodo,
                    tramos_cumplimiento=tramos_cumplimiento_periodo,
                )

                # Margen de las líneas de venta (para el % costo/margen del resumen) --
                # consulta propia porque el detalle línea a línea no forma parte del
                # resultado agregado del motor compartido.
                lineas_repo = self.goal_repo.get_commission_lines(vendedor, anio, mes)
                margen_periodo = sum(l.margen_bruto or 0.0 for l in lineas_repo)
                margen_bruto_total += margen_periodo
                costo_total_plana += c_plana.comision_devengada
                costo_total_variable += resultado.comision_final

                diferencia = resultado.comision_final - c_plana.comision_devengada
                diferencia_pct = (
                    round((diferencia / c_plana.comision_devengada) * 100, 2) if c_plana.comision_devengada > 0 else None
                )
                detalle.append(SimulacionVendedorMes(
                    vendedor_origen=vendedor, anio=anio, mes=mes, venta_neta=round(venta_neta, 2),
                    comision_plana=c_plana.comision_devengada, comision_variable=resultado.comision_final,
                    diferencia=round(diferencia, 2), diferencia_pct=diferencia_pct,
                ))

        return ResumenSimulacion(
            meses_simulados=len(periodos), vendedores_simulados=len(vendedores_vistos),
            costo_total_plana=round(costo_total_plana, 2), costo_total_variable=round(costo_total_variable, 2),
            margen_bruto_total=round(margen_bruto_total, 2),
            pct_comision_sobre_margen_plana=(
                round(costo_total_plana / margen_bruto_total * 100, 2) if margen_bruto_total else 0.0
            ),
            pct_comision_sobre_margen_variable=(
                round(costo_total_variable / margen_bruto_total * 100, 2) if margen_bruto_total else 0.0
            ),
            detalle=detalle,
        )

    def reconstruir_mes_especifico(
        self, anio: int, mes: int, usar_configuracion_de_hoy: bool = True,
    ) -> ResumenProyeccionComision:
        """Reconstruye la comisión de un mes YA CERRADO con su meta REAL
        (`goal.monto_meta`), sus devoluciones reales y sus bonos reales (venta
        cruzada/cliente nuevo/cobranza) -- a diferencia de `proyectar_comision_variable`
        (que promedia 3/6 meses y asume cumplimiento neutro porque proyecta un mes
        futuro sin meta todavía).

        Dos modos explícitos (Fase 4, docs/features/plan_motor_metas_v3_y_comisiones_
        unificadas.md, R-4, auditoría 47 A-0.6 -- antes esta función SIEMPRE usaba la
        config de hoy sin decirlo, lo que el usuario leía como "el simulador no
        concuerda con las comisiones reales"):
          - `usar_configuracion_de_hoy=False` ("reconstrucción fiel"): usa la
            configuración vigente AL CIERRE del período, exactamente igual que
            `CommissionService._calcular_variable` -- debe coincidir centavo a centavo
            con lo que el panel "Comisiones devengadas" muestra/liquidaría para ese
            mismo período (ver test de paridad).
          - `usar_configuracion_de_hoy=True` (default, comportamiento histórico): usa
            la configuración vigente HOY -- "¿cuánto se hubiera pagado ese mes si la
            configuración actual ya hubiera estado vigente?", un ejercicio de "qué
            pasaría si", no una reconstrucción contable."""
        hoy = datetime.date.today()
        if (anio, mes) > (hoy.year, hoy.month):
            raise ValidationError("No se puede reconstruir un mes futuro: todavía no existen ventas reales.")

        fecha_periodo = fecha_referencia_periodo(anio, mes)
        fecha_config = fecha_periodo if not usar_configuracion_de_hoy else hoy
        formula_componentes = resolver_componentes_formula(self.commission_config_repo)
        matriz_config = self.commission_config_repo.get_matriz_as_reglas(fecha_config)
        # Retirado (Fase 3, R-7, auditoría 30 H4): sin datos discriminantes reales.
        rangos_credito_config: list = []
        tramos_cumplimiento_config = resolver_tramos_cumplimiento(self.commission_config_repo, None, fecha_config)
        vendedores = sorted(self.goal_repo.get_vendors_with_sales_in_period(anio, mes))
        nombres = self.catalog_repo.get_vendedores_info(vendedores)
        periodo = f"{anio:04d}-{mes:02d}"

        detalle: list[ProyeccionVendedor] = []
        comision_total = 0.0
        margen_total = 0.0

        for vendedor in vendedores:
            venta_neta = self.goal_repo.get_vendor_net_sales_period(vendedor, anio, mes)
            goal = self.goal_repo.get_goal_for_period(vendedor, anio, mes)
            monto_meta = float(goal.monto_meta) if goal else 0.0

            # `fecha_config_vendedor_meta=fecha_periodo` siempre: el tipo de vendedor
            # para DESHACER el ajuste de la meta debe ser el vigente EN ESE PERÍODO
            # histórico, no el de hoy -- incluso en modo "config de hoy", donde el
            # resto de la configuración sí es la actual (mismo criterio que ya tenía
            # este método antes de consolidarse en el motor compartido).
            resultado = calcular_comision_variable_completa(
                goal_repo=self.goal_repo, commission_config_repo=self.commission_config_repo,
                vendedor_origen=vendedor, anio=anio, mes=mes,
                venta_real=venta_neta, monto_meta=monto_meta,
                fecha_config=fecha_config, fecha_config_vendedor_meta=fecha_periodo,
                formula_componentes=formula_componentes, matriz=matriz_config, rangos_credito=rangos_credito_config,
                tramos_cumplimiento=tramos_cumplimiento_config,
            )

            lineas_repo = self.goal_repo.get_commission_lines(vendedor, anio, mes)
            margen_mes = sum(
                (l.margen_bruto or 0.0)
                for l, d in zip(lineas_repo, resultado.desglose_lineas)
                if d.grupo != GRUPO_EXCLUIDO
            )
            tasa_efectiva = (resultado.comision_final / margen_mes * 100) if margen_mes > 0 else 0.0

            comision_total += resultado.comision_final
            margen_total += margen_mes

            detalle.append(ProyeccionVendedor(
                vendedor_origen=vendedor, nombre_vendedor=nombres.get(vendedor),
                periodo_proyectado=periodo, meses_historico_usados=1,
                venta_neta_promedio=round(venta_neta, 2), margen_bruto_promedio=round(margen_mes, 2),
                comision_variable_proyectada=round(resultado.comision_final, 2), tasa_efectiva_pct=round(tasa_efectiva, 2),
                pct_cumplimiento=resultado.pct_cumplimiento, nivel=(resultado.tramo.etiqueta if resultado.tramo else None),
                multiplicador_cumplimiento=(resultado.tramo.multiplicador if resultado.tramo else 1.0),
                comisiona=(resultado.tramo.multiplicador > 0 if resultado.tramo else True),
                componentes=_detalle_desde_traza(resultado.traza_formula),
            ))

        detalle.sort(key=lambda d: d.comision_variable_proyectada, reverse=True)

        return ResumenProyeccionComision(
            meses_historico=1, periodo_proyectado=periodo,
            vendedores_proyectados=len(detalle), comision_variable_total_proyectada=round(comision_total, 2),
            margen_bruto_total_promedio=round(margen_total, 2),
            tasa_efectiva_pct_global=round(comision_total / margen_total * 100, 2) if margen_total > 0 else 0.0,
            detalle=detalle,
            modo=("config_actual" if usar_configuracion_de_hoy else "reconstruccion_fiel"),
        )

    def proyectar_comision_variable(self, meses_historico: int = 3) -> ResumenProyeccionComision:
        """Proyección hacia adelante -- distinta de `simular()` en tres cosas a
        propósito: (1) toma como base los `meses_historico` meses YA CERRADOS más
        recientes (excluye el mes en curso, incompleto, igual que hace el motor IQR de
        metas con su ventana de tendencia) para estimar el PRÓXIMO mes calendario, no
        para reconstruir meses pasados; (2) usa la matriz/crédito/tipo de vendedor
        VIGENTES HOY (no la vigente en cada mes histórico), porque el objetivo es "si
        la configuración actual se aplica al patrón de venta reciente de cada vendedor,
        ¿cuánto pagaría el próximo mes" -- no una reconstrucción contable de lo ya
        cerrado; (3) no compara contra el esquema plano (`comision_plana` no existe en
        este resultado) -- es exclusivamente sobre el TOTAL de Comisiones Variables
        (líneas de venta + cobranza + contado de agencia, sumadas -- auditoría 44), por
        eso `venta_real == monto_meta` en cada mes histórico (cumplimiento neutro, tramo
        META, multiplicador 1.0): el propósito es aislar la fórmula configurada
        (margen/categoría/crédito/cobranza/tipo de vendedor), no adivinar si cumplirá una
        meta futura que la Consola de Metas (motor IQR) todavía no ha generado. Bonos y
        devoluciones también se omiten de la proyección por el mismo motivo: son
        eventos puntuales del mes ya cerrado, no un patrón proyectable con la misma
        base estadística que la venta/cobranza."""
        if meses_historico not in MESES_PROYECCION_VALIDOS:
            raise ValidationError(
                f"La proyección solo admite ventanas de {' o '.join(str(m) for m in MESES_PROYECCION_VALIDOS)} meses."
            )

        hoy = datetime.date.today()
        anio_ancla, mes_ancla = hoy.year, hoy.month - 1
        if mes_ancla == 0:
            anio_ancla, mes_ancla = anio_ancla - 1, 12
        periodos = _meses_anteriores(anio_ancla, mes_ancla, meses_historico)

        anio_proy, mes_proy = hoy.year, hoy.month + 1
        if mes_proy == 13:
            anio_proy, mes_proy = anio_proy + 1, 1
        periodo_proyectado = f"{anio_proy:04d}-{mes_proy:02d}"

        fecha_config = hoy
        # Config vigente HOY: una sola resolución para toda la proyección (matriz/
        # crédito/fórmula no varían por vendedor ni por mes histórico en este método).
        formula_componentes = resolver_componentes_formula(self.commission_config_repo)
        matriz_hoy = self.commission_config_repo.get_matriz_as_reglas(fecha_config)
        # Retirado (Fase 3, R-7, auditoría 30 H4): sin datos discriminantes reales.
        rangos_credito_hoy: list = []
        tramos_cumplimiento_hoy = resolver_tramos_cumplimiento(self.commission_config_repo, None, fecha_config)

        vendedores: set[str] = set()
        for anio, mes in periodos:
            vendedores.update(self.goal_repo.get_vendors_with_sales_in_period(anio, mes))
        nombres = self.catalog_repo.get_vendedores_info(sorted(vendedores))

        detalle: list[ProyeccionVendedor] = []
        comision_total = 0.0
        margen_total = 0.0

        for vendedor in sorted(vendedores):
            venta_acumulada = 0.0
            margen_acumulado = 0.0
            comision_acumulada = 0.0
            # Auditoría 45: acumula el paso de cada componente de la tubería a través de
            # los `n` meses históricos, por `componente` (la estructura -- orden/
            # operador -- es la misma en todos los meses, ya que la fórmula y los
            # tramos de cumplimiento se resuelven una sola vez, vigentes HOY). Los
            # componentes `sumar`/`restar` (montos en $) se PROMEDIAN; los
            # `multiplicar` (factores adimensionales) son constantes entre meses --
            # `factor_tipo_vendedor` porque la config de vendedor es la de hoy para
            # todos los meses, `multiplicador_cumplimiento` porque `venta_real ==
            # monto_meta` en cada mes histórico fuerza siempre el mismo % (100%) y por
            # lo tanto el mismo tramo -- así que solo se conserva el último valor visto.
            pasos_por_componente: dict[str, dict] = {}
            ultimo_tramo = None  # constante entre meses (ver comentario arriba) -- se captura una vez
            for anio, mes in periodos:
                venta_neta = self.goal_repo.get_vendor_net_sales_period(vendedor, anio, mes)
                # `aplicar_ajuste_meta_por_tipo=False`: `venta_real == monto_meta` ya
                # fuerza el cumplimiento neutro directamente -- pasarlo por
                # `resolver_meta_sin_ajuste_tipo` dividiría `monto_meta` por el factor de
                # tipo y rompería esa neutralidad para vendedores externos/internos.
                # `incluir_bonos`/`incluir_devoluciones=False`: omitidos a propósito (ver
                # docstring del método).
                resultado = calcular_comision_variable_completa(
                    goal_repo=self.goal_repo, commission_config_repo=self.commission_config_repo,
                    vendedor_origen=vendedor, anio=anio, mes=mes,
                    venta_real=venta_neta, monto_meta=venta_neta, fecha_config=fecha_config,
                    aplicar_ajuste_meta_por_tipo=False, incluir_bonos=False, incluir_devoluciones=False,
                    formula_componentes=formula_componentes, matriz=matriz_hoy, rangos_credito=rangos_credito_hoy,
                    tramos_cumplimiento=tramos_cumplimiento_hoy,
                )
                # El margen mostrado excluye las líneas que el motor clasificó como
                # grupo X (excluidas de comisión, ej. clase Z-999 "chatarra" -- ver
                # docs/features/matriz_categorias_comision_variable.md §4): incluirlas
                # aquí distorsionaba el margen mostrado con valores de costo rotos de
                # líneas que ya no aportan nada a la comisión, y podía volver el
                # denominador negativo (comisión positiva / margen negativo -> 0.00%
                # engañoso).
                lineas_repo = self.goal_repo.get_commission_lines(vendedor, anio, mes)
                margen_mes = sum(
                    (l.margen_bruto or 0.0)
                    for l, d in zip(lineas_repo, resultado.desglose_lineas)
                    if d.grupo != GRUPO_EXCLUIDO
                )

                venta_acumulada += venta_neta
                margen_acumulado += margen_mes
                comision_acumulada += resultado.comision_final
                if resultado.tramo is not None:
                    ultimo_tramo = resultado.tramo

                for p in resultado.traza_formula:
                    acc = pasos_por_componente.setdefault(p["componente"], {
                        "orden": p["orden"], "operador": p["operador"],
                        "es_factor": p["operador"] == OPERADOR_MULTIPLICAR, "monto": 0.0,
                    })
                    acc["monto"] = p["monto"] if acc["es_factor"] else acc["monto"] + p["monto"]

            n = len(periodos)
            comision_promedio = comision_acumulada / n
            margen_promedio = margen_acumulado / n
            tasa_efectiva = (comision_promedio / margen_promedio * 100) if margen_promedio > 0 else 0.0

            comision_total += comision_promedio
            margen_total += margen_promedio

            pasos_promedio = [
                PasoFormula(v["orden"], componente, v["operador"], v["monto"] if v["es_factor"] else round(v["monto"] / n, 4))
                for componente, v in pasos_por_componente.items()
            ]
            resultado_promedio_formula = evaluar_formula(pasos_promedio)

            detalle.append(ProyeccionVendedor(
                vendedor_origen=vendedor, nombre_vendedor=nombres.get(vendedor),
                periodo_proyectado=periodo_proyectado, meses_historico_usados=n,
                venta_neta_promedio=round(venta_acumulada / n, 2), margen_bruto_promedio=round(margen_promedio, 2),
                comision_variable_proyectada=round(comision_promedio, 2), tasa_efectiva_pct=round(tasa_efectiva, 2),
                # Cumplimiento neutro simulado (venta_real==monto_meta en cada mes
                # histórico -- ver docstring del método): 100% y el tramo que ese
                # porcentaje resuelve, no un cumplimiento real todavía inexistente.
                pct_cumplimiento=(100.0 if ultimo_tramo is not None else None),
                nivel=(ultimo_tramo.etiqueta if ultimo_tramo is not None else None),
                multiplicador_cumplimiento=(ultimo_tramo.multiplicador if ultimo_tramo is not None else 1.0),
                comisiona=(ultimo_tramo is None or ultimo_tramo.multiplicador > 0),
                componentes=_detalle_desde_traza(resultado_promedio_formula.pasos),
            ))

        detalle.sort(key=lambda d: d.comision_variable_proyectada, reverse=True)

        return ResumenProyeccionComision(
            meses_historico=meses_historico, periodo_proyectado=periodo_proyectado,
            vendedores_proyectados=len(detalle), comision_variable_total_proyectada=round(comision_total, 2),
            margen_bruto_total_promedio=round(margen_total, 2),
            tasa_efectiva_pct_global=round(comision_total / margen_total * 100, 2) if margen_total > 0 else 0.0,
            detalle=detalle,
            modo="proyeccion",
        )
