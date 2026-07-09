# backend/app/api/routes/auth.py
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm

from app.api.dependencies import UserServiceDep
from app.core import security
from app.schemas.token import Token

router = APIRouter()


@router.post("/login", response_model=Token, summary="Iniciar sesión (OAuth2 Password Flow)")
def login_for_access_token(
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
