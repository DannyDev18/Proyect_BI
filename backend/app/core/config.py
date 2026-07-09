# backend/app/core/config.py
import os
from pydantic_settings import BaseSettings

_INSECURE_JWT_SECRET_DEFAULT = "super_secret_analytical_token_key_for_bi_thesis"
_INSECURE_PG_PASSWORD_DEFAULT = "CHANGE_ME"


class Settings(BaseSettings):
    PROJECT_NAME: str = "BI Analytics API"
    API_V1_STR: str = "/api/v1"

    # ENV=production activa validaciones fail-fast (ver validar_configuracion() abajo).
    # En dev/test se mantienen los defaults inseguros de más abajo con solo un warning en logs.
    ENV: str = os.getenv("ENV", "development")

    # ── BD Única: postgres_edw (Docker) ─────────────────────────────────
    # Aloja tanto el esquema analítico (edw.*) como el de la app (public.*)
    # Puerto 5433 expuesto al host, pero internamente el backend usa 5432
    POSTGRES_SERVER: str = os.getenv("PG_HOST", "postgres_edw")
    POSTGRES_PORT: str = os.getenv("PG_PORT", "5432")
    POSTGRES_USER: str = os.getenv("PG_USER", "etl_user")
    POSTGRES_PASSWORD: str = os.getenv("PG_PASSWORD", _INSECURE_PG_PASSWORD_DEFAULT)
    POSTGRES_DB: str = os.getenv("PG_DB", "edw")

    @property
    def SQLALCHEMY_DATABASE_URI(self) -> str:
        return (
            f"postgresql://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
            f"@{self.POSTGRES_SERVER}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )

    # ── Seguridad JWT ────────────────────────────────────────────────────
    JWT_SECRET: str = os.getenv("JWT_SECRET", _INSECURE_JWT_SECRET_DEFAULT)
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 8  # 8 horas de sesión laboral

    # ── CORS ─────────────────────────────────────────────────────────────
    # Default "*" (todo permitido) para no romper el flujo de dev local; en producción
    # definir CORS_ORIGINS="https://mi-frontend.com,https://otro.com" en el entorno.
    CORS_ORIGINS: list[str] = os.getenv("CORS_ORIGINS", "*").split(",")

    # ── Modelos ML (serving) ─────────────────────────────────────────────
    # Montado por Docker en /app/ml_models (docker-compose.yml); fallback local
    # para ejecución fuera de contenedor sin Docker.
    ML_MODELS_DIR: str = os.getenv("ML_MODELS_DIR", "/app/ml_models")
    # Ruta al código fuente del pipeline de entrenamiento (ml/), solo presente en
    # entornos de desarrollo (ver docker-compose.override.yml). En producción no
    # existe, y trigger_retraining_pipeline() debe fallar con un mensaje claro.
    ML_SOURCE_DIR: str = os.getenv("ML_SOURCE_DIR", "/app/ml_src")

    class Config:
        case_sensitive = True


settings = Settings()


def validar_configuracion(config: "Settings") -> None:
    """Falla rápido en producción si quedan secretos con el valor inseguro por defecto.
    En dev/test se tolera (con warning) para no romper el flujo local de nadie."""
    import logging
    logger = logging.getLogger(__name__)

    inseguros = []
    if config.JWT_SECRET == _INSECURE_JWT_SECRET_DEFAULT:
        inseguros.append("JWT_SECRET")
    if config.POSTGRES_PASSWORD == _INSECURE_PG_PASSWORD_DEFAULT:
        inseguros.append("POSTGRES_PASSWORD")

    if not inseguros:
        return

    mensaje = (
        f"Variables de entorno con valor inseguro por defecto: {', '.join(inseguros)}. "
        "Defínalas explícitamente antes de desplegar."
    )
    if config.ENV == "production":
        raise ValueError(mensaje)
    logger.warning(mensaje)
