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
from app.services.commission_engine import GRUPO_EXCLUIDO, calcular_comision, fecha_referencia_periodo
from app.services.commission_variable_engine import calcular_comision_variable_completa, resolver_componentes_formula

MESES_PROYECCION_VALIDOS = (3, 6)


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


@dataclass
class ResumenProyeccionComision:
    meses_historico: int
    periodo_proyectado: str
    vendedores_proyectados: int
    comision_variable_total_proyectada: float
    margen_bruto_total_promedio: float
    tasa_efectiva_pct_global: float
    detalle: list[ProyeccionVendedor]


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
            rangos_credito_periodo = self.commission_config_repo.get_factores_credito_as_rangos(fecha_periodo)

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

    def reconstruir_mes_especifico(self, anio: int, mes: int) -> ResumenProyeccionComision:
        """"¿Cuánto hubiera pagado ESTE mes con la configuración de comisión variable
        vigente HOY (matriz de categorías, factores de crédito, tipo de vendedor)?" --
        a diferencia de `proyectar_comision_variable` (que promedia 3/6 meses y asume
        cumplimiento neutro porque proyecta un mes futuro sin meta todavía), aquí el mes
        elegido ya cerró: se usa su meta REAL (`goal.monto_meta`), sus devoluciones
        reales y sus bonos reales (venta cruzada/cliente nuevo/cobranza), exactamente
        igual que `simular()` calcula el esquema variable real -- pero sin comparar
        contra el esquema plano, mismo recorte que pidió gerencia para este panel."""
        hoy = datetime.date.today()
        if (anio, mes) > (hoy.year, hoy.month):
            raise ValidationError("No se puede reconstruir un mes futuro: todavía no existen ventas reales.")

        fecha_config = hoy
        fecha_periodo = fecha_referencia_periodo(anio, mes)
        formula_componentes = resolver_componentes_formula(self.commission_config_repo)
        matriz_hoy = self.commission_config_repo.get_matriz_as_reglas(fecha_config)
        rangos_credito_hoy = self.commission_config_repo.get_factores_credito_as_rangos(fecha_config)
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

            # `fecha_config=hoy` (matriz/crédito/tramos/factor_tipo/agencia VIGENTES HOY:
            # "¿cuánto pagaría este mes con la configuración de HOY?"), pero
            # `fecha_config_vendedor_meta=fecha_periodo` para deshacer el ajuste de la
            # meta con el tipo de vendedor VIGENTE EN ESE PERÍODO histórico (no el de
            # hoy, que puede haber cambiado desde entonces) -- mismo criterio que ya
            # tenía este método antes de consolidarse en el motor compartido.
            resultado = calcular_comision_variable_completa(
                goal_repo=self.goal_repo, commission_config_repo=self.commission_config_repo,
                vendedor_origen=vendedor, anio=anio, mes=mes,
                venta_real=venta_neta, monto_meta=monto_meta,
                fecha_config=fecha_config, fecha_config_vendedor_meta=fecha_periodo,
                formula_componentes=formula_componentes, matriz=matriz_hoy, rangos_credito=rangos_credito_hoy,
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
            ))

        detalle.sort(key=lambda d: d.comision_variable_proyectada, reverse=True)

        return ResumenProyeccionComision(
            meses_historico=1, periodo_proyectado=periodo,
            vendedores_proyectados=len(detalle), comision_variable_total_proyectada=round(comision_total, 2),
            margen_bruto_total_promedio=round(margen_total, 2),
            tasa_efectiva_pct_global=round(comision_total / margen_total * 100, 2) if margen_total > 0 else 0.0,
            detalle=detalle,
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
        rangos_credito_hoy = self.commission_config_repo.get_factores_credito_as_rangos(fecha_config)

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

            n = len(periodos)
            comision_promedio = comision_acumulada / n
            margen_promedio = margen_acumulado / n
            tasa_efectiva = (comision_promedio / margen_promedio * 100) if margen_promedio > 0 else 0.0

            comision_total += comision_promedio
            margen_total += margen_promedio

            detalle.append(ProyeccionVendedor(
                vendedor_origen=vendedor, nombre_vendedor=nombres.get(vendedor),
                periodo_proyectado=periodo_proyectado, meses_historico_usados=n,
                venta_neta_promedio=round(venta_acumulada / n, 2), margen_bruto_promedio=round(margen_promedio, 2),
                comision_variable_proyectada=round(comision_promedio, 2), tasa_efectiva_pct=round(tasa_efectiva, 2),
            ))

        detalle.sort(key=lambda d: d.comision_variable_proyectada, reverse=True)

        return ResumenProyeccionComision(
            meses_historico=meses_historico, periodo_proyectado=periodo_proyectado,
            vendedores_proyectados=len(detalle), comision_variable_total_proyectada=round(comision_total, 2),
            margen_bruto_total_promedio=round(margen_total, 2),
            tasa_efectiva_pct_global=round(comision_total / margen_total * 100, 2) if margen_total > 0 else 0.0,
            detalle=detalle,
        )
