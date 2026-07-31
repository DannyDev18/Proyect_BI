# backend/app/api/routes/warehouse.py
"""Bodega: dashboard de inventario y abastecimiento (docs/features/modulo_bodega.md,
auditoría 23). El endpoint legado `/demand-forecasting` se conserva sin cambios (H23-7);
el módulo nuevo vive en las rutas siguientes.

Routers thin (regla CLAUDE.md): sin lógica de negocio, solo inyección de dependencias
y traducción de query params. RBAC: roles bodega/gerencia/administrador; el rol bodega
queda forzado a sus almacenes asignados vía `resolve_almacenes_filter` (RN-B10,
`public.usuario_almacenes`). `sucursal` NO se usa como filtro de seguridad en este
módulo (docs/auditoria/42_..., hallazgo Bodega-sucursal): `edw.dim_sucursal` agrupa
`codalm` muy distintos bajo un mismo nombre (ej. "PRINCIPAL: MATRIZ" agrupa 8 almacenes,
incluidas camionetas de vendedores individuales y bodegas de consignación) -- no es la
unidad de acceso real del rol bodega, y forzarla producía 0 filas para cualquier usuario
cuyo `usuarios.sucursal` no calzara textualmente con `dim_sucursal.nombre_sucursal`
(caso real confirmado: un usuario con `todos_los_almacenes=True` veía el dashboard
completamente vacío)."""
import datetime

from fastapi import APIRouter, Depends, Response

from app.api.dependencies import (
    AnalyticsServiceDep,
    CatalogRepositoryDep,
    PredictionServiceDep,
    WarehouseServiceDep,
    resolve_almacenes_filter,
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


# ── Endpoints legados (pre-módulo, consumidores existentes) ───────────────────
@router.get("/kpis-inventory", response_model=BPKPIBodega, dependencies=[Depends(bodeguero_checker)])
def get_warehouse_kpis(
    analytics_service: AnalyticsServiceDep,
    almacenes_permitidos: list[str] | None = Depends(resolve_almacenes_filter),
) -> BPKPIBodega:
    """Ítems en sobrestock, en riesgo de desabastecimiento, y sugerencias de
    transferencias entre almacenes."""
    kpis = analytics_service.get_warehouse_kpis(almacenes_permitidos=almacenes_permitidos)
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
    catalog_repo: CatalogRepositoryDep,
    almacenes_permitidos: list[str] | None = Depends(resolve_almacenes_filter),
    categoria: str | None = None,
) -> FiltrosBodegaResponse:
    """Catálogos para los filtros globales del dashboard de bodega. El selector de
    almacén (RN-B10) solo lista las bodegas asignadas al usuario -- si se creó para una
    sola bodega, no ve las demás en el desplegable; si se marcó `todos_los_almacenes`,
    ve el catálogo completo, igual que gerencia/administrador. `categoria` (Fase 2,
    filtros "inteligentes"): si se pasa, `proveedores` se restringe a los que
    realmente suministran esa categoría -- evita ofrecer combinaciones inexistentes."""
    almacenes = analytics_service.get_almacenes()
    if almacenes_permitidos is not None:
        # `analytics_service.get_almacenes()` devuelve nombres (catálogo compartido con
        # otros módulos); la asignación del usuario es por `codalm` -- se traduce vía
        # CatalogRepository.list_almacenes() (mismo catálogo que usa el panel Admin).
        nombres_permitidos = {
            a["nombre_almacen"] for a in catalog_repo.list_almacenes() if a["codalm"] in almacenes_permitidos
        }
        almacenes = [n for n in almacenes if n in nombres_permitidos]
    data = warehouse_service.get_filtros({
        "almacenes": almacenes,
        "categorias": analytics_service.get_categories(),
        "sucursales": analytics_service.get_sucursales(),
    }, categoria=categoria)
    return FiltrosBodegaResponse(**data)


# ── §1.2 KPIs ─────────────────────────────────────────────────────────────────
@router.get("/kpis", response_model=KpisBodegaResponse, dependencies=[Depends(bodeguero_checker)])
def get_kpis_bodega(
    warehouse_service: WarehouseServiceDep,
    almacen: str | None = None,
    categoria: str | None = None,
    proveedor: str | None = None,
    tipo_movimiento: str | None = None,
    fecha_desde: str | None = None,
    fecha_hasta: str | None = None,
) -> KpisBodegaResponse:
    """Los 6 KPIs del dashboard (§1.2), afectados por los filtros globales."""
    data = warehouse_service.get_kpis(
        almacen=almacen, categoria=categoria,
        proveedor=proveedor, tipo_movimiento=tipo_movimiento,
        fecha_desde=fecha_desde, fecha_hasta=fecha_hasta,
    )
    return KpisBodegaResponse(**data)


# ── §1.3 Gráficos ─────────────────────────────────────────────────────────────
@router.get("/salidas-forecast", response_model=SalidasForecastResponse, dependencies=[Depends(bodeguero_checker)])
def get_salidas_forecast(
    warehouse_service: WarehouseServiceDep,
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
        almacen=almacen, categoria=categoria,
        proveedor=proveedor, fecha_desde=fecha_desde, fecha_hasta=fecha_hasta,
    )
    return SalidasForecastResponse(**data)


@router.get("/prediccion-compras-mes", response_model=PrediccionComprasMesResponse, dependencies=[Depends(bodeguero_checker)])
def get_prediccion_compras_mes(
    warehouse_service: WarehouseServiceDep,
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
        almacen=almacen, proveedor=proveedor,
    )
    return PrediccionComprasMesResponse(**data)


@router.get("/rotacion-matriz", response_model=RotacionMatrizResponse, dependencies=[Depends(bodeguero_checker)])
def get_rotacion_matriz(
    warehouse_service: WarehouseServiceDep,
    almacen: str | None = None,
    categoria: str | None = None,
    proveedor: str | None = None,
    tipo_movimiento: str | None = None,
    fecha_desde: str | None = None,
    fecha_hasta: str | None = None,
) -> RotacionMatrizResponse:
    """G2: matriz rotación × margen por producto (cuadrantes de prioridad)."""
    data = warehouse_service.get_rotacion_matriz(
        almacen=almacen, categoria=categoria,
        proveedor=proveedor, tipo_movimiento=tipo_movimiento,
        fecha_desde=fecha_desde, fecha_hasta=fecha_hasta,
    )
    return RotacionMatrizResponse(**data)


@router.get("/top-productos", response_model=list[ProductoTopSalidas], dependencies=[Depends(bodeguero_checker)])
def get_top_productos(
    warehouse_service: WarehouseServiceDep,
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
        almacen=almacen, categoria=categoria,
        proveedor=proveedor, tipo_movimiento=tipo_movimiento,
        fecha_desde=fecha_desde, fecha_hasta=fecha_hasta, limit=min(limit, 100),
    )
    return [ProductoTopSalidas(**d) for d in data]


@router.get("/salidas-categoria", response_model=list[CategoriaSalidas], dependencies=[Depends(bodeguero_checker)])
def get_salidas_categoria(
    warehouse_service: WarehouseServiceDep,
    almacen: str | None = None,
    proveedor: str | None = None,
    tipo_movimiento: str | None = None,
    fecha_desde: str | None = None,
    fecha_hasta: str | None = None,
) -> list[CategoriaSalidas]:
    """G4: distribución de salidas por categoría con comparativa vs período anterior."""
    data = warehouse_service.get_salidas_categoria(
        almacen=almacen, proveedor=proveedor,
        tipo_movimiento=tipo_movimiento, fecha_desde=fecha_desde, fecha_hasta=fecha_hasta,
    )
    return [CategoriaSalidas(**d) for d in data]


@router.get("/stock-reorden", response_model=Page[ProductoStockReorden], dependencies=[Depends(bodeguero_checker)])
def get_stock_reorden(
    warehouse_service: WarehouseServiceDep,
    pagination: PaginationParams = Depends(pagination_params),
    almacen: str | None = None,
    categoria: str | None = None,
    proveedor: str | None = None,
    tipo_movimiento: str | None = None,
    solo_criticos: bool = False,
) -> Page[ProductoStockReorden]:
    """G5: estado de stock vs punto de reorden (RN-B1/B2). Paginado (docs/auditoria/24)."""
    pagina = warehouse_service.get_stock_reorden(
        pagination, almacen=almacen, categoria=categoria,
        proveedor=proveedor, tipo_movimiento=tipo_movimiento, solo_criticos=solo_criticos,
    )
    return Page(
        items=[ProductoStockReorden(**d) for d in pagina.items],
        total=pagina.total, page=pagina.page, page_size=pagina.page_size, total_pages=pagina.total_pages,
    )


@router.get("/necesidad-compra", response_model=NecesidadCompraResponse, dependencies=[Depends(bodeguero_checker)])
def get_necesidad_compra(
    warehouse_service: WarehouseServiceDep,
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
        pagination, almacen=almacen, categoria=categoria,
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
        pagination, almacen=almacen, categoria=categoria,
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
    pagination: PaginationParams = Depends(pagination_params),
    categoria: str | None = None,
    proveedor: str | None = None,
    tipo_movimiento: str | None = None,
) -> TransferenciasResponse:
    """§3.2 (RN-B3): transferencias inteligentes entre bodegas con prioridad y ahorro.
    Paginado (docs/auditoria/24)."""
    data = warehouse_service.get_transferencias_sugeridas(
        pagination, categoria=categoria, proveedor=proveedor, tipo_movimiento=tipo_movimiento,
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
_TIPOS_REPORTE = {"justificacion", "transferencias", "analisis-mensual", "sin-venta", "kardex"}


def _generar_reporte(
    # `sucursal` ya no se resuelve desde ningún endpoint (siempre None) -- se conserva el
    # parámetro porque `WarehouseService`/`WarehouseRepository` aún lo aceptan, ver
    # docstring del módulo sobre por qué se retiró como filtro de seguridad/negocio.
    warehouse_service, tipo: str, sucursal: str | None, almacen: str | None,
    categoria: str | None, proveedor: str | None, tipo_movimiento: str | None,
    fecha_desde: str | None, fecha_hasta: str | None,
    solo_con_stock: bool = True, busqueda: str | None = None,
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
    if tipo == "sin-venta":
        return warehouse_service.get_reporte_sin_venta(
            sucursal=sucursal, almacen=almacen, categoria=categoria, proveedor=proveedor,
            fecha_desde=fecha_desde, fecha_hasta=fecha_hasta, solo_con_stock=solo_con_stock, busqueda=busqueda,
        )
    if tipo == "kardex":
        return warehouse_service.get_reporte_kardex(
            sucursal=sucursal, almacen=almacen, categoria=categoria, proveedor=proveedor,
            tipo_movimiento=tipo_movimiento, fecha_desde=fecha_desde, fecha_hasta=fecha_hasta, busqueda=busqueda,
        )
    return warehouse_service.get_reporte_analisis_mensual(
        sucursal=sucursal, almacen=almacen, categoria=categoria, proveedor=proveedor,
        tipo_movimiento=tipo_movimiento, fecha_desde=fecha_desde, fecha_hasta=fecha_hasta,
    )


@router.get("/reportes/{tipo}", response_model=ReporteBodegaResponse, dependencies=[Depends(bodeguero_checker)])
def get_reporte(
    tipo: str,
    warehouse_service: WarehouseServiceDep,
    almacen: str | None = None,
    categoria: str | None = None,
    proveedor: str | None = None,
    tipo_movimiento: str | None = None,
    fecha_desde: str | None = None,
    fecha_hasta: str | None = None,
    solo_con_stock: bool = True,
    busqueda: str | None = None,
) -> ReporteBodegaResponse:
    """§2: reporte tipado para gerencia (tipo: justificacion | transferencias |
    analisis-mensual | sin-venta | kardex) -- resumen ejecutivo interpretado +
    secciones de tabla con columnas de negocio (Fase 5, docs/auditoria/32_actualizacion_
    modulo_bodega.md). `solo_con_stock`/`busqueda` solo aplican a `tipo=sin-venta`
    (Fase 6.2, H-9): reemplaza QUERY_PRODUCTOS_SIN_VENTA/QUERY_ARTICULOS_ESTANCADOS con
    un solo reporte parametrizado. `tipo=kardex` (Fase 6.7, H-11) migra
    QUERY_KARDEX_MOVIMIENTOS: listado de movimientos individuales, no un agregado.
    El frontend lo renderiza como tabla; el export descargable es Excel (`/excel`)."""
    if tipo not in _TIPOS_REPORTE:
        raise NotFoundError(f"Tipo de reporte desconocido: {tipo}")
    contenido = _generar_reporte(
        warehouse_service, tipo, None, almacen, categoria, proveedor,
        tipo_movimiento, fecha_desde, fecha_hasta, solo_con_stock, busqueda,
    )
    return ReporteBodegaResponse(**contenido)


@router.get("/reportes/{tipo}/excel", dependencies=[Depends(bodeguero_checker)])
def get_reporte_excel(
    tipo: str,
    warehouse_service: WarehouseServiceDep,
    almacen: str | None = None,
    categoria: str | None = None,
    proveedor: str | None = None,
    tipo_movimiento: str | None = None,
    fecha_desde: str | None = None,
    fecha_hasta: str | None = None,
    solo_con_stock: bool = True,
    busqueda: str | None = None,
) -> Response:
    """§2.1: export XLSX del reporte para edición en Excel -- hoja Resumen (KPIs +
    filtros aplicados) + una hoja por sección con encabezados/formato de negocio."""
    if tipo not in _TIPOS_REPORTE:
        raise NotFoundError(f"Tipo de reporte desconocido: {tipo}")
    contenido = _generar_reporte(
        warehouse_service, tipo, None, almacen, categoria, proveedor,
        tipo_movimiento, fecha_desde, fecha_hasta, solo_con_stock, busqueda,
    )
    archivo = reporte_a_excel(contenido)
    # Fase 6.4 (H-4, docs/features/plan_correcciones_integrales_sistema.md): fecha/hora
    # del servidor en el nombre de archivo, generado en backend (no en frontend).
    marca_tiempo = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M")
    return Response(
        content=archivo,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="reporte_{tipo}_{marca_tiempo}.xlsx"'},
    )
