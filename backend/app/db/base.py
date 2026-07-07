# backend/app/db/base.py
# Importa ambos modelos para que SQLAlchemy registre toda la metadata
# Esto es necesario para Base.metadata.create_all(bind=engine) en main.py
from app.db.session import Base  # noqa: F401
from app.models.role import Role  # noqa: F401
from app.models.user import User  # noqa: F401
from app.models.goal import Goal  # noqa: F401
