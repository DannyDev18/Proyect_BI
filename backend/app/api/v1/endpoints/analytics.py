# backend/app/api/v1/endpoints/analytics.py
from fastapi import APIRouter, Depends, HTTPException
from typing import Optional, List, Dict, Any
from sqlalchemy.orm import Session

from app.core.deps import SessionDep, PermissionChecker, CurrentUserDep
from app.core.audit import audit_log
from app.schemas.analytics import (
    GPKPIGerencia, BPKPIBodega, VPKPIVentas,
    PrediccionVentasResponse, PrediccionDemandaResponse,
    SegmentacionClienteResponse, ChurnResponse, AnomaliaResponse,
    RecomendacionResponse
)
from app.services.analytics_service import AnalyticsService
from app.services import prediction_service
from app.models.user import User

router = APIRouter()

# -----------------
# GERENCIA (Ingresos de Negocio, Pronósticos de Ventas y Salud Comercial)
# -----------------
gerente_checker = PermissionChecker(allowed_roles=["administrador", "gerencia"])

@router.get("/gerencia/kpis", response_model=GPKPIGerencia, dependencies=[Depends(audit_log(operacion="READ", tabla_afectada="all", modulo="kpis_gerencia"))])
def get_management_kpis(
    db: SessionDep,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    categoria: Optional[str] = None,
    sucursal: Optional[str] = None,
    vendedor: Optional[str] = None,
    current_user: User = Depends(gerente_checker)
) -> GPKPIGerencia:
    """
    Devuelve los KPIs clave de Gerencia (Margen de Utilidad, Ticket Promedio, Ventas consolidadas).
    Aplica seguridad a nivel de fila (Row level security) si el usuario es un gerente zonal.
    """
    service = AnalyticsService(db)
    
    # Si es admin o gerencia, puede usar el filtro que envia el UI. Si es un rol restringido, forzamos su propia sucursal.
    sucursal_filtro = sucursal if current_user.role.nombre in ["administrador", "gerencia"] else current_user.sucursal
    
    kpis = service.get_management_kpis(
        sucursal=sucursal_filtro,
        start_date=start_date, 
        end_date=end_date, 
        categoria=categoria,
        vendedor=vendedor
    )
    return GPKPIGerencia(**kpis)

@router.get("/gerencia/revenue-by-category")
def get_revenue_by_category(
    db: SessionDep,
    start_date: str = None,
    end_date: str = None,
    sucursal: str = None,
    vendedor: str = None,
    current_user: User = Depends(gerente_checker)
):
    """
    Agrupa los ingresos segmentados por clase/categoria de productos 
    (Sirve al gráfico de Barras).
    """
    service = AnalyticsService(db)
    sucursal_filtro = sucursal if current_user.role.nombre in ["administrador", "gerencia"] else current_user.sucursal
    return service.get_revenue_by_category(
        sucursal=sucursal_filtro,
        start_date=start_date,
        end_date=end_date,
        vendedor=vendedor
    )

@router.get("/gerencia/categorias")
def get_categories(
    db: SessionDep,
    current_user: User = Depends(gerente_checker)
):
    """
    Endpoint para obtener la lista de categorias dinamicamente del DW.
    """
    service = AnalyticsService(db)
    return service.get_categories()

@router.get("/gerencia/sucursales")
def get_sucursales(
    db: SessionDep,
    current_user: User = Depends(gerente_checker)
):
    """
    Endpoint para obtener la lista de sucursales dinamicamente.
    """
    service = AnalyticsService(db)
    return service.get_sucursales()

@router.get("/gerencia/vendedores")
def get_vendedores(
    db: SessionDep,
    current_user: User = Depends(gerente_checker)
):
    """
    Endpoint para obtener la lista de vendedores dinamicamente.
    """
    service = AnalyticsService(db)
    return service.get_vendedores()

@router.get("/gerencia/sales-prediction", response_model=PrediccionVentasResponse)
def get_sales_prediction(
    db: SessionDep,
    current_user: User = Depends(gerente_checker)
) -> PrediccionVentasResponse:
    """
    Ejecuta el Random Forest Regressor de MLOps para predecir ventas semanales.
    """
    sucursal_filtro = None if current_user.role.nombre in ["administrador", "gerencia"] else current_user.sucursal
    preds = prediction_service.get_sales_forecast_weekly(db, sucursal=sucursal_filtro)
    return PrediccionVentasResponse(
        horizonte="diario_semanal",
        dias_proyectados=preds.get("dias_proyectados", 7),
        historial_y_prediccion=preds.get("historial_y_prediccion", []),
        metricas=preds.get("metricas", {}),
        insights=preds.get("insights", [])
    )


# -----------------
# BODEGA y LOGISTICA (Alertas de Reposición e Inventarios)
# -----------------
bodeguero_checker = PermissionChecker(allowed_roles=["administrador", "gerencia", "bodega"])

@router.get("/bodega/kpis-inventory", response_model=BPKPIBodega)
def get_warehouse_kpis(
    db: SessionDep,
    current_user: User = Depends(bodeguero_checker)
) -> BPKPIBodega:
    """
    Devuelve el número de ítems en sobrestock, en riesgo de desabastecimiento, 
    y sugerencias inteligentes de transferencias inter-sucursales.
    """
    service = AnalyticsService(db)
    sucursal_filtro = None if current_user.role.nombre in ["administrador", "gerencia"] else current_user.sucursal
    kpis = service.get_warehouse_kpis(sucursal=sucursal_filtro)
    return BPKPIBodega(**kpis)

@router.get("/bodega/demand-forecasting", response_model=PrediccionDemandaResponse)
def get_demand_prediction(
    producto_cod: str,
    db: SessionDep,
    current_user: User = Depends(bodeguero_checker)
) -> PrediccionDemandaResponse:
    """
    Predicción de la demanda por SKU para la próxima semana.
    """
    demanda = prediction_service.get_demand_forecast(db, producto_cod)
    return PrediccionDemandaResponse(
        producto_cod=producto_cod,
        demanda_proxima_semana=demanda
    )


# -----------------
# VENTAS (Segmentación de Clientes, Riesgo de Churn, y Venta Cruzada)
# -----------------
vendedor_checker = PermissionChecker(allowed_roles=["administrador", "gerencia", "ventas"])

@router.get("/ventas/goals", response_model=VPKPIVentas)
def get_sales_goals(
    db: SessionDep,
    current_user: User = Depends(vendedor_checker)
) -> VPKPIVentas:
    """
    KPIs de Ventas: Objetivos comerciales, ranking y proyecciones.
    """
    service = AnalyticsService(db)
    sucursal_filtro = None if current_user.role.nombre in ["administrador", "gerencia"] else current_user.sucursal
    kpis = service.get_sales_kpis(sucursal=sucursal_filtro)
    return VPKPIVentas(**kpis)

@router.get("/ventas/churn-risk", response_model=ChurnResponse)
def get_churn_risk_by_client(
    cliente_id: str,
    db: SessionDep,
    current_user: User = Depends(vendedor_checker)
) -> ChurnResponse:
    """
    Ejecuta el clasificador entrenado para predecir si un cliente está en riesgo de abandono.
    """
    res = prediction_service.get_churn_risk(db, cliente_id)
    return ChurnResponse(
        cliente_id=cliente_id,
        probabilidad_abandono=res["probabilidad_abandono"],
        riesgo_alto=res["riesgo_alto"]
    )

@router.get("/ventas/recommendations", response_model=RecomendacionResponse)
def get_recommendations_for_client(
    cliente_id: str,
    db: SessionDep,
    current_user: User = Depends(vendedor_checker)
) -> RecomendacionResponse:
    """
    Ejecuta el motor de reglas de asociación para obtener los productos que 
    frecuentemente se venden junto con las últimas compras del cliente.
    """
    recs = prediction_service.get_product_recommendations(db, cliente_id)
    return RecomendacionResponse(
        cliente_id=cliente_id,
        recomendaciones=recs
    )

@router.get("/ventas/clientes/{cliente_cod}/segmento", response_model=SegmentacionClienteResponse)
def get_customer_segmentation(
    cliente_cod: str,
    db: SessionDep,
    current_user: User = Depends(vendedor_checker)
) -> SegmentacionClienteResponse:
    """
    Calcula las variables RFM de un cliente al vuelo y evalúa el modelo K-Means 
    para clasificarlo en un segmento comercial legible.
    """
    res = prediction_service.get_customer_segment(db, cliente_cod)
    return SegmentacionClienteResponse(
        cliente_id=cliente_cod,
        segmento=res["segmento"],
        nombre_segmento=res["nombre_segmento"]
    )

# -----------------
# ADMINISTRADOR (Detección de Fraudes y Anomalías Operativas)
# -----------------
admin_only = PermissionChecker(allowed_roles=["administrador"])

@router.get("/admin/anomalies", response_model=AnomaliaResponse, dependencies=[Depends(audit_log(operacion="PREDICT", tabla_afectada="fact_ventas_detalle", modulo="detect_fraude"))])
def detect_transactional_anomaly(
    transaccion_id: str,
    db: SessionDep,
    current_user: User = Depends(admin_only)
) -> AnomaliaResponse:
    """
    Ejecuta el modelo Isolation Forest sobre una transacción a calificar
    para verificar si constituye una anomalía operativa.
    """
    res = prediction_service.get_anomaly_status(db, transaccion_id)
    return AnomaliaResponse(
        transaccion_id=transaccion_id,
        score=res["score"],
        es_anomalia=res["es_anomalia"]
    )
