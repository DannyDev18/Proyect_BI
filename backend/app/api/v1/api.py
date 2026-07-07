# backend/app/api/v1/api.py
from fastapi import APIRouter
from app.api.v1.endpoints import auth, users, analytics, admin_mlops, roles, goals

api_router = APIRouter()

api_router.include_router(auth.router,       prefix="/auth",          tags=["🔐 Autenticación"])
api_router.include_router(users.router,      prefix="/users",         tags=["👥 Usuarios (CRUD)"])
api_router.include_router(roles.router,      prefix="/roles",         tags=["🏷️ Roles"])
api_router.include_router(analytics.router,  prefix="/analytics",     tags=["📊 Analytics & KPIs"])
api_router.include_router(admin_mlops.router, prefix="/admin/modelos", tags=["🤖 MLOps Admin"])
api_router.include_router(goals.router,      prefix="/gerencia/goals", tags=["🎯 Metas y Comisiones"])
