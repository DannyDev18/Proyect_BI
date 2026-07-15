# backend/app/services/notification_service.py
"""Orquestador del módulo de Notificaciones (docs/features/plan_modulo_notificaciones.md,
docs/auditoria/31_modulo_notificaciones.md, reglas RN-N1..RN-N4). Une notificaciones
**calculadas** (al vuelo, sin persistencia -- reutiliza generadores existentes por rol)
con **persistidas** (eventos puntuales con estado de lectura, tabla `public.notificaciones`).

Cada generador calculado corre envuelto en try/except + logger.error + lista vacía
(RN-N4, mismo patrón de degradación con gracia de `prediction_service.py`): un generador
caído no debe tumbar el resto de la campana."""
import logging
from typing import Any, Callable

from app.core.config import settings
from app.core.exceptions import NotFoundError, PermissionDeniedError
from app.models.notification import Notification
from app.models.user import User
from app.repositories.notification_repository import NotificationRepository
from app.schemas.notification import NotificacionOut
from app.schemas.pagination import Page, PaginationParams, paginar
from app.services.cartera360_service import Cartera360Service
from app.services.prediction_service import PredictionService
from app.services.warehouse_service import WarehouseService

logger = logging.getLogger(__name__)

_TITULOS_BODEGA = {
    "stock_critico": "Stock crítico",
    "stock_critico_resumen": "Stock crítico (resumen)",
    "prediccion_agotamiento": "Agotamiento proyectado",
    "transferencia_sugerida": "Transferencia sugerida",
    "reporte_semanal": "Reporte de compras disponible",
}


class NotificationService:
    def __init__(
        self,
        notification_repo: NotificationRepository,
        warehouse_service: WarehouseService,
        prediction_service: PredictionService,
        cartera360_service: Cartera360Service,
    ):
        self.repo = notification_repo
        self.warehouse_service = warehouse_service
        self.prediction_service = prediction_service
        self.cartera360_service = cartera360_service

    # ── Orquestación: calculadas + persistidas por rol ──────────────────────
    def get_notificaciones(self, user: User) -> list[NotificacionOut]:
        rol = user.role.nombre if user.role else None
        calculadas = self._generar_calculadas(rol, user)
        persistidas = self._listar_persistidas(rol, user)
        return calculadas + persistidas

    def _generar_calculadas(self, rol: str | None, user: User) -> list[NotificacionOut]:
        generadores: dict[str, Callable[[User], list[dict[str, Any]]]] = {
            "bodega": self._generar_bodega,
            "administrador": self._generar_salud_modelos,
            "gerencia": self._generar_gerencia,
            "ventas": self._generar_ventas,
        }
        generador = generadores.get(rol)
        if generador is None:
            return []
        try:
            crudas = generador(user)
        except Exception as e:
            logger.error(f"Fallo generador de notificaciones calculadas (rol={rol}): {e}")
            return []
        return [
            NotificacionOut(
                tipo_evento=d["tipo_evento"], titulo=d["titulo"], mensaje=d["mensaje"],
                accion_url=d.get("accion_url"), prioridad=d["prioridad"],
                leida=False, persistida=False,
            )
            for d in crudas[: settings.NOTIF_MAX_POR_TIPO * 4]
        ]

    def _generar_bodega(self, user: User) -> list[dict[str, Any]]:
        almacen = None if user.role and user.role.nombre in ("administrador", "gerencia") else user.codalm
        crudos = self.warehouse_service.get_notificaciones(sucursal=user.sucursal, almacen=almacen)
        return [
            {
                "tipo_evento": d["tipo"],
                "titulo": _TITULOS_BODEGA.get(d["tipo"], d["tipo"]),
                "mensaje": d["mensaje"],
                "accion_url": d.get("accion_url"),
                "prioridad": d["prioridad"],
            }
            for d in crudos
        ]

    def _generar_salud_modelos(self, user: User) -> list[dict[str, Any]]:
        model_loader = self.warehouse_service.model_loader
        faltantes = [key for key in model_loader.keys() if not model_loader.is_loaded(key)]
        if not faltantes:
            return []
        return [{
            "tipo_evento": "modelo_no_cargado",
            "titulo": "Modelo ML no cargado",
            "mensaje": f"⚠️ {len(faltantes)} modelo(s) no están cargados: {', '.join(faltantes)}.",
            "accion_url": "/admin",
            "prioridad": "alta",
        }]

    def _generar_gerencia(self, user: User) -> list[dict[str, Any]]:
        """Desvío del forecast semanal (Fase 4 del plan): `PredictionService.get_sales_forecast`
        ya expone `metricas.crecimiento_esperado` (% de la venta proyectada vs. el mismo
        número de días recientes, `_build_forecast_metrics`) -- no existe hoy un backtest
        real vs. predicho por período, así que se usa esta señal ya calculada (honesta,
        no inventada, H31-3) como proxy de "desvío" contra la tendencia reciente."""
        forecast = self.prediction_service.get_sales_forecast(granularidad="semana")
        crecimiento = forecast.get("metricas", {}).get("crecimiento_esperado")
        if crecimiento is None or abs(crecimiento) < settings.NOTIF_DESVIO_FORECAST_PCT:
            return []
        direccion = "por encima" if crecimiento > 0 else "por debajo"
        return [{
            "tipo_evento": "desvio_forecast",
            "titulo": "Desvío del forecast semanal",
            "mensaje": (
                f"📈 La proyección de ventas de la próxima semana está {abs(crecimiento):.1f}% "
                f"{direccion} de la tendencia reciente."
            ),
            "accion_url": "/gerencia",
            "prioridad": "alta" if abs(crecimiento) >= settings.NOTIF_DESVIO_FORECAST_PCT * 2 else "media",
        }]

    def _generar_ventas(self, user: User) -> list[dict[str, Any]]:
        """Clientes propios con churn alto (Fase 4 del plan): reutiliza
        `Cartera360Service.get_lista_trabajo` (docs/auditoria/32_modulo_ventas_cartera_360.md),
        que ya resuelve el RLS por `codven` (RN-V3) y el churn real en un solo lote --
        no se reimplementa el two-stage shortlist+churn aquí (H31-3: sin duplicar trabajo)."""
        if not user.id_vendedor_origen:
            return []
        umbral_pct = settings.NOTIF_CHURN_UMBRAL * 100
        cartera = self.cartera360_service.get_lista_trabajo(user.id_vendedor_origen)
        en_riesgo = [c for c in cartera if c.get("probabilidad_abandono", 0.0) >= umbral_pct]
        return [
            {
                "tipo_evento": "churn_alto",
                "titulo": "Cliente en riesgo de abandono",
                "mensaje": (
                    f"⚠️ El cliente {c['cliente_id']} tiene {c['probabilidad_abandono']:.0f}% "
                    f"de probabilidad de abandono."
                ),
                "accion_url": "/ventas/cartera360",
                "prioridad": "alta",
            }
            for c in en_riesgo[: settings.NOTIF_MAX_POR_TIPO]
        ]

    # ── Persistidas: lectura, emisión, dedupe ────────────────────────────────
    def _listar_persistidas(self, rol: str | None, user: User) -> list[NotificacionOut]:
        if rol is None:
            return []
        activas = self.repo.get_activas_por_rol(rol, user.id)
        return [self._a_schema(n, user.id) for n in activas]

    def emitir(
        self, tipo_evento: str, rol_destino: str, titulo: str, mensaje: str, prioridad: str = "media",
        accion_url: str | None = None, contexto: dict | None = None, usuario_id: int | None = None,
    ) -> Notification | None:
        """Punto único de emisión persistida (RN-N2). Devuelve None si se descartó por
        dedupe (mismo tipo_evento/rol_destino/contexto dentro de NOTIF_DEDUPE_HORAS)."""
        try:
            if self.repo.existe_duplicado_reciente(tipo_evento, rol_destino, contexto, settings.NOTIF_DEDUPE_HORAS):
                return None
            return self.repo.crear(
                tipo_evento=tipo_evento, rol_destino=rol_destino, titulo=titulo, mensaje=mensaje,
                prioridad=prioridad, accion_url=accion_url, contexto=contexto, usuario_id=usuario_id,
            )
        except Exception as e:
            logger.error(f"Fallo al emitir notificación persistida (tipo_evento={tipo_evento}): {e}")
            return None

    def marcar_leida(self, user: User, notif_id: int) -> Notification:
        notif = self.repo.get_by_id(notif_id)
        if notif is None:
            raise NotFoundError(f"Notificación {notif_id} no existe.")
        rol = user.role.nombre if user.role else None
        if notif.rol_destino != rol or (notif.usuario_id is not None and notif.usuario_id != user.id):
            raise PermissionDeniedError("No puede marcar como leída una notificación fuera de su alcance.")
        return self.repo.marcar_leida(notif, user.id)

    def marcar_todas(self, user: User) -> int:
        rol = user.role.nombre if user.role else None
        if rol is None:
            return 0
        return self.repo.marcar_todas_leidas(rol, user.id)

    def get_historial(self, user: User, pagination: PaginationParams) -> Page[NotificacionOut]:
        rol = user.role.nombre if user.role else None
        if rol is None:
            return paginar([], pagination)
        historial = self.repo.get_historial_por_rol(rol, user.id)
        items = [self._a_schema(n, user.id) for n in historial]
        return paginar(items, pagination)

    @staticmethod
    def _a_schema(notif: Notification, usuario_id: int) -> NotificacionOut:
        return NotificacionOut(
            id=notif.id, tipo_evento=notif.tipo_evento, titulo=notif.titulo, mensaje=notif.mensaje,
            accion_url=notif.accion_url, prioridad=notif.prioridad, fecha_creacion=notif.fecha_creacion,
            leida=usuario_id in (notif.leida_por or []), persistida=True,
        )
