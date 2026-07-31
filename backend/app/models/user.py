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
    Un usuario con rol "bodega" se enlaza a una o varias bodegas mediante la
    relación N:N `almacenes` (public.usuario_almacenes); `todos_los_almacenes=True`
    significa acceso a todos los almacenes sin necesidad de filas en esa tabla
    (docs/features/plan_correcciones_integrales_sistema.md, B-2 / RN-B10 -- reemplaza
    el antiguo campo 1:1 `codalm`, que solo distinguía "una" de "todas").
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
    todos_los_almacenes  = Column(Boolean, default=False, nullable=False)  # rol bodega: acceso a todas las bodegas
    es_activo            = Column(Boolean, default=True, nullable=False)
    created_at           = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at           = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    # Relación con la tabla de roles (eager-load disponible)
    role = relationship("Role", back_populates="usuarios", lazy="joined")
    # Bodegas asignadas (rol "bodega", N:N); vacía + todos_los_almacenes=False = sin asignar.
    almacenes = relationship(
        "UsuarioAlmacen", back_populates="usuario", cascade="all, delete-orphan", lazy="joined",
    )

    @property
    def codalms(self) -> list[str]:
        """Códigos de almacén asignados (orden estable). Vacío si no tiene ninguno o
        si `todos_los_almacenes=True` (ese caso se representa aparte, no como lista)."""
        return sorted(a.codalm for a in self.almacenes)
