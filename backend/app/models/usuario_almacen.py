# backend/app/models/usuario_almacen.py
from sqlalchemy import Column, ForeignKey, Integer, String
from sqlalchemy.orm import relationship

from app.database.session import Base


class UsuarioAlmacen(Base):
    """Asignación N:N de bodegas a un usuario (public.usuario_almacenes).

    Reemplaza el antiguo `usuarios.codalm` (1:1) -- un usuario con rol "bodega" puede
    tener varias filas aquí (varias bodegas asignadas por el admin al crearlo/editarlo).
    `usuarios.todos_los_almacenes=TRUE` es el caso "todas" y no requiere filas en esta
    tabla (docs/features/plan_correcciones_integrales_sistema.md, B-2 / RN-B10).
    """
    __tablename__ = "usuario_almacenes"
    __table_args__ = {"schema": "public"}

    usuario_id = Column(Integer, ForeignKey("public.usuarios.id", ondelete="CASCADE"), primary_key=True)
    codalm = Column(String(10), primary_key=True)

    usuario = relationship("User", back_populates="almacenes")
