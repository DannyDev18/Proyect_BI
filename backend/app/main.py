from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import settings
from app.api.v1.api import api_router

# Importar base con todos los modelos registrados para create_all
import app.db.base  # noqa: F401 — registra Role y User en Base.metadata
from app.db.session import Base, engine

# Crear tablas public.roles y public.usuarios si no existen
# Las tablas del esquema edw.* son gestionadas por los scripts SQL de /edw/
try:
    Base.metadata.create_all(bind=engine)
    print("✅ Tablas public.* verificadas/creadas correctamente.")
except Exception as e:
    print(f"⚠️  Error al verificar tablas: {e}")

app = FastAPI(
    title=settings.PROJECT_NAME,
    description=(
        "API para la Plataforma Inteligente de Analítica de Negocios y Predicción de Ventas. "
        "Gestiona autenticación JWT con RBAC, KPIs del Data Warehouse y modelos ML de predicción."
    ),
    version="2.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# Configuración CORS — ajustar origins en producción
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Montaje de rutas API v1
app.include_router(api_router, prefix=settings.API_V1_STR)


@app.get("/health", tags=["Sistema"])
def health_check():
    """Endpoint de salud para healthchecks de Docker y balanceadores."""
    return {"status": "ok", "version": "2.0.0", "message": "Backend API running."}


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
