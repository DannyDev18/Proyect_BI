# backend/app/repositories/notification_repository.py
"""Persistencia del módulo de Notificaciones (docs/auditoria/31_modulo_notificaciones.md,
RN-N1..RN-N4). Solo cubre notificaciones PERSISTIDAS -- las calculadas al vuelo (Bodega,
forecast, churn) nunca pasan por aquí, viven en `notification_service.py`."""
import datetime

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.models.notification import Notification


class NotificationRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_activas_por_rol(
        self, rol_destino: str, usuario_id: int, ahora: datetime.datetime | None = None,
    ) -> list[Notification]:
        """Notificaciones persistidas vigentes (no expiradas) del rol, dirigidas a todo
        el rol (usuario_id NULL) o a este usuario puntualmente. No filtra por leídas --
        el service decide `leida` por usuario a partir de `leida_por` (RN-N3)."""
        ahora = ahora or datetime.datetime.now(datetime.timezone.utc)
        return (
            self.db.query(Notification)
            .filter(
                Notification.rol_destino == rol_destino,
                or_(Notification.usuario_id.is_(None), Notification.usuario_id == usuario_id),
                or_(Notification.fecha_expira.is_(None), Notification.fecha_expira > ahora),
            )
            .order_by(Notification.fecha_creacion.desc())
            .all()
        )

    def get_historial_por_rol(self, rol_destino: str, usuario_id: int) -> list[Notification]:
        """Todo el historial persistido del rol/usuario, incluyendo expiradas y leídas
        (para `GET /notificaciones/historial`, paginado en el service)."""
        return (
            self.db.query(Notification)
            .filter(
                Notification.rol_destino == rol_destino,
                or_(Notification.usuario_id.is_(None), Notification.usuario_id == usuario_id),
            )
            .order_by(Notification.fecha_creacion.desc())
            .all()
        )

    def existe_duplicado_reciente(
        self, tipo_evento: str, rol_destino: str, contexto: dict | None, horas: int,
    ) -> bool:
        """Dedupe RN-N2: mismo `(tipo_evento, rol_destino, contexto)` emitido dentro de
        la ventana de `horas` no se vuelve a insertar. Compara el JSONB completo -- basta
        para el volumen esperado (eventos puntuales, no un log de alto volumen, H31-6)."""
        desde = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=horas)
        query = self.db.query(Notification).filter(
            Notification.tipo_evento == tipo_evento,
            Notification.rol_destino == rol_destino,
            Notification.fecha_creacion >= desde,
        )
        if contexto is not None:
            query = query.filter(Notification.contexto == contexto)
        return self.db.query(query.exists()).scalar()

    def get_by_id(self, notif_id: int) -> Notification | None:
        return self.db.query(Notification).filter(Notification.id == notif_id).first()

    def crear(
        self, tipo_evento: str, rol_destino: str, titulo: str, mensaje: str, prioridad: str,
        accion_url: str | None = None, contexto: dict | None = None, usuario_id: int | None = None,
        fecha_expira: datetime.datetime | None = None,
    ) -> Notification:
        notif = Notification(
            tipo_evento=tipo_evento, rol_destino=rol_destino, usuario_id=usuario_id,
            titulo=titulo, mensaje=mensaje, accion_url=accion_url, prioridad=prioridad,
            contexto=contexto, leida_por=[], fecha_expira=fecha_expira,
        )
        self.db.add(notif)
        self.db.commit()
        self.db.refresh(notif)
        return notif

    def marcar_leida(self, notif: Notification, usuario_id: int) -> Notification:
        """Agrega `usuario_id` a `leida_por` sin duplicar (RN-N3). Reasigna la lista
        completa -- SQLAlchemy no detecta mutaciones in-place sobre columnas JSONB."""
        leida_por = list(notif.leida_por or [])
        if usuario_id not in leida_por:
            leida_por.append(usuario_id)
            notif.leida_por = leida_por
            self.db.add(notif)
            self.db.commit()
            self.db.refresh(notif)
        return notif

    def marcar_todas_leidas(self, rol_destino: str, usuario_id: int) -> int:
        activas = self.get_activas_por_rol(rol_destino, usuario_id)
        marcadas = 0
        for notif in activas:
            leida_por = list(notif.leida_por or [])
            if usuario_id not in leida_por:
                leida_por.append(usuario_id)
                notif.leida_por = leida_por
                self.db.add(notif)
                marcadas += 1
        if marcadas:
            self.db.commit()
        return marcadas
