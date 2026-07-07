# backend/app/models/role.py
from sqlalchemy import Column, Integer, String, DateTime, func
from sqlalchemy.orm import relationship
from app.db.session import Base


class Role(Base):
    """
    Catálogo de roles del sistema web.
    Tabla mapeada a: public.roles
    
    Roles del negocio (4 fijos):
      - gerencia      → acceso total de lectura a todos los KPIs
      - administrador → gestión de usuarios y configuración
      - ventas        → dashboards filtrados por sucursal/vendedor
      - bodega        → dashboards de inventario y stock
    """
    __tablename__ = "roles"
    __table_args__ = {"schema": "public"}

    id          = Column(Integer, primary_key=True, index=True)
    nombre      = Column(String(50), unique=True, nullable=False, index=True)
    descripcion = Column(String(200), nullable=True)
    created_at  = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # Relación inversa hacia usuarios
    usuarios = relationship("User", back_populates="role", lazy="dynamic")
