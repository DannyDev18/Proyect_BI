# backend/app/api/routes/ruta.py
"""Ventas: "Mi Ruta Inteligente de Ventas" (docs/features/plan_refactor_cartera360_
ruta_inteligente.md). Router thin, conviviendo con `/cartera360/*` (estrategia de
migración §7 del plan: los 4 endpoints heredados no cambian). RBAC idéntico al resto
del módulo: self-scope a la cartera propia del vendedor autenticado, sin override."""
from fastapi import APIRouter, Depends

from app.api.dependencies import Cartera360ServiceDep, GestionServiceDep
from app.core.deps import CurrentUserDep, PermissionChecker
from app.schemas.cartera360 import (
    EfectividadComercialResponse,
    PlanSemanalResponse,
    ProximasAccionesResponse,
    RegistrarGestionRutaRequest,
    RegistrarGestionRutaResponse,
    RutaHoyResponse,
    TimelineClienteResponse,
)
from app.api.routes.cartera360 import _requerir_vendedor

router = APIRouter()

vendedor_checker = PermissionChecker(allowed_roles=["administrador", "gerencia", "ventas"])


@router.get("/hoy", response_model=RutaHoyResponse, dependencies=[Depends(vendedor_checker)])
def get_ruta_hoy(cartera360_service: Cartera360ServiceDep, current_user: CurrentUserDep) -> RutaHoyResponse:
    """Ruta priorizada del día (§4.2/§4.3): hasta `CARTERA360_RUTA_TOP_N` clientes con
    score desglosado, motivo real (señales + SHAP), oferta sugerida y clasificación de
    alerta, más las tarjetas del header (§4.1)."""
    vendedor = _requerir_vendedor(current_user)
    return RutaHoyResponse(**cartera360_service.get_ruta_hoy(vendedor))


@router.post("/gestion", response_model=RegistrarGestionRutaResponse, dependencies=[Depends(vendedor_checker)])
def registrar_gestion_ruta(
    body: RegistrarGestionRutaRequest, gestion_service: GestionServiceDep, current_user: CurrentUserDep,
) -> RegistrarGestionRutaResponse:
    """Registro de gestión extendido (§4.7): 8 resultados posibles, canal, próxima
    acción y nota -- convive con `POST /cartera360/gestion` (3 resultados heredados)."""
    vendedor = _requerir_vendedor(current_user)
    resultado = gestion_service.registrar_gestion(
        usuario_id=current_user.id, cliente_id=body.cliente_id, evento=body.evento,
        codven_restriccion=vendedor, canal=body.canal, resultado=body.resultado,
        proxima_accion_fecha=body.proxima_accion_fecha, nota=body.nota,
    )
    return RegistrarGestionRutaResponse(**resultado)


@router.get(
    "/clientes/{cliente_id}/timeline", response_model=TimelineClienteResponse,
    dependencies=[Depends(vendedor_checker)],
)
def get_timeline_cliente(
    cliente_id: str, gestion_service: GestionServiceDep, current_user: CurrentUserDep,
) -> TimelineClienteResponse:
    """Timeline real de un cliente (§4.6): compras/devoluciones/cobros del EDW +
    gestiones registradas, poblado desde el día 1 aunque no haya gestiones (D-1)."""
    vendedor = _requerir_vendedor(current_user)
    return TimelineClienteResponse(**gestion_service.get_timeline_cliente(cliente_id, vendedor))


@router.get("/efectividad", response_model=EfectividadComercialResponse, dependencies=[Depends(vendedor_checker)])
def get_efectividad_comercial(
    gestion_service: GestionServiceDep, current_user: CurrentUserDep,
) -> EfectividadComercialResponse:
    """Efectividad Comercial (§4.8), reemplaza "Tasa de recuperación": gerencia/
    administrador ven el agregado global, un vendedor ve solo el suyo (mismo self-scope
    que `GET /cartera360/tasa-recuperacion`)."""
    es_supervisor = current_user.role.nombre in ["administrador", "gerencia"]
    usuario_id = None if es_supervisor else current_user.id
    return EfectividadComercialResponse(**gestion_service.get_efectividad_comercial(usuario_id))


@router.get(
    "/proximas-acciones", response_model=ProximasAccionesResponse, dependencies=[Depends(vendedor_checker)],
)
def get_proximas_acciones(
    gestion_service: GestionServiceDep, current_user: CurrentUserDep,
) -> ProximasAccionesResponse:
    """Auditoría 43 (H43-13, docs/auditoria/43_correcciones_sesion_ventas_y_datos.md):
    agenda del vendedor con `proxima_accion_fecha` registrada -- independiente del top-N
    de `/ruta/hoy`, que EXCLUYE deliberadamente a estos mismos clientes mientras la fecha
    siga vigente (rotación de la ruta). RLS: self-scope al `codven` del vendedor
    autenticado, sin override, igual que el resto de este router."""
    vendedor = _requerir_vendedor(current_user)
    return ProximasAccionesResponse(**gestion_service.get_proximas_acciones(vendedor))


@router.get("/plan-semanal", response_model=PlanSemanalResponse, dependencies=[Depends(vendedor_checker)])
def get_plan_semanal(
    cartera360_service: Cartera360ServiceDep, gestion_service: GestionServiceDep, current_user: CurrentUserDep,
) -> PlanSemanalResponse:
    """Planificador semanal (§4.9): reparte la ruta priorizada del día en cupos
    lunes-viernes -- regla determinista, etiquetada como "plan sugerido" en la UI."""
    vendedor = _requerir_vendedor(current_user)
    ruta = cartera360_service.get_ruta_hoy(vendedor)
    dias = gestion_service.get_plan_semanal(ruta["clientes"])
    return PlanSemanalResponse(dias=dias)
