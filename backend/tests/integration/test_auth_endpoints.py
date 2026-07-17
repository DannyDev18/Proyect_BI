# backend/tests/integration/test_auth_endpoints.py
import pytest

from app.core.rate_limit import limiter

pytestmark = pytest.mark.integration


def test_login_con_credenciales_correctas(client):
    r = client.post("/api/v1/auth/login", data={"username": "admin@empresa.com", "password": "Admin2024!Seguro"})
    assert r.status_code == 200
    assert "access_token" in r.json()


def test_login_con_credenciales_incorrectas(client):
    r = client.post("/api/v1/auth/login", data={"username": "admin@empresa.com", "password": "incorrecta"})
    assert r.status_code == 401


def test_endpoint_protegido_sin_token_devuelve_401(client):
    r = client.get("/api/v1/users/me")
    assert r.status_code == 401


def test_me_devuelve_perfil_del_usuario_autenticado(client, auth_headers):
    r = client.get("/api/v1/users/me", headers=auth_headers("administrador"))
    assert r.status_code == 200
    assert r.json()["email"] == "admin@empresa.com"


def test_login_rate_limit_bloquea_tras_N_intentos(client):
    """S-3 (docs/features/plan_correcciones_pendientes.md): mitiga fuerza bruta contra
    /auth/login. Con AUTH_LOGIN_RATE_LIMIT="5/minute" (default), el 6to intento en la
    ventana debe devolver 429 sin importar si las credenciales son correctas."""
    limiter.reset()
    try:
        for _ in range(5):
            r = client.post(
                "/api/v1/auth/login",
                data={"username": "admin@empresa.com", "password": "incorrecta"},
            )
            assert r.status_code == 401

        r = client.post(
            "/api/v1/auth/login",
            data={"username": "admin@empresa.com", "password": "incorrecta"},
        )
        assert r.status_code == 429
    finally:
        limiter.reset()
