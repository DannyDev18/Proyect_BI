# backend/app/services/analytics_service.py
"""KPIs de Gerencia/Bodega/Ventas. Sin ML, sin metas (ver `prediction_service.py` y
`goals_service.py`). El SQL vive en `AnalyticsRepository`; este service solo aplica
reglas de negocio de formateo (redondeos, cálculo de ROI simulado, defaults)."""
import datetime
from typing import Any

from app.repositories.analytics_repository import AnalyticsRepository


class AnalyticsService:
    def __init__(self, analytics_repo: AnalyticsRepository):
        self.repo = analytics_repo

    @staticmethod
    def _tendencia_pct(actual: float, previo: float) -> float | None:
        """Mismo patrón que `WarehouseService._tendencia_pct` (Bodega) -- % de cambio
        vs. el período previo de igual longitud, o `None` si el previo es 0/negativo
        (no hay base de comparación significativa)."""
        if previo <= 0:
            return None
        return round((actual - previo) / previo * 100, 1)

    @staticmethod
    def _periodo_anterior(start_date: str, end_date: str) -> tuple[str, str]:
        """Ventana previa de igual longitud, inmediatamente anterior a
        `[start_date, end_date]` -- mismo patrón que `WarehouseService._defaults_rango`."""
        desde = datetime.date.fromisoformat(start_date)
        hasta = datetime.date.fromisoformat(end_date)
        delta = hasta - desde
        hasta_prev = desde - datetime.timedelta(days=1)
        desde_prev = hasta_prev - delta
        return desde_prev.isoformat(), hasta_prev.isoformat()

    def get_management_kpis(
        self, sucursal: str | None = None, start_date: str | None = None,
        end_date: str | None = None, categoria: str | None = None, vendedor: str | None = None,
        almacen: str | None = None,
    ) -> dict[str, Any]:
        """Caso de Uso 2 (Gerencia): Índice de Salud Comercial."""
        data = self.repo.get_management_kpis(sucursal, start_date, end_date, categoria, vendedor, almacen)
        roi_estimado = round(data["margen"] * 1.15, 2)  # Simulación adaptada de ROI de campaña
        resultado = {
            # docs/auditoria/33_actualizacion_modulo_gerencia.md, H2: el repositorio ya
            # calculaba `total_sales` en SQL (venta neta - devoluciones), pero antes se
            # descartaba aquí y el frontend lo recalculaba sumando `ventas_por_sucursal`.
            "ingresos_totales": round(data["total_sales"], 2),
            "margen_utilidad_neta": round(data["margen"], 2),
            "ticket_promedio": round(data["ticket"], 2),
            "roi_estimado": roi_estimado,
            "ventas_por_sucursal": data["branch_map"],
            "ventas_por_vendedor": data["vend_map"],
            "ingresos_totales_tendencia_pct": None,
            "margen_utilidad_neta_tendencia_pct": None,
            "ticket_promedio_tendencia_pct": None,
            "roi_estimado_tendencia_pct": None,
        }

        # Fase 2 Gerencia (docs/features/plan_correcciones_pendientes.md §3): comparativa
        # vs. período anterior, mismo patrón `tendencia_pct` de Bodega. Solo cuando el
        # usuario fija un rango explícito -- sin fechas, la vista es "todo el histórico"
        # y no existe un "período anterior" con el que compararla sin cambiar el
        # comportamiento por defecto ya existente de este KPI.
        if start_date and end_date:
            desde_prev, hasta_prev = self._periodo_anterior(start_date, end_date)
            data_prev = self.repo.get_management_kpis(sucursal, desde_prev, hasta_prev, categoria, vendedor, almacen)
            roi_prev = data_prev["margen"] * 1.15
            resultado["ingresos_totales_tendencia_pct"] = self._tendencia_pct(data["total_sales"], data_prev["total_sales"])
            resultado["margen_utilidad_neta_tendencia_pct"] = self._tendencia_pct(data["margen"], data_prev["margen"])
            resultado["ticket_promedio_tendencia_pct"] = self._tendencia_pct(data["ticket"], data_prev["ticket"])
            resultado["roi_estimado_tendencia_pct"] = self._tendencia_pct(roi_estimado, roi_prev)

        return resultado

    def get_revenue_by_category(
        self, sucursal: str | None = None, start_date: str | None = None,
        end_date: str | None = None, vendedor: str | None = None, almacen: str | None = None,
    ) -> list[dict[str, Any]]:
        return self.repo.get_revenue_by_category(sucursal, start_date, end_date, vendedor, almacen)

    def get_categories(self) -> list[str]:
        return self.repo.get_categories()

    def get_sucursales(self) -> list[str]:
        return self.repo.get_sucursales()

    def get_vendedores(self) -> list[str]:
        return self.repo.get_vendedores()

    def get_almacenes(self) -> list[str]:
        return self.repo.get_almacenes()

    def get_warehouse_kpis(self, sucursal: str | None = None) -> dict[str, Any]:
        """Caso de Uso 3 (Bodega): Alertas de Desabastecimiento -- implementación real
        contra `edw.fact_inventario_snapshot` (antes esta función devolvía datos
        hardcodeados)."""
        return self.repo.get_inventory_alerts(sucursal)

    def get_sales_kpis(
        self, sucursal: str | None = None, anio: int | None = None, mes: int | None = None,
    ) -> dict[str, Any]:
        """Caso de Uso 4 (Ventas): Cumplimiento de metas de vendedor -- implementación
        real combinando `edw.fact_ventas_detalle` y `public.metas_comerciales_operativas`.
        Por defecto el período vigente (antes esta función devolvía datos hardcodeados);
        `anio`/`mes` explícitos permiten consultar un período anterior (docs/auditoria/
        34_actualizacion_modulo_ventas.md, H-V3 -- antes el vendedor no podía ver meses
        cerrados, solo el período vigente)."""
        if anio is None or mes is None:
            anio, mes = self.repo.get_latest_period()
        return self.repo.get_sales_performance(anio, mes, sucursal)

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
            {"etiqueta": "Proyección ROI", "valor": f"{kpis['roi_estimado']:.1f}%", "tono": "positivo" if kpis["roi_estimado"] >= 10 else "negativo"},
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
