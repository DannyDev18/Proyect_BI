# backend/app/api/routes/sales.py
"""Ventas: cumplimiento de metas, riesgo de churn, recomendaciones (cross-selling) y
segmentación de clientes."""
from fastapi import APIRouter, Depends

from app.api.dependencies import AnalyticsServiceDep, PredictionServiceDep, resolve_sucursal_filter
from app.core.deps import PermissionChecker
from app.schemas.analytics import (
    ChurnResponse, RecomendacionProducto, RecomendacionResponse,
    SegmentacionClienteResponse, VPKPIVentas,
)

router = APIRouter()

vendedor_checker = PermissionChecker(allowed_roles=["administrador", "gerencia", "ventas"])
sucursal_ventas = resolve_sucursal_filter(allow_override=False)


@router.get("/goals", response_model=VPKPIVentas, dependencies=[Depends(vendedor_checker)])
def get_sales_goals(
    analytics_service: AnalyticsServiceDep,
    sucursal_filtro: str | None = Depends(sucursal_ventas),
) -> VPKPIVentas:
    """KPIs de ventas: metas, ranking y proyecciones del período vigente."""
    kpis = analytics_service.get_sales_kpis(sucursal=sucursal_filtro)
    return VPKPIVentas(**kpis)


@router.get("/churn-risk", response_model=ChurnResponse, dependencies=[Depends(vendedor_checker)])
def get_churn_risk_by_client(cliente_id: str, prediction_service: PredictionServiceDep) -> ChurnResponse:
    """Riesgo de abandono de un cliente vía el clasificador entrenado."""
    res = prediction_service.get_churn_risk(cliente_id)
    return ChurnResponse(cliente_id=cliente_id, probabilidad_abandono=res["probabilidad_abandono"], riesgo_alto=res["riesgo_alto"])


@router.get("/recommendations", response_model=RecomendacionResponse, dependencies=[Depends(vendedor_checker)])
def get_recommendations_for_client(cliente_id: str, prediction_service: PredictionServiceDep) -> RecomendacionResponse:
    """Productos que frecuentemente se venden junto con las últimas compras del cliente."""
    res = prediction_service.get_product_recommendations(cliente_id)
    return RecomendacionResponse(
        cliente_id=cliente_id,
        recomendaciones=[RecomendacionProducto(**r) for r in res["recomendaciones"]],
    )


@router.get("/clientes/{cliente_cod}/segmento", response_model=SegmentacionClienteResponse, dependencies=[Depends(vendedor_checker)])
def get_customer_segmentation(cliente_cod: str, prediction_service: PredictionServiceDep) -> SegmentacionClienteResponse:
    """Segmento comercial (RFM + K-Means) de un cliente, calculado al vuelo."""
    res = prediction_service.get_customer_segment(cliente_cod)
    return SegmentacionClienteResponse(cliente_id=cliente_cod, segmento=res["segmento"], nombre_segmento=res["nombre_segmento"])
