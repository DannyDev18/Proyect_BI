# backend/app/models/user.py
from sqlalchemy import Column, Integer, String, Boolean, ForeignKey, DateTime, func
from sqlalchemy.orm import relationship
from app.database.session import Base


class User(Base):
    """
    Usuarios con acceso a la plataforma web BI.
    Tabla mapeada a: public.usuarios
    
    IMPORTANTE: Esta tabla es INDEPENDIENTE de edw.Dim_Usuario.
    - public.usuarios → personas autorizadas a usar el dashboard web
    - edw.Dim_Usuario → datos históricos de SAP para analytics (sin contraseñas)
    
    El campo id_vendedor_origen permite enlazar al usuario de la app con
    su registro en dw.Dim_Vendedor para ejecutar filtros analíticos seguros.
    El campo codalm enlaza a un usuario con rol "bodega" a un almacén
    específico (edw.Dim_Almacen.codalm); codalm=NULL con rol bodega significa
    acceso a todos los almacenes (panel Administrador, ver UserService.create).
    """
    __tablename__ = "usuarios"
    __table_args__ = {"schema": "public"}

    id                   = Column(Integer, primary_key=True, index=True)
    nombre               = Column(String(100), nullable=False)
    email                = Column(String(100), unique=True, index=True, nullable=False)
    hashed_password      = Column(String(255), nullable=False)
    rol_id               = Column(Integer, ForeignKey("public.roles.id", ondelete="RESTRICT"), nullable=False)
    sucursal             = Column(String(50), nullable=True)          # Filtro de seguridad a nivel de fila
    id_vendedor_origen   = Column(String(15), unique=True, nullable=True)          # Código SAP del vendedor (para JWT)
    codalm               = Column(String(10), nullable=True)          # Código de almacén (bodega); NULL = todos los almacenes
    es_activo            = Column(Boolean, default=True, nullable=False)
    created_at           = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at           = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    # Relación con la tabla de roles (eager-load disponible)
    role = relationship("Role", back_populates="usuarios", lazy="joined")
