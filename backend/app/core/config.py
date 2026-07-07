# backend/app/core/config.py
import os
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    PROJECT_NAME: str = "BI Analytics API"
    API_V1_STR: str = "/api/v1"

    # ── BD Única: postgres_edw (Docker) ─────────────────────────────────
    # Aloja tanto el esquema analítico (edw.*) como el de la app (public.*)
    # Puerto 5433 expuesto al host, pero internamente el backend usa 5432
    POSTGRES_SERVER: str = os.getenv("PG_HOST", "postgres_edw")
    POSTGRES_PORT: str = os.getenv("PG_PORT", "5432")
    POSTGRES_USER: str = os.getenv("PG_USER", "etl_user")
    POSTGRES_PASSWORD: str = os.getenv("PG_PASSWORD", "CHANGE_ME")
    POSTGRES_DB: str = os.getenv("PG_DB", "edw")

    @property
    def SQLALCHEMY_DATABASE_URI(self) -> str:
        return (
            f"postgresql://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
            f"@{self.POSTGRES_SERVER}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )

    # ── Seguridad JWT ────────────────────────────────────────────────────
    JWT_SECRET: str = os.getenv("JWT_SECRET", "super_secret_analytical_token_key_for_bi_thesis")
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 8  # 8 horas de sesión laboral

    class Config:
        case_sensitive = True


settings = Settings()
