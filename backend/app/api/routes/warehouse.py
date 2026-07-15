# backend/app/api/routes/warehouse.py
"""Bodega: dashboard de inventario y abastecimiento (docs/features/modulo_bodega.md,
auditoría 23). Los endpoints legados `/kpis-inventory` y `/demand-forecasting` se
conservan sin cambios (H23-7); el módulo nuevo vive en las rutas siguientes.

Routers thin (regla CLAUDE.md): sin lógica de negocio, solo inyección de dependencias
y traducción de query params. RBAC: roles bodega/gerencia/administrador; el rol bodega
queda forzado a su sucursal vía `resolve_sucursal_filter(allow_override=False)`."""
from fastapi import APIRouter, Depends, Response

from app.api.dependencies import (
    AnalyticsServiceDep,
    PredictionServiceDep,
    WarehouseServiceDep,
    resolve_sucursal_filter,
)
from app.core.deps import PermissionChecker
from app.core.exceptions import NotFoundError
from app.schemas.analytics import BPKPIBodega, PrediccionDemandaResponse
from app.schemas.pagination import Page, PaginationParams, pagination_params
from app.schemas.warehouse import (
    CategoriaSalidas,
    FiltrosBodegaResponse,
    InventarioMatrizResponse,
    KpisBodegaResponse,
    NecesidadCompraResponse,
    PrediccionComprasMesResponse,
    ProductoCompra,
    ProductoMatrizAlmacen,
    ProductoStockReorden,
    ProductoTopSalidas,
    ReporteBodegaResponse,
    RotacionMatrizResponse,
    SalidasForecastResponse,
    TransferenciaSugerida,
    TransferenciasResponse,
)
from app.services.warehouse_export import reporte_a_excel

router = APIRouter()

bodeguero_checker = PermissionChecker(allowed_roles=["administrador", "gerencia", "bodega"])
sucursal_bodega = resolve_sucursal_filter(allow_override=False)


# ── Endpoints legados (pre-módulo, consumidores existentes) ───────────────────
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


# ── §1.1 Filtros globales ─────────────────────────────────────────────────────
@router.get("/filtros", response_model=FiltrosBodegaResponse, dependencies=[Depends(bodeguero_checker)])
def get_filtros(
    warehouse_service: WarehouseServiceDep,
    analytics_service: AnalyticsServiceDep,
) -> FiltrosBodegaResponse:
    """Catálogos para los filtros globales del dashboard de bodega."""
    data = warehouse_service.get_filtros({
        "almacenes": analytics_service.get_almacenes(),
        "categorias": analytics_service.get_categories(),
        "sucursales": analytics_service.get_sucursales(),
    })
    return FiltrosBodegaResponse(**data)


# ── §1.2 KPIs ─────────────────────────────────────────────────────────────────
@router.get("/kpis", response_model=KpisBodegaResponse, dependencies=[Depends(bodeguero_checker)])
def get_kpis_bodega(
    warehouse_service: WarehouseServiceDep,
    sucursal_filtro: str | None = Depends(sucursal_bodega),
    almacen: str | None = None,
    categoria: str | None = None,
    proveedor: str | None = None,
    tipo_movimiento: str | None = None,
    fecha_desde: str | None = None,
    fecha_hasta: str | None = None,
) -> KpisBodegaResponse:
    """Los 6 KPIs del dashboard (§1.2), afectados por los filtros globales."""
    data = warehouse_service.get_kpis(
        sucursal=sucursal_filtro, almacen=almacen, categoria=categoria,
        proveedor=proveedor, tipo_movimiento=tipo_movimiento,
        fecha_desde=fecha_desde, fecha_hasta=fecha_hasta,
    )
    return KpisBodegaResponse(**data)


# ── §1.3 Gráficos ─────────────────────────────────────────────────────────────
@router.get("/salidas-forecast", response_model=SalidasForecastResponse, dependencies=[Depends(bodeguero_checker)])
def get_salidas_forecast(
    warehouse_service: WarehouseServiceDep,
    sucursal_filtro: str | None = Depends(sucursal_bodega),
    producto_cod: str | None = None,
    almacen: str | None = None,
    categoria: str | None = None,
    proveedor: str | None = None,
    fecha_desde: str | None = None,
    fecha_hasta: str | None = None,
    dias_horizonte: int = 30,
) -> SalidasForecastResponse:
    """G1: histórico de salidas + predicción (`demand_rf` si hay producto; estadística
    declarada para agregados top-10)."""
    data = warehouse_service.get_salidas_forecast(
        producto_cod=producto_cod, dias_horizonte=dias_horizonte,
        sucursal=sucursal_filtro, almacen=almacen, categoria=categoria,
        proveedor=proveedor, fecha_desde=fecha_desde, fecha_hasta=fecha_hasta,
    )
    return SalidasForecastResponse(**data)


@router.get("/prediccion-compras-mes", response_model=PrediccionComprasMesResponse, dependencies=[Depends(bodeguero_checker)])
def get_prediccion_compras_mes(
    warehouse_service: WarehouseServiceDep,
    sucursal_filtro: str | None = Depends(sucursal_bodega),
    categoria: str | None = None,
    producto_cod: str | None = None,
    almacen: str | None = None,
    proveedor: str | None = None,
) -> PrediccionComprasMesResponse:
    """Predicción de compras del mes calendario siguiente (RN-B7, docs/auditoria/24),
    enlazada al filtro de categoría; con `producto_cod` responde el drill-down
    individual de uno de los top artículos devueltos por `categoria`."""
    data = warehouse_service.get_prediccion_compras_mes(
        categoria=categoria, producto_cod=producto_cod,
        sucursal=sucursal_filtro, almacen=almacen, proveedor=proveedor,
    )
    return PrediccionComprasMesResponse(**data)


@router.get("/rotacion-matriz", response_model=RotacionMatrizResponse, dependencies=[Depends(bodeguero_checker)])
def get_rotacion_matriz(
    warehouse_service: WarehouseServiceDep,
    sucursal_filtro: str | None = Depends(sucursal_bodega),
    almacen: str | None = None,
    categoria: str | None = None,
    proveedor: str | None = None,
    tipo_movimiento: str | None = None,
    fecha_desde: str | None = None,
    fecha_hasta: str | None = None,
) -> RotacionMatrizResponse:
    """G2: matriz rotación × margen por producto (cuadrantes de prioridad)."""
    data = warehouse_service.get_rotacion_matriz(
        sucursal=sucursal_filtro, almacen=almacen, categoria=categoria,
        proveedor=proveedor, tipo_movimiento=tipo_movimiento,
        fecha_desde=fecha_desde, fecha_hasta=fecha_hasta,
    )
    return RotacionMatrizResponse(**data)


@router.get("/top-productos", response_model=list[ProductoTopSalidas], dependencies=[Depends(bodeguero_checker)])
def get_top_productos(
    warehouse_service: WarehouseServiceDep,
    sucursal_filtro: str | None = Depends(sucursal_bodega),
    almacen: str | None = None,
    categoria: str | None = None,
    proveedor: str | None = None,
    tipo_movimiento: str | None = None,
    fecha_desde: str | None = None,
    fecha_hasta: str | None = None,
    limit: int = 20,
) -> list[ProductoTopSalidas]:
    """G3: top N productos con mayor salida, con stock, días y tendencia."""
    data = warehouse_service.get_top_productos(
        sucursal=sucursal_filtro, almacen=almacen, categoria=categoria,
        proveedor=proveedor, tipo_movimiento=tipo_movimiento,
        fecha_desde=fecha_desde, fecha_hasta=fecha_hasta, limit=min(limit, 100),
    )
    return [ProductoTopSalidas(**d) for d in data]


@router.get("/salidas-categoria", response_model=list[CategoriaSalidas], dependencies=[Depends(bodeguero_checker)])
def get_salidas_categoria(
    warehouse_service: WarehouseServiceDep,
    sucursal_filtro: str | None = Depends(sucursal_bodega),
    almacen: str | None = None,
    proveedor: str | None = None,
    tipo_movimiento: str | None = None,
    fecha_desde: str | None = None,
    fecha_hasta: str | None = None,
) -> list[CategoriaSalidas]:
    """G4: distribución de salidas por categoría con comparativa vs período anterior."""
    data = warehouse_service.get_salidas_categoria(
        sucursal=sucursal_filtro, almacen=almacen, proveedor=proveedor,
        tipo_movimiento=tipo_movimiento, fecha_desde=fecha_desde, fecha_hasta=fecha_hasta,
    )
    return [CategoriaSalidas(**d) for d in data]


@router.get("/stock-reorden", response_model=Page[ProductoStockReorden], dependencies=[Depends(bodeguero_checker)])
def get_stock_reorden(
    warehouse_service: WarehouseServiceDep,
    sucursal_filtro: str | None = Depends(sucursal_bodega),
    pagination: PaginationParams = Depends(pagination_params),
    almacen: str | None = None,
    categoria: str | None = None,
    proveedor: str | None = None,
    tipo_movimiento: str | None = None,
    solo_criticos: bool = False,
) -> Page[ProductoStockReorden]:
    """G5: estado de stock vs punto de reorden (RN-B1/B2). Paginado (docs/auditoria/24)."""
    pagina = warehouse_service.get_stock_reorden(
        pagination, sucursal=sucursal_filtro, almacen=almacen, categoria=categoria,
        proveedor=proveedor, tipo_movimiento=tipo_movimiento, solo_criticos=solo_criticos,
    )
    return Page(
        items=[ProductoStockReorden(**d) for d in pagina.items],
        total=pagina.total, page=pagina.page, page_size=pagina.page_size, total_pages=pagina.total_pages,
    )


@router.get("/necesidad-compra", response_model=NecesidadCompraResponse, dependencies=[Depends(bodeguero_checker)])
def get_necesidad_compra(
    warehouse_service: WarehouseServiceDep,
    sucursal_filtro: str | None = Depends(sucursal_bodega),
    pagination: PaginationParams = Depends(pagination_params),
    almacen: str | None = None,
    categoria: str | None = None,
    proveedor: str | None = None,
    tipo_movimiento: str | None = None,
    horizonte_dias: int | None = None,
) -> NecesidadCompraResponse:
    """G6 y §3.3 (RN-B4): proyección de necesidad de compra. `horizonte_dias=45`
    produce el plan de fin de mes. `recomendados` paginado (docs/auditoria/24)."""
    data = warehouse_service.get_necesidad_compra(
        pagination, sucursal=sucursal_filtro, almacen=almacen, categoria=categoria,
        proveedor=proveedor, tipo_movimiento=tipo_movimiento, horizonte_dias=horizonte_dias,
    )
    recomendados = data["recomendados"]
    return NecesidadCompraResponse(
        horizonte_dias=data["horizonte_dias"],
        recomendados=Page(
            items=[ProductoCompra(**d) for d in recomendados.items],
            total=recomendados.total, page=recomendados.page,
            page_size=recomendados.page_size, total_pages=recomendados.total_pages,
        ),
        no_comprar=[ProductoCompra(**d) for d in data["no_comprar"]],
        total_productos_a_comprar=data["total_productos_a_comprar"],
        valor_total_compra=data["valor_total_compra"],
        ahorro_por_no_comprar=data["ahorro_por_no_comprar"],
    )


# ── §3 Panel por almacén y transferencias ─────────────────────────────────────
@router.get("/inventario-matriz", response_model=InventarioMatrizResponse, dependencies=[Depends(bodeguero_checker)])
def get_inventario_matriz(
    warehouse_service: WarehouseServiceDep,
    sucursal_filtro: str | None = Depends(sucursal_bodega),
    pagination: PaginationParams = Depends(pagination_params),
    almacen: str | None = None,
    categoria: str | None = None,
    proveedor: str | None = None,
    tipo_movimiento: str | None = None,
    estado: str | None = None,
) -> InventarioMatrizResponse:
    """§3.1: stock por producto en cada almacén, con estado (Crítico/Cerca/Seguro/Exceso).
    Si se filtra por `almacen`, la matriz queda restringida a esa sola bodega (una
    columna) en vez de mostrar todas. Paginado (docs/auditoria/24)."""
    data = warehouse_service.get_inventario_matriz(
        pagination, sucursal=sucursal_filtro, almacen=almacen, categoria=categoria,
        proveedor=proveedor, tipo_movimiento=tipo_movimiento, estado=estado,
    )
    productos = data["productos"]
    return InventarioMatrizResponse(
        almacenes=data["almacenes"],
        productos=Page(
            items=[ProductoMatrizAlmacen(**d) for d in productos.items],
            total=productos.total, page=productos.page,
            page_size=productos.page_size, total_pages=productos.total_pages,
        ),
    )


@router.get("/transferencias-sugeridas", response_model=TransferenciasResponse, dependencies=[Depends(bodeguero_checker)])
def get_transferencias_sugeridas(
    warehouse_service: WarehouseServiceDep,
    sucursal_filtro: str | None = Depends(sucursal_bodega),
    pagination: PaginationParams = Depends(pagination_params),
    categoria: str | None = None,
    proveedor: str | None = None,
    tipo_movimiento: str | None = None,
) -> TransferenciasResponse:
    """§3.2 (RN-B3): transferencias inteligentes entre bodegas con prioridad y ahorro.
    Paginado (docs/auditoria/24)."""
    data = warehouse_service.get_transferencias_sugeridas(
        pagination, sucursal=sucursal_filtro, categoria=categoria, proveedor=proveedor, tipo_movimiento=tipo_movimiento,
    )
    sugerencias = data["sugerencias"]
    return TransferenciasResponse(
        sugerencias=Page(
            items=[TransferenciaSugerida(**d) for d in sugerencias.items],
            total=sugerencias.total, page=sugerencias.page,
            page_size=sugerencias.page_size, total_pages=sugerencias.total_pages,
        ),
        total_sugerencias=data["total_sugerencias"],
        ahorro_total_estimado=data["ahorro_total_estimado"],
    )

# NOTA: el endpoint `GET /notificaciones` de este router fue reemplazado por el router
# unificado `GET /notificaciones` (prefijo raíz, docs/auditoria/31_modulo_notificaciones.md,
# Fase 4): `NotificationService._generar_bodega` sigue reutilizando
# `WarehouseService.get_notificaciones` tal cual, solo que ahora expuesto por rol/usuario
# del JWT en vez de un endpoint propio de Bodega. Se removió tras validar paridad de
# contenido (misma fuente, mismo generador) y confirmar que el frontend no tenía otro
# consumidor del endpoint viejo.


# ── §2 (Fase 5) Reportes tipados ────────────────────────────────────────────
_TIPOS_REPORTE = {"justificacion", "transferencias", "analisis-mensual"}


def _generar_reporte(
    warehouse_service, tipo: str, sucursal: str | None, almacen: str | None,
    categoria: str | None, proveedor: str | None, tipo_movimiento: str | None,
    fecha_desde: str | None, fecha_hasta: str | None,
) -> dict:
    if tipo == "justificacion":
        return warehouse_service.get_reporte_justificacion(
            sucursal=sucursal, almacen=almacen, categoria=categoria, proveedor=proveedor,
            tipo_movimiento=tipo_movimiento, fecha_desde=fecha_desde, fecha_hasta=fecha_hasta,
        )
    if tipo == "transferencias":
        return warehouse_service.get_reporte_transferencias(
            sucursal=sucursal, categoria=categoria, proveedor=proveedor, tipo_movimiento=tipo_movimiento,
        )
    return warehouse_service.get_reporte_analisis_mensual(
        sucursal=sucursal, almacen=almacen, categoria=categoria, proveedor=proveedor,
        tipo_movimiento=tipo_movimiento, fecha_desde=fecha_desde, fecha_hasta=fecha_hasta,
    )


@router.get("/reportes/{tipo}", response_model=ReporteBodegaResponse, dependencies=[Depends(bodeguero_checker)])
def get_reporte(
    tipo: str,
    warehouse_service: WarehouseServiceDep,
    sucursal_filtro: str | None = Depends(sucursal_bodega),
    almacen: str | None = None,
    categoria: str | None = None,
    proveedor: str | None = None,
    tipo_movimiento: str | None = None,
    fecha_desde: str | None = None,
    fecha_hasta: str | None = None,
) -> ReporteBodegaResponse:
    """§2: reporte tipado para gerencia (tipo: justificacion | transferencias |
    analisis-mensual) -- resumen ejecutivo interpretado + secciones de tabla con
    columnas de negocio (Fase 5, docs/auditoria/32_actualizacion_modulo_bodega.md).
    El frontend lo renderiza con vista imprimible (PDF)."""
    if tipo not in _TIPOS_REPORTE:
        raise NotFoundError(f"Tipo de reporte desconocido: {tipo}")
    contenido = _generar_reporte(
        warehouse_service, tipo, sucursal_filtro, almacen, categoria, proveedor,
        tipo_movimiento, fecha_desde, fecha_hasta,
    )
    return ReporteBodegaResponse(**contenido)


@router.get("/reportes/{tipo}/excel", dependencies=[Depends(bodeguero_checker)])
def get_reporte_excel(
    tipo: str,
    warehouse_service: WarehouseServiceDep,
    sucursal_filtro: str | None = Depends(sucursal_bodega),
    almacen: str | None = None,
    categoria: str | None = None,
    proveedor: str | None = None,
    tipo_movimiento: str | None = None,
    fecha_desde: str | None = None,
    fecha_hasta: str | None = None,
) -> Response:
    """§2.1: export XLSX del reporte para edición en Excel -- hoja Resumen (KPIs +
    filtros aplicados) + una hoja por sección con encabezados/formato de negocio."""
    if tipo not in _TIPOS_REPORTE:
        raise NotFoundError(f"Tipo de reporte desconocido: {tipo}")
    contenido = _generar_reporte(
        warehouse_service, tipo, sucursal_filtro, almacen, categoria, proveedor,
        tipo_movimiento, fecha_desde, fecha_hasta,
    )
    archivo = reporte_a_excel(contenido)
    return Response(
        content=archivo,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="reporte_{tipo}.xlsx"'},
    )
