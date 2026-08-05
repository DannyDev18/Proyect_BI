# backend/scripts/backtest_motor_metas.py
"""Backtest motor-a-motor del motor de metas -- Fase 9.A de docs/features/
plan_motor_metas_v3_y_comisiones_unificadas.md (R-13). Herramienta de AUDITORÍA, no
código de producción: recalcula, con walk-forward real (solo histórico ESTRICTAMENTE
anterior a cada mes objetivo, nunca datos del propio mes o posteriores), la meta que
habría producido el motor v2 (estadístico puro, sin madurez/tipo/redondeo) y el motor v3
(pipeline modular vigente hoy en `metas_config_modulos`, incluida la etapa de madurez ya
activa) para cada vendedor activo en cada uno de los últimos `--meses` meses CERRADOS con
venta real -- y las compara contra la Venta Neta real de ese mes.

**Este backtest es el instrumento de calibración de la Fase 5** (§12.9-A del plan): la
configuración semilla del v3 se valida aquí con evidencia real del EDW, no por
suposición. No genera ni modifica ninguna fila de `metas_comerciales_operativas` --
100% de solo lectura contra `edw.fact_ventas_detalle`/`fact_devoluciones` y la
configuración vigente de comisiones/metas.

**Costo de comisión**: reutiliza `calcular_comision_variable_completa` (el MISMO motor
que liquida comisiones reales) con la meta recalculada por cada motor como denominador
del % de cumplimiento y el gate de la Fase 2 activo -- nunca una aproximación inventada;
si un vendedor no tiene datos suficientes para calcularla realmente, se omite (nunca se
rellena con un placeholder).

Uso:
    docker exec bi_backend python scripts/backtest_motor_metas.py --meses 12
    docker exec bi_backend python scripts/backtest_motor_metas.py --meses 12 --md docs_out/backtest.md
"""
import argparse
import logging
import os
import statistics
import sys

import sqlalchemy as sa
from sqlalchemy.orm import Session

logger = logging.getLogger("Backend.BacktestMotorMetas")
logging.basicConfig(level=logging.INFO, format="%(levelname)-5.5s [%(name)s] %(message)s")

_BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)


def _meses_cerrados(db: Session, n: int) -> list[tuple[int, int]]:
    """Últimos `n` meses calendario con al menos una venta real (`fact_ventas_detalle`),
    más recientes primero -- no asume que el mes en curso esté completo, simplemente usa
    lo que el EDW realmente tiene poblado."""
    rows = db.execute(sa.text("""
        SELECT DISTINCT d.anio, d.mes
        FROM edw.fact_ventas_detalle f
        JOIN edw.dim_fecha d ON f.fecha_sk = d.fecha_sk
        JOIN edw.dim_estado_documento ed ON f.estado_documento_sk = ed.estado_documento_sk
        WHERE ed.estado_documento_sk <> -1
        ORDER BY d.anio DESC, d.mes DESC
        LIMIT :n
    """), {"n": n}).fetchall()
    return [(int(r[0]), int(r[1])) for r in rows]


def _vendedores_activos(db: Session) -> list[str]:
    rows = db.execute(sa.text(
        "SELECT codven FROM edw.dim_vendedor WHERE activo = TRUE AND codven <> '-1' ORDER BY codven"
    )).fetchall()
    return [str(r[0]) for r in rows]


def _percentiles(valores: list[float]) -> dict[str, float]:
    if not valores:
        return {"p10": 0.0, "p25": 0.0, "mediana": 0.0, "p75": 0.0, "p90": 0.0}
    ordenados = sorted(valores)
    return {
        "p10": statistics.quantiles(ordenados, n=10, method="inclusive")[0] if len(ordenados) > 1 else ordenados[0],
        "p25": statistics.quantiles(ordenados, n=4, method="inclusive")[0] if len(ordenados) > 1 else ordenados[0],
        "mediana": statistics.median(ordenados),
        "p75": statistics.quantiles(ordenados, n=4, method="inclusive")[2] if len(ordenados) > 1 else ordenados[0],
        "p90": statistics.quantiles(ordenados, n=10, method="inclusive")[8] if len(ordenados) > 1 else ordenados[0],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--meses", type=int, default=12, help="Meses cerrados a incluir en el backtest (default 12).")
    parser.add_argument("--md", type=str, default=None, help="Ruta opcional para escribir el reporte también en Markdown.")
    args = parser.parse_args()

    from app.core.config import settings
    from app.repositories.commission_config_repository import CommissionConfigRepository
    from app.repositories.goal_repository import GoalRepository, VendorMonthlySales
    from app.repositories.meta_config_modulo_repository import MetaConfigModuloRepository
    from app.services.commission_engine import fecha_referencia_periodo
    from app.services.commission_variable_engine import (
        calcular_comision_variable_completa, resolver_componentes_formula, resolver_tramos_cumplimiento,
    )
    from app.services.goal_calculation_engine import (
        DEFAULT_PARAMETROS, IQRGoalCalculationEngine, RegistroMensual, ajustar_meta_por_madurez,
    )
    from app.services.goal_pipeline_stages import aplicar_factor_tipo, redondear_meta
    from app.services.meta_config_modulo_service import MetaConfigModuloService
    # Registra TODOS los modelos en el mismo registro declarativo antes de la primera
    # consulta ORM -- `MetaConfigModulo.usuario` referencia `User` por nombre de clase
    # (string), que solo resuelve si `app.models.user` ya fue importado en algún punto
    # del proceso; los scripts standalone (a diferencia de la app FastAPI, que importa
    # `app.database.base` en el arranque) no lo hacen por sí solos.
    import app.database.base  # noqa: F401

    engine = sa.create_engine(settings.SQLALCHEMY_DATABASE_URI)
    db = Session(bind=engine)
    try:
        goal_repo = GoalRepository(db)
        commission_config_repo = CommissionConfigRepository(db)
        pipeline_config_service = MetaConfigModuloService(MetaConfigModuloRepository(db))
        motor_parametros, pipeline = pipeline_config_service.get_pipeline_config()
        calc_engine = IQRGoalCalculationEngine()

        meses = _meses_cerrados(db, args.meses)
        logger.info("Backtest sobre %d meses cerrados.", len(meses))

        # Cumplimiento real (venta_real / meta) por motor, y costo de comisión agregado.
        cumplimiento: dict[str, list[float]] = {"v2": [], "v3": []}
        costo_comision: dict[str, float] = {"v2": 0.0, "v3": 0.0}
        divergencias: list[tuple[float, str, int, int, float, float]] = []  # (pct_div, vendedor, anio, mes, meta_v2, meta_v3)

        for anio, mes in meses:
            indice_estacional_empresa = goal_repo.get_indice_estacional_empresa()
            fecha_config = fecha_referencia_periodo(anio, mes)
            matriz_periodo = commission_config_repo.get_matriz_as_reglas(fecha_config)
            formula_componentes = resolver_componentes_formula(commission_config_repo)
            tramos_cumplimiento_periodo = resolver_tramos_cumplimiento(commission_config_repo, None, fecha_config)

            # Misma población que usaría `GoalMLService.generate_proposals` en producción
            # para este mes objetivo (auditoría 47 H-2, ventana de 12 meses) -- evaluar
            # motores sobre vendedores realmente dormidos (última venta años atrás, pero
            # con el flag `activo=TRUE` sin actualizar) produciría metas de ruido
            # estadístico (histórico casi vacío) sin ningún valor de calibración real.
            vendedores = [t.vendedor_origen for t in goal_repo.get_vendors_with_recent_sales(anio, mes, meses_ventana=12)]

            # ── Primera pasada: metas base (sin madurez/tipo/redondeo) para la mediana
            # del equipo, exactamente como hace `GoalMLService.generate_proposals` ──────
            metas_v3_base: dict[str, tuple[float, int | None]] = {}
            historicos: dict[str, list[RegistroMensual]] = {}
            for vendedor in vendedores:
                hist_rows = goal_repo.get_vendor_monthly_history(vendedor, meses=48)
                registros = [RegistroMensual(anio=h.anio, mes=h.mes, ventas=h.ventas, unidades=h.unidades) for h in hist_rows]
                registros_previos = [r for r in registros if (r.anio, r.mes) < (anio, mes)]
                if not registros_previos:
                    continue
                historicos[vendedor] = registros_previos
                try:
                    r_v3 = calc_engine.calcular(
                        vendedor, registros_previos, anio, mes,
                        indice_estacional_empresa=indice_estacional_empresa, parametros=motor_parametros,
                        aplicar_limpieza=pipeline.aplicar_limpieza, aplicar_estacionalidad=pipeline.aplicar_estacionalidad,
                        aplicar_tendencia=pipeline.aplicar_tendencia, aplicar_estabilidad=pipeline.aplicar_estabilidad,
                        aplicar_banda=pipeline.aplicar_banda,
                    )
                except Exception:
                    continue
                metas_v3_base[vendedor] = (r_v3.meta_ventas_total, r_v3.meses_historico_usados)

            mediana_equipo_v3 = statistics.median([m for m, _ in metas_v3_base.values()]) if metas_v3_base else 0.0

            for vendedor, registros_previos in historicos.items():
                venta_real = goal_repo.get_vendor_net_sales_period(vendedor, anio, mes)

                try:
                    r_v2 = calc_engine.calcular(
                        vendedor, registros_previos, anio, mes,
                        indice_estacional_empresa=indice_estacional_empresa, parametros=DEFAULT_PARAMETROS,
                    )
                except Exception:
                    continue
                meta_v2 = round(r_v2.meta_ventas_total, 2)

                meta_v3_base, meses_hist = metas_v3_base.get(vendedor, (0.0, None))
                madurez = ajustar_meta_por_madurez(
                    meta_propia=meta_v3_base, benchmark_equipo=mediana_equipo_v3, meses_antiguedad=meses_hist,
                    umbral_nuevo_meses=pipeline.umbral_nuevo_meses, umbral_maduro_meses=pipeline.umbral_maduro_meses,
                    peso_propio_intermedio=pipeline.peso_propio_intermedio,
                )
                meta_v3 = madurez.meta_ajustada
                config_vendedor = commission_config_repo.get_config_vendedor(vendedor, fecha_config)
                tipo = config_vendedor.tipo if config_vendedor else "externo"
                meta_v3 = aplicar_factor_tipo(meta_v3, tipo, pipeline.factores_tipo_vendedor)
                meta_v3 = round(redondear_meta(meta_v3, pipeline.redondeo_multiplo, pipeline.redondeo_modo), 2)

                if meta_v2 > 0:
                    cumplimiento["v2"].append(venta_real / meta_v2 * 100)
                if meta_v3 > 0:
                    cumplimiento["v3"].append(venta_real / meta_v3 * 100)

                if meta_v2 > 0 and meta_v3 > 0:
                    pct_div = abs(meta_v3 - meta_v2) / meta_v2 * 100
                    divergencias.append((pct_div, vendedor, anio, mes, meta_v2, meta_v3))

                for clave, monto_meta in (("v2", meta_v2), ("v3", meta_v3)):
                    if monto_meta <= 0:
                        continue
                    try:
                        resultado = calcular_comision_variable_completa(
                            goal_repo=goal_repo, commission_config_repo=commission_config_repo,
                            vendedor_origen=vendedor, anio=anio, mes=mes,
                            venta_real=venta_real, monto_meta=monto_meta, fecha_config=fecha_config,
                            formula_componentes=formula_componentes, matriz=matriz_periodo, rangos_credito=[],
                            tramos_cumplimiento=tramos_cumplimiento_periodo,
                        )
                        costo_comision[clave] += resultado.comision_final
                    except Exception as e:
                        logger.debug("Sin comisión calculable para %s %d-%02d (%s): %s", vendedor, anio, mes, clave, e)

            logger.info("Mes %d-%02d procesado (%d vendedores con historial suficiente).", anio, mes, len(historicos))

        divergencias.sort(key=lambda d: d[0], reverse=True)

        reporte = _construir_reporte(meses, cumplimiento, costo_comision, divergencias[:15])
        print(reporte)
        if args.md:
            os.makedirs(os.path.dirname(args.md) or ".", exist_ok=True)
            with open(args.md, "w", encoding="utf-8") as f:
                f.write(reporte)
            logger.info("Reporte escrito en %s", args.md)
    finally:
        db.close()
        engine.dispose()


def _construir_reporte(
    meses: list[tuple[int, int]], cumplimiento: dict[str, list[float]], costo_comision: dict[str, float],
    top_divergencias: list[tuple[float, str, int, int, float, float]],
) -> str:
    lineas = ["# Backtest motor-a-motor de metas (Fase 9.A)", ""]
    lineas.append(f"Meses evaluados: {len(meses)} ({meses[-1][0]}-{meses[-1][1]:02d} .. {meses[0][0]}-{meses[0][1]:02d})")
    lineas.append("")
    lineas.append("| Motor | n | Mediana % cumpl. | P10 | P25 | P75 | P90 | % >=100% | % <90% | % >125% | Costo comisión agregado |")
    lineas.append("|---|---|---|---|---|---|---|---|---|---|---|")
    for clave, nombre in (("v2", "v2 (estadístico puro)"), ("v3", "v3 (pipeline modular vigente)")):
        valores = cumplimiento[clave]
        p = _percentiles(valores)
        n = len(valores)
        pct_ge_100 = (sum(1 for v in valores if v >= 100) / n * 100) if n else 0.0
        pct_lt_90 = (sum(1 for v in valores if v < 90) / n * 100) if n else 0.0
        pct_gt_125 = (sum(1 for v in valores if v > 125) / n * 100) if n else 0.0
        lineas.append(
            f"| {nombre} | {n} | {p['mediana']:.1f}% | {p['p10']:.1f}% | {p['p25']:.1f}% | {p['p75']:.1f}% | "
            f"{p['p90']:.1f}% | {pct_ge_100:.1f}% | {pct_lt_90:.1f}% | {pct_gt_125:.1f}% | ${costo_comision[clave]:,.2f} |"
        )
    lineas.append("")
    lineas.append("## Casos de mayor divergencia entre motores (top 15, vendedor-mes)")
    lineas.append("")
    lineas.append("| Vendedor | Período | Meta v2 | Meta v3 | Divergencia % |")
    lineas.append("|---|---|---|---|---|")
    for pct_div, vendedor, anio, mes, meta_v2, meta_v3 in top_divergencias:
        lineas.append(f"| {vendedor} | {anio}-{mes:02d} | ${meta_v2:,.2f} | ${meta_v3:,.2f} | {pct_div:.1f}% |")
    return "\n".join(lineas) + "\n"


if __name__ == "__main__":
    main()
