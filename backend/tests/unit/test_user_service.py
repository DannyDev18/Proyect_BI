# backend/tests/unit/test_user_service.py
"""Servicio de usuarios probado con repositorios 100% mockeados -- ningún test toca la BD."""
from unittest.mock import MagicMock

import pytest

from app.core.exceptions import ConflictError, NotFoundError, ValidationError
from app.schemas.user import UserCreate
from app.services.user_service import UserService


@pytest.fixture
def user_repo():
    return MagicMock()


@pytest.fixture
def role_repo():
    return MagicMock()


@pytest.fixture
def service(user_repo, role_repo):
    return UserService(user_repo, role_repo)


def test_create_falla_si_email_ya_existe(service, user_repo):
    user_repo.get_by_email.return_value = MagicMock()  # ya existe
    user_in = UserCreate(nombre="Juan", email="juan@empresa.com", password="password123", rol_id=1)

    with pytest.raises(ConflictError):
        service.create(user_in)

    user_repo.create.assert_not_called()


def test_create_falla_si_rol_no_existe(service, user_repo, role_repo):
    user_repo.get_by_email.return_value = None
    role_repo.get_by_id.return_value = None
    user_in = UserCreate(nombre="Juan", email="juan@empresa.com", password="password123", rol_id=999)

    with pytest.raises(NotFoundError):
        service.create(user_in)


def test_create_ok_delega_al_repositorio(service, user_repo, role_repo):
    user_repo.get_by_email.return_value = None
    role_repo.get_by_id.return_value = MagicMock(id=1)
    created = MagicMock(id=5)
    user_repo.create.return_value = created
    user_repo.get_by_id.return_value = created

    user_in = UserCreate(nombre="Juan", email="Juan@Empresa.com", password="password123", rol_id=1)
    result = service.create(user_in)

    assert result is created
    kwargs = user_repo.create.call_args.kwargs
    assert kwargs["email"] == "juan@empresa.com"  # normalizado a minúsculas


def test_deactivate_falla_si_ya_esta_desactivado(service, user_repo):
    db_user = MagicMock(es_activo=False)
    with pytest.raises(ValidationError):
        service.deactivate(db_user)
    user_repo.update.assert_not_called()


def test_change_password_falla_si_password_actual_incorrecta(service, monkeypatch):
    from app.services import user_service as mod
    monkeypatch.setattr(mod, "verify_password", lambda plain, hashed: False)
    db_user = MagicMock(hashed_password="hash")

    with pytest.raises(ValidationError):
        service.change_password(db_user, "wrong", "newpassword123")
