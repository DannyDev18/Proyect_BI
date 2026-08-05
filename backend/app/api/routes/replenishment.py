# backend/app/api/routes/replenishment.py
"""Reabastecimiento Inteligente (docs/features/plan_reabastecimiento_inteligente.md
§6.4, auditoría docs/auditoria/50_reabastecimiento_inteligente.md): Sistema de Apoyo a
Decisiones para reposición de inventario -- convive con `/analytics/bodega/necesidad-
compra` (motor determinista, sin tocar), no lo reemplaza (Fase 3 del plan). Mismo RBAC
y misma RLS por almacén (RN-B10) que el resto del módulo Bodega, vía
`WarehouseRepository`/`resolve_almacenes_filter` reutilizados en `ReplenishmentService`.

Routers thin (regla CLAUDE.md): sin lógica de negocio, solo inyección de dependencias
y traducción de query params."""
from fastapi import APIRouter, Depends

from app.api.dependencies import ReplenishmentConfigServiceDep, ReplenishmentServiceDep
from app.core.deps import CurrentUserDep, PermissionChecker
from app.schemas.pagination import Page, PaginationParams, pagination_params, paginar
from app.inventory.schemas import (
    ActualizarPoliticaRequest,
    AlertaReabastecimiento,
    CrearPropuestaRequest,
    ItemReabastecimiento,
    LeadTimeConfig,
    PoliticaABC,
    PropuestaCompraDetalleOut,
    PropuestaCompraOut,
    ResumenReabastecimiento,
    SimularReabastecimientoRequest,
    SimularReabastecimientoResponse,
    UpsertLeadTimeRequest,
)

router = APIRouter()

bodeguero_checker = PermissionChecker(allowed_roles=["administrador", "gerencia", "bodega"])
gerencia_checker = PermissionChecker(allowed_roles=["administrador", "gerencia"])


@router.get("/lista", response_model=Page[ItemReabastecimiento], dependencies=[Depends(bodeguero_checker)])
def get_lista(
    service: ReplenishmentServiceDep,
    pagination: PaginationParams = Depends(pagination_params),
    almacen: str | None = None,
    categoria: str | None = None,
    proveedor: str | None = None,
    tipo_movimiento: str | None = None,
    horizonte_dias: float | None = None,
    solo_criticos: bool = False,
    riesgo: str | None = None,
    clase_abc: str | None = None,
    clase_xyz: str | None = None,
) -> Page[ItemReabastecimiento]:
    """Bloque 2 del plan (Lista Inteligente de Reabastecimiento): tabla priorizada por
    criticidad, no por ventas (H-13/G3 de la auditoría 50 -- el top de ventas rara vez
    coincide con el riesgo real de quiebre)."""
    filas = service.get_lista_reabastecimiento(
        almacen=almacen, categoria=categoria, proveedor=proveedor,
        tipo_movimiento=tipo_movimiento, horizonte_dias=horizonte_dias,
        solo_criticos=solo_criticos, riesgo=riesgo, clase_abc=clase_abc, clase_xyz=clase_xyz,
    )
    pagina = paginar(filas, pagination)
    return Page(
        items=[ItemReabastecimiento(**f) for f in pagina.items],
        total=pagina.total, page=pagina.page, page_size=pagina.page_size, total_pages=pagina.total_pages,
    )


@router.get("/lista/{codart}/explicacion", response_model=ItemReabastecimiento, dependencies=[Depends(bodeguero_checker)])
def get_explicacion(
    codart: str,
    service: ReplenishmentServiceDep,
    almacen: str | None = None,
    categoria: str | None = None,
    proveedor: str | None = None,
    tipo_movimiento: str | None = None,
    horizonte_dias: float | None = None,
) -> ItemReabastecimiento:
    """Bloque 3 del plan (Explicabilidad, §6.4): desglose completo de un solo artículo
    -- deep-link desde alertas o desde la fila expandible de la lista, sin recalcular
    la clasificación ABC en aislamiento (ver docstring del servicio)."""
    fila = service.get_explicacion(
        codart, almacen=almacen, categoria=categoria, proveedor=proveedor,
        tipo_movimiento=tipo_movimiento, horizonte_dias=horizonte_dias,
    )
    return ItemReabastecimiento(**fila)


@router.get("/resumen", response_model=ResumenReabastecimiento, dependencies=[Depends(bodeguero_checker)])
def get_resumen(
    service: ReplenishmentServiceDep,
    almacen: str | None = None,
    categoria: str | None = None,
    proveedor: str | None = None,
    tipo_movimiento: str | None = None,
    horizonte_dias: float | None = None,
) -> ResumenReabastecimiento:
    """Bloque 1 del plan (Centro de Decisiones): KPIs de decisión, no de censo (H-6 de
    la auditoría 50: el dashboard actual calcula 6 KPIs y descarta 3 sin usarlos)."""
    data = service.get_resumen(
        almacen=almacen, categoria=categoria, proveedor=proveedor,
        tipo_movimiento=tipo_movimiento, horizonte_dias=horizonte_dias,
    )
    return ResumenReabastecimiento(**data)


@router.get("/alertas", response_model=list[AlertaReabastecimiento], dependencies=[Depends(bodeguero_checker)])
def get_alertas(
    service: ReplenishmentServiceDep,
    almacen: str | None = None,
    categoria: str | None = None,
    proveedor: str | None = None,
    tipo_movimiento: str | None = None,
    horizonte_dias: float | None = None,
) -> list[AlertaReabastecimiento]:
    """F7 del plan (§7.4): cambio brusco de demanda y tendencia decreciente sostenida --
    señales que el generador existente de Bodega nunca calculó (ver docstring del
    servicio para por qué el riesgo de quiebre y el sobrestock NO se repiten aquí)."""
    crudas = service.get_alertas(
        almacen=almacen, categoria=categoria, proveedor=proveedor,
        tipo_movimiento=tipo_movimiento, horizonte_dias=horizonte_dias,
    )
    return [AlertaReabastecimiento(**a) for a in crudas]


@router.post("/simular", response_model=SimularReabastecimientoResponse, dependencies=[Depends(bodeguero_checker)])
def post_simular(
    body: SimularReabastecimientoRequest, service: ReplenishmentServiceDep,
) -> SimularReabastecimientoResponse:
    """F8 del plan (bloque 4, Simulación): recalcula el Centro de Decisiones bajo
    parámetros hipotéticos de política -- SIN persistir nada en `reabastecimiento_
    politica`/`_lead_time`. Cambiar la política real sigue siendo `PUT /politica`/
    `PUT /lead-times` (solo gerencia/administrador); este endpoint es de solo lectura,
    igual que `/lista`/`/resumen`."""
    resultado = service.simular(
        niveles_servicio=body.niveles_servicio, lead_time_default_dias=body.lead_time_default_dias,
        almacen=body.almacen, categoria=body.categoria, proveedor=body.proveedor,
        tipo_movimiento=body.tipo_movimiento, horizonte_dias=body.horizonte_dias,
    )
    return SimularReabastecimientoResponse(
        resumen_actual=ResumenReabastecimiento(**resultado["resumen_actual"]),
        resumen_simulado=ResumenReabastecimiento(**resultado["resumen_simulado"]),
        parametros_simulados=resultado["parametros_simulados"],
    )


# ── Configuración editable (§6.3): política de nivel de servicio + lead time ────────
@router.get("/politica", response_model=list[PoliticaABC], dependencies=[Depends(gerencia_checker)])
def get_politica(config_service: ReplenishmentConfigServiceDep) -> list[PoliticaABC]:
    return [PoliticaABC.model_validate(p) for p in config_service.get_politica()]


@router.put("/politica/{clase_abc}", response_model=PoliticaABC, dependencies=[Depends(gerencia_checker)])
def update_politica(
    clase_abc: str, body: ActualizarPoliticaRequest,
    config_service: ReplenishmentConfigServiceDep, current_user: CurrentUserDep,
) -> PoliticaABC:
    fila = config_service.update_politica(clase_abc, body.nivel_servicio, current_user.id)
    return PoliticaABC.model_validate(fila)


@router.get("/lead-times", response_model=list[LeadTimeConfig], dependencies=[Depends(gerencia_checker)])
def get_lead_times(config_service: ReplenishmentConfigServiceDep) -> list[LeadTimeConfig]:
    return [LeadTimeConfig.model_validate(f) for f in config_service.get_lead_times()]


@router.put("/lead-times", response_model=LeadTimeConfig, dependencies=[Depends(gerencia_checker)])
def upsert_lead_time(
    body: UpsertLeadTimeRequest, config_service: ReplenishmentConfigServiceDep, current_user: CurrentUserDep,
) -> LeadTimeConfig:
    fila = config_service.upsert_lead_time(
        body.dias, current_user.id, producto=body.producto, categoria=body.categoria, proveedor=body.proveedor,
    )
    return LeadTimeConfig.model_validate(fila)


@router.delete("/lead-times/{lead_time_id}", status_code=204, dependencies=[Depends(gerencia_checker)])
def delete_lead_time(lead_time_id: int, config_service: ReplenishmentConfigServiceDep) -> None:
    config_service.delete_lead_time(lead_time_id)


# ── F9 (§6.3/§8, bloque 5 Gestión Operativa): propuestas de compra persistidas ──────
@router.post("/propuestas", response_model=PropuestaCompraDetalleOut, dependencies=[Depends(bodeguero_checker)])
def crear_propuesta(
    body: CrearPropuestaRequest, service: ReplenishmentServiceDep, current_user: CurrentUserDep,
) -> PropuestaCompraDetalleOut:
    propuesta = service.crear_propuesta(
        usuario_id=current_user.id, almacen=body.almacen, categoria=body.categoria,
        proveedor=body.proveedor, tipo_movimiento=body.tipo_movimiento, horizonte_dias=body.horizonte_dias,
        solo_criticos=body.solo_criticos, riesgo=body.riesgo, clase_abc=body.clase_abc, clase_xyz=body.clase_xyz,
    )
    return PropuestaCompraDetalleOut.model_validate(propuesta)


@router.get("/propuestas", response_model=list[PropuestaCompraOut], dependencies=[Depends(bodeguero_checker)])
def listar_propuestas(service: ReplenishmentServiceDep) -> list[PropuestaCompraOut]:
    return [PropuestaCompraOut.model_validate(p) for p in service.listar_propuestas()]


@router.get("/propuestas/{propuesta_id}", response_model=PropuestaCompraDetalleOut, dependencies=[Depends(bodeguero_checker)])
def get_propuesta(propuesta_id: int, service: ReplenishmentServiceDep) -> PropuestaCompraDetalleOut:
    return PropuestaCompraDetalleOut.model_validate(service.get_propuesta(propuesta_id))


@router.post("/propuestas/{propuesta_id}/aprobar", response_model=PropuestaCompraOut, dependencies=[Depends(bodeguero_checker)])
def aprobar_propuesta(propuesta_id: int, service: ReplenishmentServiceDep) -> PropuestaCompraOut:
    return PropuestaCompraOut.model_validate(service.decidir_propuesta(propuesta_id, "aprobar"))


@router.post("/propuestas/{propuesta_id}/rechazar", response_model=PropuestaCompraOut, dependencies=[Depends(bodeguero_checker)])
def rechazar_propuesta(propuesta_id: int, service: ReplenishmentServiceDep) -> PropuestaCompraOut:
    return PropuestaCompraOut.model_validate(service.decidir_propuesta(propuesta_id, "rechazar"))
