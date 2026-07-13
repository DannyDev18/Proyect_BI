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
    # Contratos declarativos (ml/contracts/models/*.json) montados de solo lectura --
    # NO es el código fuente de ml/ (eso es ML_SOURCE_DIR, ausente en producción). Es la
    # interfaz declarada entre las dos imágenes Docker (docs/ml_contracts.md): el backend
    # lee el JSON, nunca importa ml.src.contracts.*.
    ML_CONTRACTS_DIR: str = os.getenv("ML_CONTRACTS_DIR", "/app/ml_contracts")
    # Ruta al código fuente del pipeline de entrenamiento (ml/), solo presente en
    # entornos de desarrollo (ver docker-compose.override.yml). En producción no
    # existe, y trigger_retraining_pipeline() debe fallar con un mensaje claro.
    ML_SOURCE_DIR: str = os.getenv("ML_SOURCE_DIR", "/app/ml_src")

    # ── Módulo Bodega (reglas RN-B1..B5, docs/auditoria/23_modulo_bodega.md) ──
    # Umbrales del requerimiento docs/features/modulo_bodega.md §6.3/§3.2/§3.3;
    # parametrizados por env para no hardcodearlos en el código (regla de CLAUDE.md).
    BODEGA_LEAD_TIME_DIAS: int = int(os.getenv("BODEGA_LEAD_TIME_DIAS", "7"))
    BODEGA_STOCK_SEGURIDAD_DIAS: int = int(os.getenv("BODEGA_STOCK_SEGURIDAD_DIAS", "5"))
    BODEGA_DIAS_DEFICIT: int = int(os.getenv("BODEGA_DIAS_DEFICIT", "15"))
    BODEGA_DIAS_COMPRA: int = int(os.getenv("BODEGA_DIAS_COMPRA", "20"))
    BODEGA_DIAS_OBJETIVO_TRANSFERENCIA: int = int(os.getenv("BODEGA_DIAS_OBJETIVO_TRANSFERENCIA", "30"))
    BODEGA_HORIZONTE_COMPRA_DIAS: int = int(os.getenv("BODEGA_HORIZONTE_COMPRA_DIAS", "30"))
    BODEGA_HORIZONTE_PLAN_DIAS: int = int(os.getenv("BODEGA_HORIZONTE_PLAN_DIAS", "45"))
    BODEGA_DIAS_EXCEDENTE: int = int(os.getenv("BODEGA_DIAS_EXCEDENTE", "60"))
    BODEGA_DIAS_EXCESO: int = int(os.getenv("BODEGA_DIAS_EXCESO", "90"))
    BODEGA_ROTACION_BUENA: float = float(os.getenv("BODEGA_ROTACION_BUENA", "4.0"))
    BODEGA_ROTACION_REGULAR: float = float(os.getenv("BODEGA_ROTACION_REGULAR", "2.0"))
    BODEGA_ROTACION_MIN_COMPRA: float = float(os.getenv("BODEGA_ROTACION_MIN_COMPRA", "3.0"))

    # ── Predicción de compras del próximo mes por categoría (docs/auditoria/24) ──
    # Top-N artículos por ventas de la categoría sobre los que corre `demand_rf`
    # (walk-forward); cache en memoria por proceso para no recalcular 20 series por
    # cada request mientras el EDW no cambie (se carga por lotes, no intra-hora).
    BODEGA_TOP_ARTICULOS_PREDICCION: int = int(os.getenv("BODEGA_TOP_ARTICULOS_PREDICCION", "20"))
    BODEGA_FORECAST_CACHE_TTL_MIN: int = int(os.getenv("BODEGA_FORECAST_CACHE_TTL_MIN", "60"))

    # ── Módulo Venta Cruzada (RN-CS1/RN-CS2, docs/auditoria/25_modulo_cross_selling.md) ──
    CROSS_SELL_TOP_N: int = int(os.getenv("CROSS_SELL_TOP_N", "5"))
    CROSS_SELL_MIN_LIFT: float = float(os.getenv("CROSS_SELL_MIN_LIFT", "1.5"))
    CROSS_SELL_PESO_MARGEN: float = float(os.getenv("CROSS_SELL_PESO_MARGEN", "0.3"))
    # RN-CS3: tope de sugerencias de una misma categoría entre las CROSS_SELL_TOP_N finales
    # -- evita que el asistente muestre solo variantes de la misma categoría del producto
    # en la canasta (hallazgo de uso real, auditoría 25 §6.1) y fuerza diversidad para
    # capturar venta cruzada real entre categorías distintas.
    CROSS_SELL_MAX_POR_CATEGORIA: int = int(os.getenv("CROSS_SELL_MAX_POR_CATEGORIA", "2"))
    # Ventana de análisis para el KPI "top combinaciones de productos" (§6.4): 2 años,
    # misma ventana usada para entrenar el modelo ganador (item-item, ver auditoría 25 §"Estado").
    CROSS_SELL_TOP_COMBINACIONES_DIAS: int = int(os.getenv("CROSS_SELL_TOP_COMBINACIONES_DIAS", "730"))
    CROSS_SELL_TOP_COMBINACIONES_N: int = int(os.getenv("CROSS_SELL_TOP_COMBINACIONES_N", "3"))

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
