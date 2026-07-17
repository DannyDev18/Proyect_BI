# backend/app/database/base.py
# Importa todos los modelos para que SQLAlchemy registre su metadata. Necesario para
# que Alembic (backend/alembic/, docs/features/plan_migraciones_esquema_public.md) vea
# los 13 modelos al comparar Base.metadata -- única fuente de verdad del esquema public.
from app.database.session import Base  # noqa: F401
from app.models.role import Role  # noqa: F401
from app.models.user import User  # noqa: F401
from app.models.goal import Goal  # noqa: F401
from app.models.recommendation_event import RecommendationEvent  # noqa: F401
from app.models.gestion_cartera_evento import GestionCarteraEvento  # noqa: F401
from app.models.commission_config import (  # noqa: F401
    ComisionMatrizCategoria, ComisionFactorCredito, ComisionConfigVendedor, ComisionLiquidacion,
    ComisionConfigAuditoria,
)
from app.models.notification import Notification  # noqa: F401
from app.models.anomalia_revision import AnomaliaRevision  # noqa: F401
from app.models.login_intento_fallido import LoginIntentoFallido  # noqa: F401
