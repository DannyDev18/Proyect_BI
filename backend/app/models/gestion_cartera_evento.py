# backend/app/models/gestion_cartera_evento.py
from sqlalchemy import Column, BigInteger, Integer, String, ForeignKey, DateTime, Date, Text, func, CheckConstraint
from app.database.session import Base

# Auditoría 41 (refactor Cartera 360 -> "Mi Ruta Inteligente de Ventas"), migración 0005:
# el prompt original pide 8 resultados de gestión (§7 del plan); los 3 valores heredados
# ('contactado', 'recompro', 'perdido') se conservan para no romper filas existentes
# (aunque D-1 confirmó 0 filas al momento del refactor, la constante se amplía nunca se
# restringe -- R-4 del plan).
EVENTOS_VALIDOS = (
    "contactado", "recompro", "perdido",
    "no_contesto", "reagendado", "interesado_sin_cierre", "objecion_precio", "objecion_stock",
)

CANALES_VALIDOS = ("llamada", "whatsapp", "email", "visita")


class GestionCarteraEvento(Base):
    """
    Registro de gestión del módulo Ventas — Cartera de Clientes 360 / Mi Ruta
    Inteligente de Ventas. Mapeada a: public.gestion_cartera_eventos
    Ver docs/features/propuesta_nuevos_modulos_roi.md §4 (auditoría 32) y
    docs/features/plan_refactor_cartera360_ruta_inteligente.md §2.3/§4.7 (DEC-4, migración 0005).
    Mismo espíritu que la telemetría de Venta Cruzada (public.recomendaciones_eventos,
    RN-CS2): el vendedor marca el resultado de cada contacto, creando el dato de
    efectividad que hoy no existe (D-1: 0 filas al momento del refactor).
    """
    __tablename__ = "gestion_cartera_eventos"
    __table_args__ = (
        CheckConstraint(
            "evento IN ('contactado', 'recompro', 'perdido', 'no_contesto', 'reagendado', "
            "'interesado_sin_cierre', 'objecion_precio', 'objecion_stock')",
            name="check_gestion_evento_valido",
        ),
        CheckConstraint(
            "canal IS NULL OR canal IN ('llamada', 'whatsapp', 'email', 'visita')",
            name="check_gestion_canal_valido",
        ),
        {"schema": "public"},
    )

    id = Column(BigInteger, primary_key=True, index=True)
    fecha = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    usuario_id = Column(Integer, ForeignKey("public.usuarios.id", ondelete="SET NULL"), nullable=True)
    cliente_sk = Column(Integer, nullable=True)
    evento = Column(String(30), nullable=False)
    motivo = Column(Text, nullable=True)
    # Columnas nuevas de la migración 0005 (DEC-4: el canal SÍ se captura para el panel de
    # Efectividad Comercial §4.8, aunque DEC-4C descarta *recomendar* un canal).
    canal = Column(String(20), nullable=True)
    resultado = Column(Text, nullable=True)
    proxima_accion_fecha = Column(Date, nullable=True)
    nota = Column(Text, nullable=True)


class CarteraRecordatorio(Base):
    """Recordatorios/reagendados del vendedor sobre un cliente de su cartera (§2.3 del
    plan). Tabla nueva, migración 0005. Vive separada de `gestion_cartera_eventos`
    porque un recordatorio tiene un ciclo de vida propio (pendiente -> cumplido/vencido)
    que una fila de evento append-only no representa bien."""
    __tablename__ = "cartera_recordatorios"
    __table_args__ = ({"schema": "public"},)

    id = Column(BigInteger, primary_key=True, index=True)
    usuario_id = Column(Integer, ForeignKey("public.usuarios.id", ondelete="CASCADE"), nullable=False)
    cliente_sk = Column(Integer, nullable=False)
    fecha_programada = Column(Date, nullable=False)
    nota = Column(Text, nullable=True)
    estado = Column(String(20), nullable=False, server_default="pendiente")
    creado_en = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    cumplido_en = Column(DateTime(timezone=True), nullable=True)
