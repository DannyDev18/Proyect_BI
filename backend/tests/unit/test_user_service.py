# backend/tests/unit/test_user_service.py
"""Servicio de usuarios probado con repositorios 100% mockeados -- ningún test toca la BD."""
from unittest.mock import MagicMock

import pydantic
import pytest

from app.core.exceptions import ConflictError, NotFoundError, ValidationError
from app.schemas.user import UserCreate, UserUpdate
from app.services.user_service import UserService


@pytest.fixture
def user_repo():
    repo = MagicMock()
    repo.get_by_vendedor.return_value = None  # default: sin colisión (docs/auditoria/36)
    return repo


@pytest.fixture
def role_repo():
    return MagicMock()


@pytest.fixture
def catalog_repo():
    return MagicMock()


@pytest.fixture
def service(user_repo, role_repo, catalog_repo):
    return UserService(user_repo, role_repo, catalog_repo)


def test_create_falla_si_email_ya_existe(service, user_repo):
    user_repo.get_by_email.return_value = MagicMock()  # ya existe
    user_in = UserCreate(nombre="Juan", email="juan@empresa.com", password="Password123!", rol_id=1)

    with pytest.raises(ConflictError):
        service.create(user_in)

    user_repo.create.assert_not_called()


def test_create_falla_si_rol_no_existe(service, user_repo, role_repo):
    user_repo.get_by_email.return_value = None
    role_repo.get_by_id.return_value = None
    user_in = UserCreate(nombre="Juan", email="juan@empresa.com", password="Password123!", rol_id=999)

    with pytest.raises(NotFoundError):
        service.create(user_in)


def test_create_ok_delega_al_repositorio(service, user_repo, role_repo):
    user_repo.get_by_email.return_value = None
    role_repo.get_by_id.return_value = MagicMock(id=1)
    created = MagicMock(id=5)
    user_repo.create.return_value = created
    user_repo.get_by_id.return_value = created

    user_in = UserCreate(nombre="Juan", email="Juan@Empresa.com", password="Password123!", rol_id=1)
    result = service.create(user_in)

    assert result is created
    kwargs = user_repo.create.call_args.kwargs
    assert kwargs["email"] == "juan@empresa.com"  # normalizado a minúsculas


def test_create_ventas_falla_si_vendedor_no_existe(service, user_repo, role_repo, catalog_repo):
    user_repo.get_by_email.return_value = None
    role_repo.get_by_id.return_value = MagicMock(id=2, nombre="ventas")
    catalog_repo.get_vendedor_activo.return_value = None
    user_in = UserCreate(
        nombre="Juan", email="juan@empresa.com", password="Password123!",
        rol_id=2, id_vendedor_origen="V999",
    )

    with pytest.raises(ValidationError):
        service.create(user_in)
    user_repo.create.assert_not_called()


def test_create_ventas_falla_si_vendedor_inactivo(service, user_repo, role_repo, catalog_repo):
    user_repo.get_by_email.return_value = None
    role_repo.get_by_id.return_value = MagicMock(id=2, nombre="ventas")
    catalog_repo.get_vendedor_activo.return_value = {"codven": "V001", "activo": False}
    user_in = UserCreate(
        nombre="Juan", email="juan@empresa.com", password="Password123!",
        rol_id=2, id_vendedor_origen="V001",
    )

    with pytest.raises(ValidationError):
        service.create(user_in)


def test_create_ventas_ok_enlaza_vendedor_activo(service, user_repo, role_repo, catalog_repo):
    user_repo.get_by_email.return_value = None
    role_repo.get_by_id.return_value = MagicMock(id=2, nombre="ventas")
    catalog_repo.get_vendedor_activo.return_value = {"codven": "V001", "activo": True}
    created = MagicMock(id=5)
    user_repo.create.return_value = created
    user_repo.get_by_id.return_value = created

    user_in = UserCreate(
        nombre="Juan", email="juan@empresa.com", password="Password123!",
        rol_id=2, id_vendedor_origen="V001",
    )
    service.create(user_in)

    kwargs = user_repo.create.call_args.kwargs
    assert kwargs["id_vendedor_origen"] == "V001"
    assert kwargs["codalm"] is None


def test_create_bodega_falla_sin_almacen_ni_todos(service, user_repo, role_repo, catalog_repo):
    user_repo.get_by_email.return_value = None
    role_repo.get_by_id.return_value = MagicMock(id=4, nombre="bodega")
    user_in = UserCreate(nombre="Ana", email="ana@empresa.com", password="Password123!", rol_id=4)

    with pytest.raises(ValidationError):
        service.create(user_in)


def test_create_bodega_falla_si_almacen_no_existe(service, user_repo, role_repo, catalog_repo):
    user_repo.get_by_email.return_value = None
    role_repo.get_by_id.return_value = MagicMock(id=4, nombre="bodega")
    catalog_repo.get_almacen.return_value = None
    user_in = UserCreate(nombre="Ana", email="ana@empresa.com", password="Password123!", rol_id=4, codalm="ZZZ")

    with pytest.raises(ValidationError):
        service.create(user_in)


def test_create_bodega_ok_enlaza_almacen(service, user_repo, role_repo, catalog_repo):
    user_repo.get_by_email.return_value = None
    role_repo.get_by_id.return_value = MagicMock(id=4, nombre="bodega")
    catalog_repo.get_almacen.return_value = {"codalm": "A01", "nombre_almacen": "Bodega Central"}
    created = MagicMock(id=6)
    user_repo.create.return_value = created
    user_repo.get_by_id.return_value = created

    user_in = UserCreate(nombre="Ana", email="ana@empresa.com", password="Password123!", rol_id=4, codalm="A01")
    service.create(user_in)

    kwargs = user_repo.create.call_args.kwargs
    assert kwargs["codalm"] == "A01"
    assert kwargs["id_vendedor_origen"] is None


def test_create_bodega_ok_todos_los_almacenes(service, user_repo, role_repo, catalog_repo):
    user_repo.get_by_email.return_value = None
    role_repo.get_by_id.return_value = MagicMock(id=4, nombre="bodega")
    created = MagicMock(id=7)
    user_repo.create.return_value = created
    user_repo.get_by_id.return_value = created

    user_in = UserCreate(
        nombre="Ana", email="ana@empresa.com", password="Password123!",
        rol_id=4, todos_los_almacenes=True,
    )
    service.create(user_in)

    kwargs = user_repo.create.call_args.kwargs
    assert kwargs["codalm"] is None
    catalog_repo.get_almacen.assert_not_called()


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
        service.change_password(db_user, "wrong", "NewPassword123!")


# ── Política de contraseña unificada (docs/auditoria/36_actualizacion_modulo_admin.md, H4) ──
@pytest.mark.parametrize("password", ["short1!", "password123", "PASSWORD123!", "Password!!!!"])
def test_usercreate_rechaza_password_que_no_cumple_la_politica(password):
    with pytest.raises(pydantic.ValidationError):
        UserCreate(nombre="Juan", email="juan@empresa.com", password=password, rol_id=1)


def test_usercreate_acepta_password_que_cumple_la_politica():
    user_in = UserCreate(nombre="Juan", email="juan@empresa.com", password="Password123!", rol_id=1)
    assert user_in.password == "Password123!"


def test_userupdate_password_none_no_dispara_validacion():
    assert UserUpdate(password=None).password is None


# ── Colisión de email/vendedor en update (docs/auditoria/36_actualizacion_modulo_admin.md, H6) ──
def test_update_falla_si_email_ya_pertenece_a_otro_usuario(service, user_repo):
    db_user = MagicMock(id=1, email="juan@empresa.com", role=MagicMock(nombre="gerencia"))
    user_repo.get_by_email.return_value = MagicMock(id=2, email="otro@empresa.com")

    with pytest.raises(ConflictError):
        service.update(db_user, UserUpdate(email="otro@empresa.com"))
    user_repo.update.assert_not_called()


def test_update_permite_conservar_el_propio_email(service, user_repo):
    db_user = MagicMock(id=1, email="juan@empresa.com", role=MagicMock(nombre="gerencia"))
    user_repo.update.return_value = db_user
    user_repo.get_by_id.return_value = db_user

    service.update(db_user, UserUpdate(email="Juan@Empresa.com"))

    user_repo.get_by_email.assert_not_called()


def test_update_falla_si_vendedor_ya_enlazado_a_otro_usuario(service, user_repo):
    db_user = MagicMock(id=1, email="juan@empresa.com", role=MagicMock(nombre="ventas"))
    user_repo.get_by_vendedor.return_value = MagicMock(id=2, email="otro@empresa.com")

    with pytest.raises(ConflictError):
        service.update(db_user, UserUpdate(id_vendedor_origen="V001"))
    user_repo.update.assert_not_called()
