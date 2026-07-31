# backend/app/models/token_revocado.py
"""Denylist de tokens revocados (auditoría 43, H43-12): mapeada a
public.tokens_revocados. Append-only -- cada logout inserta una fila con el `jti` del
token cerrado; nunca se actualiza ni se borra desde el código de la app (solo un job de
limpieza futuro podría purgar filas con `expira_en` vencido, no implementado aquí porque
la fila vencida ya es inofensiva: get_current_user también rechaza el token por `exp`)."""
from sqlalchemy import Column, BigInteger, Integer, String, DateTime, ForeignKey, func
from app.database.session import Base


class TokenRevocado(Base):
    """Un `jti` por fila = un token que dejó de ser válido antes de su expiración natural
    porque el usuario cerró sesión explícitamente. `get_current_user` rechaza cualquier
    token cuyo `jti` aparezca aquí, sin importar que la firma y el `exp` sigan siendo
    válidos."""
    __tablename__ = "tokens_revocados"
    __table_args__ = {"schema": "public"}

    id = Column(BigInteger, primary_key=True, index=True)
    jti = Column(String(36), nullable=False, unique=True, index=True)
    usuario_id = Column(Integer, ForeignKey("public.usuarios.id", ondelete="SET NULL"), nullable=True)
    expira_en = Column(DateTime(timezone=True), nullable=False)
    revocado_en = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
