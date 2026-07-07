# backend/app/core/security.py
from datetime import datetime, timedelta, timezone
from typing import Any, Union
from jose import jwt
from passlib.context import CryptContext
from app.core.config import settings

# passlib con bcrypt (rounds=12) para hashing seguro de contraseñas
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verifica una contraseña en texto plano contra su hash bcrypt."""
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    """Genera un hash bcrypt de la contraseña."""
    return pwd_context.hash(password)


def create_access_token(
    subject: Union[str, Any],
    expires_delta: timedelta = None,
    extra_claims: dict = None,
) -> str:
    """
    Genera un JWT Access Token con claims estándar y claims analíticos.
    
    Args:
        subject: Email del usuario (campo 'sub' del JWT)
        expires_delta: Duración del token. Por defecto: ACCESS_TOKEN_EXPIRE_MINUTES
        extra_claims: Claims adicionales para inyectar en el payload:
            - rol: nombre del rol (p.ej. "ventas")
            - sucursal: sucursal del usuario para filtros RLS
            - id_vendedor_origen: código SAP del vendedor para filtros analíticos
    
    El payload resultante permite que el backend filtre dw.fact_ventas
    directamente desde el JWT sin consultar la BD en cada request:
        WHERE id_vendedor = jwt_payload["id_vendedor_origen"]
    """
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)

    to_encode = {"exp": expire, "sub": str(subject)}

    # Inyectar claims analíticos en el token para filtros de seguridad fila
    if extra_claims:
        to_encode.update(extra_claims)

    encoded_jwt = jwt.encode(to_encode, settings.JWT_SECRET, algorithm=settings.ALGORITHM)
    return encoded_jwt
