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

from app.core.config import settings
from app.core.exceptions import ValidationError
from app.repositories.catalog_repository import CatalogRepository
from app.repositories.commission_config_repository import CommissionConfigRepository
from app.repositories.goal_repository import GoalRepository
from app.services.commission_bonus import calcular_bonos_periodo
from app.services.commission_engine import (
    GRUPO_EXCLUIDO, ConfigComisionVariable, LineaComisionable, calcular_comision, calcular_comision_variable,
    fecha_referencia_periodo,
)

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
        persistidas) contra el esquema variable (matriz/crédito/tipo vigentes)."""
        hoy = datetime.date.today()
        ancla_anio, ancla_mes = (anio_desde, mes_desde) if anio_desde and mes_desde else (hoy.year, hoy.month)
        periodos = _meses_anteriores(ancla_anio, ancla_mes, meses)

        config = ConfigComisionVariable(
            tope_descuento_pct=settings.COMISION_TOPE_DESCUENTO_PCT,
            tasa_minima_sin_costo_pct=settings.COMISION_TASA_MINIMA_SIN_COSTO_PCT,
            umbral_subtotal_x=settings.COMISION_UMBRAL_SUBTOTAL_X,
            mult_excelente=settings.COMISION_MULT_EXCELENTE, mult_cerca=settings.COMISION_MULT_CERCA,
            piso_lejos=settings.COMISION_PISO_LEJOS,
        )

        detalle: list[SimulacionVendedorMes] = []
        costo_total_plana = 0.0
        costo_total_variable = 0.0
        margen_bruto_total = 0.0
        vendedores_vistos: set[str] = set()

        for anio, mes in periodos:
            fecha_periodo = fecha_referencia_periodo(anio, mes)
            matriz = self.commission_config_repo.get_matriz_as_reglas(fecha_periodo)
            rangos_credito = self.commission_config_repo.get_factores_credito_as_rangos(fecha_periodo)

            vendedores = self.goal_repo.get_vendors_with_sales_in_period(anio, mes)
            for vendedor in vendedores:
                vendedores_vistos.add(vendedor)
                goal = self.goal_repo.get_goal_for_period(vendedor, anio, mes)
                venta_neta = self.goal_repo.get_vendor_net_sales_period(vendedor, anio, mes)

                monto_meta = float(goal.monto_meta) if goal else 0.0
                comision_base_pct = float(goal.comision_base_pct) if goal else 0.0
                bono = float(goal.bono_sobrecumplimiento) if goal else 0.0
                c_plana = calcular_comision(venta_neta, monto_meta, comision_base_pct, bono)

                lineas_repo = self.goal_repo.get_commission_lines(vendedor, anio, mes)
                lineas = [
                    LineaComisionable(
                        codart=l.codart, clase=l.clase, subclase=l.subclase, es_servicio=l.es_servicio,
                        subtotal_neto=l.subtotal_neto, margen_bruto=l.margen_bruto,
                        valor_descuento=l.valor_descuento, dias_plazo=l.dias_plazo,
                    )
                    for l in lineas_repo
                ]
                config_vendedor = self.commission_config_repo.get_config_vendedor(vendedor, fecha_periodo)
                factor_tipo = (
                    float(config_vendedor.factor_tipo) if config_vendedor else settings.COMISION_FACTOR_EXTERNO_DEFAULT
                )
                devoluciones = self.goal_repo.get_vendor_devoluciones_period(vendedor, anio, mes)
                # Dos pasadas, igual que el cálculo real (CommissionService._calcular_variable,
                # docs/auditoria/35_actualizacion_modulo_metas.md H3): el bono de cobranza es un
                # % ADICIONAL sobre la comisión post-cumplimiento, así que hace falta conocerla
                # antes de poder sumar los bonos. Antes la simulación siempre pasaba
                # `bonos_total=0.0` y subestimaba el costo real del esquema variable.
                pre_bonos = calcular_comision_variable(
                    lineas=lineas, matriz=matriz, rangos_credito=rangos_credito, factor_tipo_vendedor=factor_tipo,
                    venta_real=venta_neta, monto_meta=monto_meta, devoluciones_mes=devoluciones,
                    bonos_total=0.0, config=config,
                )
                bonos_total = calcular_bonos_periodo(
                    self.goal_repo, vendedor, anio, mes, pre_bonos.comision_post_cumplimiento,
                )
                c_variable = (
                    pre_bonos if bonos_total == 0.0 else calcular_comision_variable(
                        lineas=lineas, matriz=matriz, rangos_credito=rangos_credito, factor_tipo_vendedor=factor_tipo,
                        venta_real=venta_neta, monto_meta=monto_meta, devoluciones_mes=devoluciones,
                        bonos_total=bonos_total, config=config,
                    )
                )

                margen_periodo = sum(l.margen_bruto or 0.0 for l in lineas_repo)
                margen_bruto_total += margen_periodo
                costo_total_plana += c_plana.comision_devengada
                costo_total_variable += c_variable.comision_final

                diferencia = c_variable.comision_final - c_plana.comision_devengada
                diferencia_pct = (
                    round((diferencia / c_plana.comision_devengada) * 100, 2) if c_plana.comision_devengada > 0 else None
                )
                detalle.append(SimulacionVendedorMes(
                    vendedor_origen=vendedor, anio=anio, mes=mes, venta_neta=round(venta_neta, 2),
                    comision_plana=c_plana.comision_devengada, comision_variable=c_variable.comision_final,
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
        este resultado) -- es exclusivamente sobre el esquema variable, por eso
        `venta_real == monto_meta` en cada mes histórico (cumplimiento neutro, tramo
        META, multiplicador 1.0): el propósito es aislar la fórmula de
        margen/categoría/crédito/tipo de vendedor, no adivinar si cumplirá una meta
        futura que la Consola de Metas (motor IQR) todavía no ha generado. Bonos y
        devoluciones también se omiten de la proyección por el mismo motivo: son
        eventos puntuales del mes ya cerrado, no un patrón proyectable con la misma
        base estadística que la venta."""
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
        matriz = self.commission_config_repo.get_matriz_as_reglas(fecha_config)
        rangos_credito = self.commission_config_repo.get_factores_credito_as_rangos(fecha_config)
        config = ConfigComisionVariable(
            tope_descuento_pct=settings.COMISION_TOPE_DESCUENTO_PCT,
            tasa_minima_sin_costo_pct=settings.COMISION_TASA_MINIMA_SIN_COSTO_PCT,
            umbral_subtotal_x=settings.COMISION_UMBRAL_SUBTOTAL_X,
            mult_excelente=settings.COMISION_MULT_EXCELENTE, mult_cerca=settings.COMISION_MULT_CERCA,
            piso_lejos=settings.COMISION_PISO_LEJOS,
        )

        vendedores: set[str] = set()
        for anio, mes in periodos:
            vendedores.update(self.goal_repo.get_vendors_with_sales_in_period(anio, mes))
        nombres = self.catalog_repo.get_vendedores_info(sorted(vendedores))

        detalle: list[ProyeccionVendedor] = []
        comision_total = 0.0
        margen_total = 0.0

        for vendedor in sorted(vendedores):
            config_vendedor = self.commission_config_repo.get_config_vendedor(vendedor, fecha_config)
            factor_tipo = (
                float(config_vendedor.factor_tipo) if config_vendedor else settings.COMISION_FACTOR_EXTERNO_DEFAULT
            )

            venta_acumulada = 0.0
            margen_acumulado = 0.0
            comision_acumulada = 0.0
            for anio, mes in periodos:
                venta_neta = self.goal_repo.get_vendor_net_sales_period(vendedor, anio, mes)
                lineas_repo = self.goal_repo.get_commission_lines(vendedor, anio, mes)
                lineas = [
                    LineaComisionable(
                        codart=l.codart, clase=l.clase, subclase=l.subclase, es_servicio=l.es_servicio,
                        subtotal_neto=l.subtotal_neto, margen_bruto=l.margen_bruto,
                        valor_descuento=l.valor_descuento, dias_plazo=l.dias_plazo,
                    )
                    for l in lineas_repo
                ]
                resultado = calcular_comision_variable(
                    lineas=lineas, matriz=matriz, rangos_credito=rangos_credito, factor_tipo_vendedor=factor_tipo,
                    venta_real=venta_neta, monto_meta=venta_neta, devoluciones_mes=0.0, bonos_total=0.0,
                    config=config,
                )
                # El margen mostrado excluye las líneas que el motor clasificó como
                # grupo X (excluidas de comisión, ej. clase Z-999 "chatarra" -- ver
                # docs/features/matriz_categorias_comision_variable.md §4): incluirlas
                # aquí distorsionaba el margen mostrado con valores de costo rotos de
                # líneas que ya no aportan nada a la comisión, y podía volver el
                # denominador negativo (comisión positiva / margen negativo -> 0.00%
                # engañoso). `desglose_lineas` preserva el mismo orden que `lineas`.
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
