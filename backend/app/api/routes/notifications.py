# backend/app/api/routes/notifications.py
"""Notificaciones Inteligentes Segmentadas por Rol (docs/features/plan_modulo_notificaciones.md,
docs/auditoria/31_modulo_notificaciones.md, RN-N1..RN-N4). Router thin (regla CLAUDE.md):
sin lógica de negocio, solo inyección de dependencias. Segmentación por rol/usuario ocurre
enteramente en `NotificationService` a partir del usuario del JWT -- ningún query param
permite pedir notificaciones de otro rol/usuario."""
from fastapi import APIRouter, Depends

from app.api.dependencies import NotificationServiceDep
from app.core.deps import CurrentUserDep
from app.schemas.notification import MarcarLeidaResponse, NotificacionOut
from app.schemas.pagination import Page, PaginationParams, pagination_params

router = APIRouter()


@router.get("", response_model=list[NotificacionOut])
def get_notificaciones(
    notification_service: NotificationServiceDep,
    current_user: CurrentUserDep,
) -> list[NotificacionOut]:
    """Calculadas (al vuelo) + persistidas (no expiradas) del rol/usuario del token."""
    return notification_service.get_notificaciones(current_user)


@router.post("/{notif_id}/leer", response_model=MarcarLeidaResponse)
def marcar_leida(
    notif_id: int,
    notification_service: NotificationServiceDep,
    current_user: CurrentUserDep,
) -> MarcarLeidaResponse:
    notif = notification_service.marcar_leida(current_user, notif_id)
    return MarcarLeidaResponse(id=notif.id, leida=True)


@router.post("/leer-todas")
def marcar_todas(
    notification_service: NotificationServiceDep,
    current_user: CurrentUserDep,
) -> dict[str, int]:
    marcadas = notification_service.marcar_todas(current_user)
    return {"marcadas": marcadas}


@router.get("/historial", response_model=Page[NotificacionOut])
def get_historial(
    notification_service: NotificationServiceDep,
    current_user: CurrentUserDep,
    pagination: PaginationParams = Depends(pagination_params),
) -> Page[NotificacionOut]:
    return notification_service.get_historial(current_user, pagination)
