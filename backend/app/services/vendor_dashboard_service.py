# backend/app/services/vendor_dashboard_service.py
"""Dashboard "Mi Negocio" del vendedor (auditoría 43, Fase 5,
docs/auditoria/43_correcciones_sesion_ventas_y_datos.md): `DashboardVentas.tsx` era
efectivamente un formulario de búsqueda (H43-16) -- ningún widget real hasta que el
vendedor escribía un `cliente_id` exacto de memoria. Este servicio compone, en UNA sola
llamada, datos que YA existen en otros servicios/repositorios -- sin lógica de negocio
nueva de comisiones ni de cartera (invariante del plan: el dashboard lee, no reimplementa)
y sin ningún modelo ML nuevo. Cada widget del mockup del usuario que no tiene una fuente
real en el EDW se omite aquí -- no se rellena con datos simulados (ver la tabla de "no
implementable" del plan)."""
from typing import Any

from app.repositories.catalog_repository import CatalogRepository
from app.services.analytics_service import AnalyticsService
from app.services.cartera360_service import Cartera360Service
from app.services.commission_service import CommissionService
from app.services.gestion_service import GestionService

CODIGOS_RIESGO = {"riesgo_critico", "riesgo_medio"}


class VendorDashboardService:
    def __init__(
        self, analytics_service: AnalyticsService, commission_service: CommissionService,
        cartera360_service: Cartera360Service, gestion_service: GestionService,
        catalog_repo: CatalogRepository,
    ):
        self.analytics_service = analytics_service
        self.commission_service = commission_service
        self.cartera360_service = cartera360_service
        self.gestion_service = gestion_service
        self.catalog_repo = catalog_repo

    def _ranking_posicion(self, codven: str, anio: int, mes: int) -> dict[str, Any] | None:
        """Posición del vendedor en el ranking company-wide del período (regla 10,
        mismo `AnalyticsService.get_sales_kpis` que ya usa `ai-summary` de Gerencia, aquí
        llamado SIN `vendedor` para obtener el ranking completo -- pasar `vendedor` lo
        vacía a propósito, ver auditoría A-0.3/decisión B-3)."""
        vendedor_info = self.catalog_repo.get_vendedor_activo(codven)
        if not vendedor_info:
            return None
        performance = self.analytics_service.get_sales_kpis(anio=anio, mes=mes)
        ranking = performance["ranking_vendedores"]
        nombre = vendedor_info["nombre_vendedor"]
        posiciones = [r["nombre"] for r in ranking]
        if nombre not in posiciones:
            return None
        return {"posicion": posiciones.index(nombre) + 1, "total": len(ranking)}

    def get_mi_negocio(self, codven: str, usuario_id: int, anio: int, mes: int) -> dict[str, Any]:
        mi_comision = self.commission_service.get_my_commission(codven, anio, mes)
        ranking = self._ranking_posicion(codven, anio, mes)
        evolucion = self.analytics_service.get_evolucion_mensual_vendedor(codven)
        top_productos = self.analytics_service.get_top_productos_vendedor(codven)
        proximas_acciones = self.gestion_service.get_proximas_acciones(codven)
        efectividad = self.gestion_service.get_efectividad_comercial(usuario_id)

        # Ruta priorizada del día: reutiliza el two-stage ya calculado por "Mi Ruta
        # Inteligente" (churn_rf real, no un modelo nuevo) para dos widgets del mockup --
        # "clientes en riesgo" (clasificación riesgo_critico/riesgo_medio) y "pipeline"
        # (los mismos clientes priorizados, con `probabilidad_recompra` real). Etiquetado
        # explícitamente como probabilidad de RECOMPRA (100 - probabilidad de abandono),
        # nunca "probabilidad de cierre de venta" -- no hay CRM ni etapas de oportunidad
        # en el ERP (ver §Fase 5 del plan).
        ruta = self.cartera360_service.get_ruta_hoy(codven)
        clientes_en_riesgo = [
            c for c in ruta["clientes"] if c["clasificacion"]["codigo"] in CODIGOS_RIESGO
        ][:5]
        pipeline = ruta["clientes"][:5]
        # "Meta diaria" / "falta para hoy" (mockup): ya calculados por `get_ruta_hoy` para
        # sus propias tarjetas de header -- se reutilizan aquí en vez de repetir la
        # consulta (`objetivo_diario` es None si el vendedor no tiene meta generada).
        meta_diaria = {
            "objetivo_diario": ruta["tarjetas"]["objetivo_diario"],
            "venta_hoy": ruta["tarjetas"]["avance_dia"],
        }

        comparativo_mes_anterior = None
        if len(evolucion) >= 2:
            actual, anterior = evolucion[-1], evolucion[-2]
            if anterior["venta_real"] > 0:
                variacion_pct = round(
                    (actual["venta_real"] - anterior["venta_real"]) / anterior["venta_real"] * 100, 1
                )
                comparativo_mes_anterior = {
                    "venta_mes_actual": actual["venta_real"],
                    "venta_mes_anterior": anterior["venta_real"],
                    "variacion_pct": variacion_pct,
                }

        return {
            "vendedor_origen": codven,
            "anio": anio,
            "mes": mes,
            "cuota": {
                "meta_mensual": mi_comision.monto_meta,
                "venta_actual": mi_comision.venta_real,
                "pct_cumplimiento": mi_comision.pct_cumplimiento,
                "nivel": mi_comision.nivel,
            },
            "comision": {
                "comision_devengada": mi_comision.comision_devengada,
                "tasa_aplicada_pct": mi_comision.tasa_aplicada_pct,
                "bono_aplicado": mi_comision.bono_aplicado,
                "dias_restantes_mes": mi_comision.dias_restantes_mes,
                "comision_variable": mi_comision.comision_variable,
                "modo_comision": mi_comision.modo_comision,
            },
            "meta_diaria": meta_diaria,
            "ranking": ranking,
            "evolucion_mensual": evolucion,
            "comparativo_mes_anterior": comparativo_mes_anterior,
            "top_productos": top_productos,
            "clientes_en_riesgo": clientes_en_riesgo,
            "pipeline": pipeline,
            "proximas_acciones": proximas_acciones["acciones"],
            "efectividad_comercial": efectividad,
        }
