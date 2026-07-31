# backend/app/api/routes/auth.py
import logging
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordRequestForm
from jose import jwt, JWTError

from app.api.dependencies import UserServiceDep
from app.core import security
from app.core.config import settings
from app.core.deps import CurrentUserDep, SessionDep, TokenDep
from app.core.rate_limit import limiter
from app.models.token_revocado import TokenRevocado
from app.schemas.token import Token

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/login", response_model=Token, summary="Iniciar sesión (OAuth2 Password Flow)")
@limiter.limit(settings.AUTH_LOGIN_RATE_LIMIT)
def login_for_access_token(
    request: Request,
    user_service: UserServiceDep,
    form_data: OAuth2PasswordRequestForm = Depends(),
) -> Token:
    """
    Endpoint estándar OAuth2 Password Flow.

    Retorna un JWT Access Token con el payload enriquecido:
    - `sub`: email del usuario
    - `rol`: nombre del rol (p.ej. "ventas")
    - `sucursal`: sucursal del usuario para filtros de seguridad a nivel fila
    - `id_vendedor_origen`: código SAP del vendedor para filtros analíticos automáticos

    El frontend debe almacenar el token y enviarlo como `Authorization: Bearer <token>`.
    """
    user = user_service.authenticate(form_data.username, form_data.password)
    if not user:
        # Fase 2 Admin, panel de salud (docs/features/plan_correcciones_pendientes.md
        # §3): antes no se registraba ningún intento fallido. Best-effort, no bloquea
        # la respuesta 401 si falla.
        user_service.registrar_intento_fallido(form_data.username, request.client.host if request.client else None)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Correo o contraseña incorrectos.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not user.es_activo:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Esta cuenta de usuario ha sido desactivada. Contacta al administrador.",
        )

    access_token_expires = timedelta(minutes=security.settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    extra_claims = {
        "rol": user.role.nombre if user.role else None,
        "sucursal": user.sucursal,
        "id_vendedor_origen": user.id_vendedor_origen,
    }
    token = security.create_access_token(
        subject=user.email, expires_delta=access_token_expires, extra_claims=extra_claims,
    )
    return Token(access_token=token, token_type="bearer")


@router.post(
    "/logout", status_code=status.HTTP_204_NO_CONTENT,
    summary="Cerrar sesión (revoca el token actual del lado del servidor)",
)
def logout(token: TokenDep, current_user: CurrentUserDep, db: SessionDep) -> None:
    """Auditoría 43 (H43-12, docs/auditoria/43_correcciones_sesion_ventas_y_datos.md): sin
    este endpoint, un JWT seguía siendo válido hasta su expiración natural aunque el
    usuario "cerrara sesión" en el frontend. Inserta el `jti` del token actual en la
    denylist (`public.tokens_revocados`) -- `get_current_user` lo rechaza desde ese
    momento, aunque la firma y el `exp` sigan siendo válidos. Idempotente: si el `jti` ya
    estaba revocado (doble logout), no falla.

    No revoca los DEMÁS tokens activos del mismo usuario en otros dispositivos/pestañas --
    fuera de alcance del requerimiento ("cerrar ESTA sesión"), y consistente con el
    estándar OAuth2 de un token por sesión."""
    try:
        payload = jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.ALGORITHM])
    except JWTError:
        # El token ya es inválido por otra razón (expirado, mal formado) -- no hay nada
        # que revocar, pero tampoco es un error para el usuario que solo quiere salir.
        return None

    jti = payload.get("jti")
    exp = payload.get("exp")
    if jti is None or exp is None:
        return None

    ya_revocado = db.query(TokenRevocado.id).filter(TokenRevocado.jti == jti).first()
    if ya_revocado is not None:
        return None

    db.add(TokenRevocado(
        jti=jti,
        usuario_id=current_user.id,
        expira_en=datetime.fromtimestamp(exp, tz=timezone.utc),
    ))
    db.commit()
    logger.info(f"AUDIT_LOGOUT: Usuario '{current_user.email}' cerró sesión, token {jti} revocado.")
    return None
