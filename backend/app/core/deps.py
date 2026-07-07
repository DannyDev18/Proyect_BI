# backend/app/core/deps.py
import logging
from typing import Generator, Annotated
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import jwt, JWTError
from pydantic import BaseModel
from sqlalchemy.orm import Session, joinedload

from app.core.config import settings
from app.db.session import SessionLocal
from app.models.user import User

logger = logging.getLogger(__name__)

reusable_oauth2 = OAuth2PasswordBearer(
    tokenUrl=f"{settings.API_V1_STR}/auth/login"
)


def get_db() -> Generator:
    """Dependencia que provee una sesión de BD y garantiza su cierre."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# Tipos anotados para inyección de dependencias
SessionDep = Annotated[Session, Depends(get_db)]
TokenDep = Annotated[str, Depends(reusable_oauth2)]


class TokenPayload(BaseModel):
    sub: str | None = None


def get_current_user(db: SessionDep, token: TokenDep) -> User:
    """
    Dependencia que valida el JWT Bearer token y retorna el usuario autenticado.
    El usuario se carga con joinedload(User.role) para evitar N+1 queries.
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="No se pudo validar las credenciales de acceso.",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            raise credentials_exception
        token_data = TokenPayload(sub=username)
    except JWTError:
        raise credentials_exception

    # Carga el usuario con la relación del rol en un solo JOIN
    user = (
        db.query(User)
        .options(joinedload(User.role))
        .filter(User.email == token_data.sub)
        .first()
    )

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Usuario del token no encontrado en la base de datos."
        )
    if not user.es_activo:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Esta cuenta de usuario ha sido desactivada."
        )

    return user


# Tipo anotado del usuario actual
CurrentUserDep = Annotated[User, Depends(get_current_user)]


class PermissionChecker:
    """
    Verificador de roles para usar como dependencia FastAPI.
    
    Uso:
        only_admin = PermissionChecker(["administrador"])
        
        @router.get("/", dependencies=[Depends(only_admin)])
        def endpoint_only_admin(): ...
    
    Si el usuario no tiene uno de los allowed_roles, retorna 403 Forbidden
    y registra un evento de auditoría en el log.
    """
    def __init__(self, allowed_roles: list[str]):
        self.allowed_roles = allowed_roles

    def __call__(self, current_user: CurrentUserDep) -> User:
        # Acceder al nombre del rol desde la relación ORM (no desde un campo string)
        user_role_name = current_user.role.nombre if current_user.role else None

        if user_role_name not in self.allowed_roles:
            logger.warning(
                f"AUDIT_ACCESS_DENIED: Usuario '{current_user.email}' "
                f"(Rol: '{user_role_name}') intentó acceder a un recurso "
                f"restringido para roles {self.allowed_roles}."
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Acceso denegado. Privilegios insuficientes para esta acción."
            )
        return current_user
