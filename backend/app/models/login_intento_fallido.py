# backend/app/models/login_intento_fallido.py
"""Registro de intentos de login fallidos -- Fase 2 Admin (docs/features/
plan_correcciones_pendientes.md §3, panel de salud): antes no se registraban en
absoluto, así que el panel de salud no podía mostrar ningún conteo. Best-effort: un
fallo al escribir aquí no debe tumbar el login (mismo patrón que AuditRepository.
log_action)."""
from sqlalchemy import BigInteger, Column, DateTime, String, func
from app.database.session import Base


class LoginIntentoFallido(Base):
    __tablename__ = "intentos_login_fallidos"
    __table_args__ = {"schema": "public"}

    id     = Column(BigInteger, primary_key=True, index=True)
    email  = Column(String(100), nullable=False, index=True)
    ip     = Column(String(45), nullable=True)
    fecha  = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)
