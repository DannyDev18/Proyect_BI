# backend/app/api/routes/cartera360.py
"""Ventas: Cartera de Clientes 360 (docs/features/propuesta_nuevos_modulos_roi.md §4,
auditoría 32). Router thin: sin lógica de negocio. RBAC: ventas/gerencia/administrador,
self-scope a la cartera propia del vendedor autenticado (mismo patrón `_requerir_vendedor`
de `sales.py`) — administrador/gerencia consultando este router también quedan acotados
a su propio `id_vendedor_origen` (no hay override de "ver todos" en este módulo, a
diferencia de `resolve_sucursal_filter`: la propuesta es la cartera de UN vendedor)."""
from fastapi import APIRouter, Depends

from app.api.dependencies import Cartera360ServiceDep
from app.core.deps import CurrentUserDep, PermissionChecker
from app.core.exceptions import ValidationError
from app.schemas.cartera360 import (
    DetalleClienteResponse,
    ListaTrabajoResponse,
    RegistrarGestionRequest,
    RegistrarGestionResponse,
    TasaRecuperacionResponse,
)

router = APIRouter()

vendedor_checker = PermissionChecker(allowed_roles=["administrador", "gerencia", "ventas"])


def _requerir_vendedor(current_user: CurrentUserDep) -> str:
    if not current_user.id_vendedor_origen:
        raise ValidationError("El usuario actual no tiene un código de vendedor (id_vendedor_origen) asociado.")
    return current_user.id_vendedor_origen


@router.get("/lista-trabajo", response_model=ListaTrabajoResponse, dependencies=[Depends(vendedor_checker)])
def get_lista_trabajo(cartera360_service: Cartera360ServiceDep, current_user: CurrentUserDep) -> ListaTrabajoResponse:
    """Clientes de la cartera propia ordenados por valor histórico × caída de
    frecuencia (auditoría 32: estadística, no la probabilidad del modelo churn — ver
    `get_detalle_cliente` para el enriquecimiento ML bajo demanda)."""
    vendedor = _requerir_vendedor(current_user)
    return ListaTrabajoResponse(clientes=cartera360_service.get_lista_trabajo(vendedor))


@router.get(
    "/clientes/{cliente_id}/detalle", response_model=DetalleClienteResponse, dependencies=[Depends(vendedor_checker)],
)
def get_detalle_cliente(
    cliente_id: str, cartera360_service: Cartera360ServiceDep, current_user: CurrentUserDep,
) -> DetalleClienteResponse:
    """Enriquecimiento ML bajo demanda de un cliente: churn real, segmento RFM y
    recomendaciones de venta cruzada (reutiliza `PredictionService`, sin modelos nuevos).
    Self-scope a la cartera propia (RN-V3, sin override) -- ver H-V2 en docs/auditoria/
    34_actualizacion_modulo_ventas.md."""
    vendedor = _requerir_vendedor(current_user)
    return DetalleClienteResponse(**cartera360_service.get_detalle_cliente(cliente_id, vendedor))


@router.post("/gestion", response_model=RegistrarGestionResponse, dependencies=[Depends(vendedor_checker)])
def registrar_gestion(
    body: RegistrarGestionRequest, cartera360_service: Cartera360ServiceDep, current_user: CurrentUserDep,
) -> RegistrarGestionResponse:
    """Registro de 1 clic del resultado de un contacto (contactado/recompro/perdido) —
    mismo espíritu que la telemetría de Venta Cruzada (RN-CS2)."""
    evento_id = cartera360_service.registrar_gestion(current_user.id, body.cliente_id, body.evento, body.motivo)
    return RegistrarGestionResponse(id=evento_id, evento=body.evento)


@router.get("/tasa-recuperacion", response_model=TasaRecuperacionResponse, dependencies=[Depends(vendedor_checker)])
def get_tasa_recuperacion(
    cartera360_service: Cartera360ServiceDep, current_user: CurrentUserDep,
) -> TasaRecuperacionResponse:
    """Panel del supervisor (§4.2): gerencia/administrador ven la tasa de recuperación
    global; un vendedor ve solo la suya (mismo self-scope que el resto del módulo)."""
    es_supervisor = current_user.role.nombre in ["administrador", "gerencia"]
    usuario_id = None if es_supervisor else current_user.id
    return TasaRecuperacionResponse(**cartera360_service.get_tasa_recuperacion(usuario_id))
