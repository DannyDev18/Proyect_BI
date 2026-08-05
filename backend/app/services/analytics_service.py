# backend/app/services/analytics_service.py
"""KPIs de Gerencia/Bodega/Ventas. Sin ML, sin metas (ver `prediction_service.py` y
`goals_service.py`). El SQL vive en `AnalyticsRepository`; este service solo aplica
reglas de negocio de formateo (redondeos, defaults) y la comparación temporal
(`app/services/metricas/comparador.py`)."""
import datetime
from typing import Any

from app.core.config import settings
from app.repositories.analytics_repository import AnalyticsRepository
from app.services.metricas.comparador import (
    ModoComparacion,
    N_PERIODOS_DEFAULT,
    comparar,
    ventanas_de_referencia,
)


class AnalyticsService:
    def __init__(self, analytics_repo: AnalyticsRepository):
        self.repo = analytics_repo

    def get_management_kpis(
        self, sucursal: str | None = None, start_date: str | None = None,
        end_date: str | None = None, categoria: str | None = None, vendedor: str | None = None,
        almacen: str | None = None,
        modo_comparacion: ModoComparacion = ModoComparacion.PERIODO_ANTERIOR,
        n_periodos: int = N_PERIODOS_DEFAULT,
    ) -> dict[str, Any]:
        """Caso de Uso 2 (Gerencia): Índice de Salud Comercial.

        G-04 (docs/features/plan_madurez_bi_toma_decisiones.md): `modo_comparacion` permite
        contrastar contra el período anterior (default, comportamiento histórico), el mismo
        período del **año anterior** (el relevante en un negocio estacional, regla 11) o el
        promedio de los N períodos previos."""
        data = self.repo.get_management_kpis(sucursal, start_date, end_date, categoria, vendedor, almacen)
        # docs/auditoria/39_madurez_bi_toma_decisiones.md, H-02 (G-01 del plan de madurez BI):
        # antes aquí vivía `roi_estimado = round(data["margen"] * 1.15, 2)` -- un porcentaje
        # de margen multiplicado por una constante sin respaldo, publicado como "Proyección
        # ROI" con semáforo. Reemplazado por RN-BI2, calculado en SQL sobre el EDW:
        # (venta_neta - costo_mercaderia_vendida) / costo_mercaderia_vendida * 100.
        roi_real = round(data["roi_real"], 2) if data["roi_real"] is not None else None
        resultado = {
            # docs/auditoria/33_actualizacion_modulo_gerencia.md, H2: el repositorio ya
            # calculaba `total_sales` en SQL (venta neta - devoluciones), pero antes se
            # descartaba aquí y el frontend lo recalculaba sumando `ventas_por_sucursal`.
            "ingresos_totales": round(data["total_sales"], 2),
            "margen_utilidad_neta": round(data["margen"], 2),
            "ticket_promedio": round(data["ticket"], 2),
            "roi_real": roi_real,
            "costo_mercaderia": round(data["costo_mercaderia"], 2),
            "ventas_por_sucursal": data["branch_map"],
            "ventas_por_vendedor": data["vend_map"],
            "ingresos_totales_tendencia_pct": None,
            "margen_utilidad_neta_tendencia_pct": None,
            "ticket_promedio_tendencia_pct": None,
            "roi_real_tendencia_pct": None,
            # G-04: contexto de la comparación, para que la UI pueda decir CONTRA QUÉ compara
            # y por qué no hay base cuando las tendencias vienen en None.
            "comparacion": None,
        }

        # Comparativa temporal (G-04). Solo cuando el usuario fija un rango explícito: sin
        # fechas la vista es "todo el histórico" y no existe un período de referencia con el
        # que compararla sin cambiar el comportamiento por defecto ya existente de este KPI.
        if start_date and end_date:
            ventanas = ventanas_de_referencia(start_date, end_date, modo_comparacion, n_periodos)
            datos_ref = [
                self.repo.get_management_kpis(sucursal, v.desde, v.hasta, categoria, vendedor, almacen)
                for v in ventanas
            ]

            campos = {
                "ingresos_totales_tendencia_pct": ("total_sales", data["total_sales"]),
                "margen_utilidad_neta_tendencia_pct": ("margen", data["margen"]),
                "ticket_promedio_tendencia_pct": ("ticket", data["ticket"]),
                # H-02: la tendencia anterior comparaba `margen*1.15` contra `margen_prev*1.15`,
                # algebraicamente idéntica a la tendencia del margen -- un cuarto KPI que en
                # realidad repetía el segundo. Ahora compara el ROI real de ambos períodos.
                "roi_real_tendencia_pct": ("roi_real", roi_real),
            }
            motivos: list[str] = []
            for campo, (clave_repo, valor_actual) in campos.items():
                c = comparar(valor_actual, [d[clave_repo] for d in datos_ref], modo_comparacion, ventanas)
                resultado[campo] = c.variacion_pct
                if c.variacion_pct is None and c.motivo_sin_base:
                    motivos.append(f"{campo}: {c.motivo_sin_base}")

            resultado["comparacion"] = {
                "modo": modo_comparacion.value,
                # `ventanas` viene de la más reciente a la más antigua, así que el rango
                # cubierto va del inicio de la ÚLTIMA al fin de la PRIMERA.
                "desde_referencia": ventanas[-1].desde,
                "hasta_referencia": ventanas[0].hasta,
                "periodos_promediados": len(ventanas),
                "sin_base": motivos or None,
            }

        return resultado

    def get_revenue_by_category(
        self, sucursal: str | None = None, start_date: str | None = None,
        end_date: str | None = None, vendedor: str | None = None, almacen: str | None = None,
    ) -> list[dict[str, Any]]:
        return self.repo.get_revenue_by_category(sucursal, start_date, end_date, vendedor, almacen)

    def get_evolucion_mensual_ventas(
        self, vendedor: str | None = None, almacen: str | None = None, meses: int = 24,
    ) -> list[dict[str, Any]]:
        """Reemplaza al panel de predicción ML retirado (auditoría 49): Venta Neta real
        mes a mes, sin ningún modelo."""
        return self.repo.get_evolucion_mensual_ventas(vendedor=vendedor, almacen=almacen, meses=meses)

    def get_categories(self) -> list[str]:
        return self.repo.get_categories()

    def get_sucursales(self) -> list[str]:
        return self.repo.get_sucursales()

    def get_vendedores(self) -> list[str]:
        return self.repo.get_vendedores()

    def get_almacenes(self) -> list[str]:
        return self.repo.get_almacenes()

    def get_warehouse_kpis(self, almacenes_permitidos: list[str] | None = None) -> dict[str, Any]:
        """Caso de Uso 3 (Bodega): Alertas de Desabastecimiento -- implementación real
        contra `edw.fact_inventario_snapshot` (antes esta función devolvía datos
        hardcodeados). `almacenes_permitidos` (docs/auditoria/42_...): RLS real del rol
        `bodega` -- reemplaza el filtro por `sucursal`, ver docstring de
        `AnalyticsRepository.get_inventory_alerts`."""
        return self.repo.get_inventory_alerts(almacenes_permitidos)

    def get_sales_kpis(
        self, sucursal: str | None = None, anio: int | None = None, mes: int | None = None,
        vendedor: str | None = None,
    ) -> dict[str, Any]:
        """Caso de Uso 4 (Ventas): Cumplimiento de metas de vendedor -- implementación
        real combinando `edw.fact_ventas_detalle` y `public.metas_comerciales_operativas`.
        Por defecto el período vigente (antes esta función devolvía datos hardcodeados);
        `anio`/`mes` explícitos permiten consultar un período anterior (docs/auditoria/
        34_actualizacion_modulo_ventas.md, H-V3). `vendedor` (auditoría A-0.3, decisión
        B-3): RLS real del rol `ventas`, reemplaza `sucursal` -- ver docstring de
        `AnalyticsRepository.get_sales_performance`.

        El "período vigente" sin `anio`/`mes` explícitos es el mes calendario ACTUAL
        (`datetime.now()`), no `AnalyticsRepository.get_latest_period()` (el último mes
        con ventas ya cargadas en el EDW) -- hallazgo real: la Consola de Metas aprueba
        metas para el mes de planificación (mes actual/siguiente, ver
        `GoalsService.get_periods`), pero si el ETL todavía no cargó las ventas del mes
        en curso, `get_latest_period()` devuelve el mes anterior -- el vendedor veía la
        meta de un período distinto al que gerencia acababa de aprobarle ("solo como
        referencia", nunca el monto real de su mes vigente)."""
        if anio is None or mes is None:
            hoy = datetime.datetime.now()
            anio, mes = hoy.year, hoy.month
        return self.repo.get_sales_performance(anio, mes, sucursal, vendedor)

    def get_evolucion_mensual_vendedor(self, codven: str, meses: int = 6) -> list[dict[str, Any]]:
        """Auditoría 43, Fase 5 (dashboard "Mi Negocio" del vendedor)."""
        return self.repo.get_evolucion_mensual_vendedor(codven, meses)

    def get_top_productos_vendedor(self, codven: str, meses: int = 3, limit: int = 5) -> list[dict[str, Any]]:
        """Auditoría 43, Fase 5."""
        return self.repo.get_top_productos_vendedor(codven, meses, limit)

    def get_dashboard_report(
        self, kpis: dict[str, Any], revenue_by_category: list[dict[str, Any]],
        cumplimiento: dict[str, Any], filtros_aplicados: dict[str, Any],
    ) -> dict[str, Any]:
        """Fase 2 Gerencia (docs/features/plan_correcciones_pendientes.md §3): ensambla
        el contrato tipado de reporte (mismo `ReporteBodegaResponse`/`reporte_a_excel`
        que Bodega, "no duplicar exportadores") a partir de datos YA calculados por los
        endpoints existentes (`get_management_kpis`, `get_revenue_by_category`,
        `CommissionService.get_cumplimiento_meta_periodo`) -- sin SQL propio ni consulta
        nueva al EDW."""
        moneda = lambda v: f"${v:,.2f}"  # noqa: E731 -- mismo formato que warehouse_service._moneda
        resumen_ejecutivo = [
            {"etiqueta": "Ingresos Totales (ventas-devoluciones)", "valor": moneda(kpis["ingresos_totales"]), "tono": "neutral"},
            {"etiqueta": "Margen de Utilidad", "valor": f"{kpis['margen_utilidad_neta']:.1f}%", "tono": "positivo" if kpis["margen_utilidad_neta"] >= 0 else "negativo"},
            {"etiqueta": "Factura Promedio", "valor": moneda(kpis["ticket_promedio"]), "tono": "neutral"},
            # H-02: antes "Proyección ROI" con un umbral `>= 10` literal. Ahora el ROI real
            # (RN-BI2) contra `ANALYTICS_ROI_UMBRAL_SANO`, y "sin base de cálculo" cuando
            # no hay costo de mercadería con el que comparar (en vez de fingir un 0%).
            {
                "etiqueta": "ROI (retorno sobre costo de mercadería)",
                "valor": f"{kpis['roi_real']:.1f}%" if kpis.get("roi_real") is not None else "sin base de cálculo",
                "tono": "neutral" if kpis.get("roi_real") is None
                        else "positivo" if kpis["roi_real"] >= settings.ANALYTICS_ROI_UMBRAL_SANO else "negativo",
            },
            {
                "etiqueta": f"Cumplimiento vs Meta ({cumplimiento['mes']:02d}/{cumplimiento['anio']})",
                "valor": f"{cumplimiento['pct_cumplimiento']:.1f}%",
                "tono": "positivo" if cumplimiento["pct_cumplimiento"] >= 100 else "negativo" if cumplimiento["pct_cumplimiento"] < 70 else "neutral",
            },
        ]
        interpretacion = (
            f"Ingresos de {moneda(kpis['ingresos_totales'])} con {kpis['margen_utilidad_neta']:.1f}% de margen; "
            f"el cumplimiento de metas del mes en curso es {cumplimiento['pct_cumplimiento']:.1f}% "
            f"({cumplimiento['vendedores_con_meta_aprobada']} vendedores con meta aprobada)."
        )
        secciones = [
            {
                "titulo": "Ventas por Sucursal",
                "descripcion": "Venta neta (ventas - devoluciones) por sucursal, según los filtros aplicados.",
                "columnas": [
                    {"key": "sucursal", "etiqueta": "Sucursal", "tipo": "texto"},
                    {"key": "ventas", "etiqueta": "Ventas Netas", "tipo": "moneda"},
                ],
                "filas": [{"sucursal": k, "ventas": v} for k, v in kpis["ventas_por_sucursal"].items()],
            },
            {
                "titulo": "Ingresos por Categoría",
                "descripcion": "Ingresos agregados por categoría de producto, según los filtros aplicados.",
                "columnas": [
                    {"key": "cat", "etiqueta": "Categoría", "tipo": "texto"},
                    {"key": "v", "etiqueta": "Ingresos", "tipo": "moneda"},
                ],
                "filas": revenue_by_category,
            },
        ]
        return {
            "tipo": "dashboard-gerencial",
            "titulo": "Reporte Ejecutivo — Visión Gerencial",
            "generado_en": datetime.datetime.now().isoformat(timespec="seconds"),
            "filtros_aplicados": {k: v for k, v in filtros_aplicados.items() if v},
            "resumen_ejecutivo": resumen_ejecutivo,
            "interpretacion": interpretacion,
            "secciones": secciones,
        }
