# backend/app/repositories/user_repository.py
"""Acceso a datos de `public.usuarios` (ORM). Sin reglas de negocio -- eso vive en
`services/user_service.py` (hashing de contraseñas, validación de duplicados, etc.)."""
import logging

from sqlalchemy.orm import Session, joinedload

from app.models.login_intento_fallido import LoginIntentoFallido
from app.models.user import User
from app.repositories.base import BaseRepository

logger = logging.getLogger("Backend.UserRepository")


class UserRepository(BaseRepository):
    def _query_with_role(self):
        """Query base con joinedload del rol para evitar N+1 queries."""
        return self.db.query(User).options(joinedload(User.role))

    def get_by_email(self, email: str) -> User | None:
        return self._query_with_role().filter(User.email == email).first()

    def get_by_vendedor(self, id_vendedor_origen: str) -> User | None:
        return self._query_with_role().filter(User.id_vendedor_origen == id_vendedor_origen).first()

    def get_by_id(self, user_id: int) -> User | None:
        return self._query_with_role().filter(User.id == user_id).first()

    def get_all(self, skip: int = 0, limit: int = 100) -> list[User]:
        return self._query_with_role().order_by(User.id).offset(skip).limit(limit).all()

    def count(self) -> int:
        return self.db.query(User).count()

    def create(self, **fields) -> User:
        db_user = User(**fields)
        self.db.add(db_user)
        self.db.commit()
        self.db.refresh(db_user)
        return db_user

    def update(self, db_user: User, **fields) -> User:
        for field, value in fields.items():
            setattr(db_user, field, value)
        self.db.commit()
        self.db.refresh(db_user)
        return db_user

    def delete(self, db_user: User) -> None:
        self.db.delete(db_user)
        self.db.commit()

    def registrar_intento_fallido(self, email: str, ip: str | None) -> None:
        """Best-effort (Fase 2 Admin, panel de salud, docs/features/
        plan_correcciones_pendientes.md §3): un fallo al escribir esto NUNCA debe
        tumbar el login -- mismo patrón que AuditRepository.log_action."""
        try:
            self.db.add(LoginIntentoFallido(email=email, ip=ip))
            self.db.commit()
        except Exception as e:
            self.db.rollback()
            logger.error(f"Fallo al registrar intento de login fallido para email={email}: {e}")
