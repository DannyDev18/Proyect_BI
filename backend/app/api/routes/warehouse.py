# backend/app/api/routes/warehouse.py
"""Bodega: alertas de inventario y predicción de demanda logística."""
from fastapi import APIRouter, Depends

from app.api.dependencies import AnalyticsServiceDep, PredictionServiceDep, resolve_sucursal_filter
from app.core.deps import PermissionChecker
from app.schemas.analytics import BPKPIBodega, PrediccionDemandaResponse

router = APIRouter()

bodeguero_checker = PermissionChecker(allowed_roles=["administrador", "gerencia", "bodega"])
sucursal_bodega = resolve_sucursal_filter(allow_override=False)


@router.get("/kpis-inventory", response_model=BPKPIBodega, dependencies=[Depends(bodeguero_checker)])
def get_warehouse_kpis(
    analytics_service: AnalyticsServiceDep,
    sucursal_filtro: str | None = Depends(sucursal_bodega),
) -> BPKPIBodega:
    """Ítems en sobrestock, en riesgo de desabastecimiento, y sugerencias de
    transferencias inter-sucursales."""
    kpis = analytics_service.get_warehouse_kpis(sucursal=sucursal_filtro)
    return BPKPIBodega(**kpis)


@router.get("/demand-forecasting", response_model=PrediccionDemandaResponse, dependencies=[Depends(bodeguero_checker)])
def get_demand_prediction(
    producto_cod: str,
    prediction_service: PredictionServiceDep,
) -> PrediccionDemandaResponse:
    """Predicción de demanda por SKU para la próxima semana."""
    demanda = prediction_service.get_demand_forecast(producto_cod)
    return PrediccionDemandaResponse(producto_cod=producto_cod, demanda_proxima_semana=demanda)
