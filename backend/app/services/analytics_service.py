# backend/app/services/analytics_service.py
"""KPIs de Gerencia/Bodega/Ventas. Sin ML, sin metas (ver `prediction_service.py` y
`goals_service.py`). El SQL vive en `AnalyticsRepository`; este service solo aplica
reglas de negocio de formateo (redondeos, cálculo de ROI simulado, defaults)."""
from typing import Any

from app.repositories.analytics_repository import AnalyticsRepository


class AnalyticsService:
    def __init__(self, analytics_repo: AnalyticsRepository):
        self.repo = analytics_repo

    def get_management_kpis(
        self, sucursal: str | None = None, start_date: str | None = None,
        end_date: str | None = None, categoria: str | None = None, vendedor: str | None = None,
        almacen: str | None = None,
    ) -> dict[str, Any]:
        """Caso de Uso 2 (Gerencia): Índice de Salud Comercial."""
        data = self.repo.get_management_kpis(sucursal, start_date, end_date, categoria, vendedor, almacen)
        return {
            # docs/auditoria/33_actualizacion_modulo_gerencia.md, H2: el repositorio ya
            # calculaba `total_sales` en SQL (venta neta - devoluciones), pero antes se
            # descartaba aquí y el frontend lo recalculaba sumando `ventas_por_sucursal`.
            "ingresos_totales": round(data["total_sales"], 2),
            "margen_utilidad_neta": round(data["margen"], 2),
            "ticket_promedio": round(data["ticket"], 2),
            "roi_estimado": round(data["margen"] * 1.15, 2),  # Simulación adaptada de ROI de campaña
            "ventas_por_sucursal": data["branch_map"],
            "ventas_por_vendedor": data["vend_map"],
        }

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
