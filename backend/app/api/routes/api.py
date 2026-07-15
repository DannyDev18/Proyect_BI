# backend/app/api/routes/api.py
from fastapi import APIRouter

from app.api.routes import admin, admin_ml, analytics, auth, cartera360, goals, notifications, roles, sales, system, users, warehouse

api_router = APIRouter()

api_router.include_router(auth.router, prefix="/auth", tags=["🔐 Autenticación"])
api_router.include_router(users.router, prefix="/users", tags=["👥 Usuarios (CRUD)"])
api_router.include_router(roles.router, prefix="/roles", tags=["🏷️ Roles"])
api_router.include_router(analytics.router, prefix="/analytics", tags=["📊 Analytics & KPIs (Gerencia)"])
api_router.include_router(warehouse.router, prefix="/analytics/bodega", tags=["📦 Analytics (Bodega)"])
api_router.include_router(sales.router, prefix="/analytics/ventas", tags=["🛒 Analytics (Ventas)"])
api_router.include_router(cartera360.router, prefix="/analytics/ventas/cartera360", tags=["📇 Analytics (Ventas · Cartera 360)"])
api_router.include_router(admin.router, prefix="/analytics/admin", tags=["🛡️ Analytics (Admin/Fraude)"])
api_router.include_router(admin_ml.router, prefix="/admin/modelos", tags=["🤖 MLOps Admin"])
api_router.include_router(goals.router, prefix="/gerencia/goals", tags=["🎯 Metas y Comisiones"])
api_router.include_router(notifications.router, prefix="/notificaciones", tags=["🔔 Notificaciones"])
api_router.include_router(system.router, prefix="/system", tags=["🩺 Sistema"])
