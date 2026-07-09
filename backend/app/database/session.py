# backend/app/database/session.py
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from app.core.config import settings

# ── BD Única: postgres_edw (Docker) ─────────────────────────────────────────
# - Esquema analítico: edw.* (dimensiones, hechos, KPIs, ML) — solo lectura desde el backend
# - Esquema de la app: public.* (roles, usuarios, autenticación, metas)
engine = create_engine(
    settings.SQLALCHEMY_DATABASE_URI,
    pool_pre_ping=True,
    pool_size=5,
    max_overflow=10,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()
