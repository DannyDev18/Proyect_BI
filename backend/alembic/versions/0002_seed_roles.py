"""seed roles and admin user

Revision ID: 0002_seed_roles
Revises: 0001_baseline_public
Create Date: 2026-07-16 14:44:53.611042

Reemplaza la parte de catálogo de `edw/08_seed_roles_usuarios.sql` con una migración
de datos idempotente (`ON CONFLICT ... DO NOTHING`), para que también corra sobre una
BD ya inicializada con `edw/07` a la que le falte una tabla nueva con FK a
`roles(nombre)` (p.ej. `notificaciones`) -- el seed de `edw/08` nunca corre por sí solo
en ese caso porque solo vive atado al initdb del volumen nuevo.

A diferencia de `edw/08`, el usuario admin inicial NO usa el hash bcrypt fijo
versionado en el repo -- ese hash conocido es una puerta trasera en producción. La
contraseña se toma de `ADMIN_INITIAL_PASSWORD` (obligatoria) y se hashea aquí mismo con
el mismo esquema (`passlib` + `bcrypt`) que usa el backend
(`app/core/security.py::get_password_hash`).
"""
import os
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from passlib.context import CryptContext

# revision identifiers, used by Alembic.
revision: str = '0002_seed_roles'
down_revision: Union[str, None] = '0001_baseline_public'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def upgrade() -> None:
    op.execute("""
        INSERT INTO public.roles (nombre, descripcion) VALUES
            ('gerencia',      'Gerente de la empresa. Acceso total de solo lectura a todos los dashboards y KPIs globales.'),
            ('administrador', 'Administrador del sistema. Gestiona usuarios, roles y configuración de la plataforma.'),
            ('ventas',        'Vendedor asignado. Accede solo a dashboards de ventas filtrados por su sucursal y código SAP.'),
            ('bodega',        'Jefe de Bodega. Accede a dashboards de inventario y stock por sucursal asignada.')
        ON CONFLICT (nombre) DO NOTHING
    """)

    password = os.environ.get("ADMIN_INITIAL_PASSWORD")
    if not password:
        # Fail-fast (mismo patrón que validar_configuracion en app/core/config.py):
        # sin esta env var no hay forma segura de crear el admin inicial, y omitirla
        # en silencio dejaría production sin ningún usuario administrador.
        raise RuntimeError(
            "ADMIN_INITIAL_PASSWORD no está definida. Es requerida para sembrar el "
            "usuario administrador inicial (0002_seed_roles) -- defínela en el entorno "
            "antes de correr las migraciones."
        )
    hashed_password = _pwd_context.hash(password)

    op.get_bind().execute(
        sa.text("""
            INSERT INTO public.usuarios (nombre, email, hashed_password, rol_id, sucursal, id_vendedor_origen, es_activo)
            SELECT 'Administrador Sistema', 'admin@empresa.com', :hashed_password, r.id, NULL, NULL, TRUE
            FROM public.roles r
            WHERE r.nombre = 'administrador'
            ON CONFLICT (email) DO NOTHING
        """),
        {"hashed_password": hashed_password},
    )


def downgrade() -> None:
    raise NotImplementedError(
        "0002_seed_roles no soporta downgrade: borrar roles/usuarios de producción "
        "por rollback de esquema es más peligroso que dejarlos. Gestionar bajas de "
        "usuario vía la UI/API existente."
    )
