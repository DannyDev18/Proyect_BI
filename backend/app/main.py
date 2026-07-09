# backend/app/main.py
"""Composición de la aplicación: registra middleware, routers, el `lifespan` (carga de
modelos ML + verificación de tablas) y los exception handlers globales. Sin lógica de
negocio -- eso vive en `services/`."""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.routes.api import api_router
from app.core.config import settings, validar_configuracion
from app.core.exceptions import ConflictError, DomainError, NotFoundError, PermissionDeniedError
from app.core.logging_config import configure_logging
from app.ml.model_loader import ModelLoader
from app.services.training_service import TrainingService

# Importa base con todos los modelos registrados para create_all
import app.database.base  # noqa: F401 — registra Role, User, Goal en Base.metadata
from app.database.session import Base, engine

configure_logging()
logger = logging.getLogger("Backend.Main")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    validar_configuracion(settings)

    try:
        Base.metadata.create_all(bind=engine)
        logger.info("Tablas public.* verificadas/creadas correctamente.")
    except Exception as e:
        logger.error(f"Error al verificar tablas: {e}", exc_info=True)

    app.state.model_loader = ModelLoader(models_dir=settings.ML_MODELS_DIR)
    app.state.model_loader.load_all()
    app.state.training_service = TrainingService()

    yield
    # Shutdown: nada que liberar hoy (los .pkl no mantienen conexiones abiertas).


app = FastAPI(
    title=settings.PROJECT_NAME,
    description=(
        "API para la Plataforma Inteligente de Analítica de Negocios y Predicción de Ventas. "
        "Gestiona autenticación JWT con RBAC, KPIs del Data Warehouse y modelos ML de predicción."
    ),
    version="2.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# CORS: en producción restringir a los orígenes reales del frontend, no "*".
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router, prefix=settings.API_V1_STR)


# ── Manejo global de excepciones ──────────────────────────────────────────────
# Los servicios lanzan excepciones de dominio (app/core/exceptions.py), nunca
# HTTPException directamente -- estos handlers las traducen a respuestas HTTP.
@app.exception_handler(NotFoundError)
def handle_not_found(request: Request, exc: NotFoundError):
    return JSONResponse(status_code=404, content={"detail": str(exc)})


@app.exception_handler(ConflictError)
def handle_conflict(request: Request, exc: ConflictError):
    return JSONResponse(status_code=409, content={"detail": str(exc)})


@app.exception_handler(PermissionDeniedError)
def handle_permission_denied(request: Request, exc: PermissionDeniedError):
    return JSONResponse(status_code=403, content={"detail": str(exc)})


@app.exception_handler(DomainError)
def handle_domain_error(request: Request, exc: DomainError):
    """Catch-all de dominio para ValidationError/ModelNotLoadedError/ExternalDataError
    y cualquier subclase futura sin handler específico."""
    return JSONResponse(status_code=400, content={"detail": str(exc)})


@app.exception_handler(Exception)
def handle_unexpected(request: Request, exc: Exception):
    """Catch-all real: loguea con traceback completo y responde 500 genérico SIN
    filtrar el mensaje interno al cliente (antes `goals.py::generate_goals` exponía
    `str(e)` directamente en la respuesta HTTP)."""
    logger.exception(f"Error no manejado en {request.method} {request.url.path}")
    return JSONResponse(status_code=500, content={"detail": "Error interno del servidor."})


@app.get("/health", tags=["Sistema"])
def health_check(request: Request):
    """Endpoint de salud para healthchecks de Docker y balanceadores."""
    modelos_listos = getattr(request.app.state, "model_loader", None)
    return {
        "status": "ok",
        "version": "2.0.0",
        "message": "Backend API running.",
        "modelos_ml_listos": modelos_listos.is_ready() if modelos_listos else False,
    }


@app.get("/", tags=["Sistema"])
def read_root():
    return {
        "status": "ok",
        "message": "BI Analytics API v2.0 — Ver /docs para documentación Swagger.",
        "endpoints": {
            "auth": f"{settings.API_V1_STR}/auth",
            "users": f"{settings.API_V1_STR}/users",
            "roles": f"{settings.API_V1_STR}/roles",
            "analytics": f"{settings.API_V1_STR}/analytics",
        },
    }
