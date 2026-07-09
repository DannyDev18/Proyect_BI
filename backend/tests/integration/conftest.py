# backend/tests/integration/conftest.py
"""Fixtures de integración: requieren Postgres real (postgres_edw) corriendo y
accesible en PG_HOST/PG_PORT (ver tests/conftest.py -- default localhost:5433, el
puerto expuesto por docker-compose). No usan credenciales hardcodeadas en el código:
la contraseña de los usuarios semilla viene de PYTEST_SEED_PASSWORD (ver
edw/08_seed_roles_usuarios.sql), con el mismo valor documentado ahí como default."""
import os

import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("ML_MODELS_DIR", os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))),
    "ml", "models",
))

SEED_PASSWORD = os.getenv("PYTEST_SEED_PASSWORD", "Admin2024!Seguro")

SEED_USERS = {
    "administrador": "admin@empresa.com",
    "gerencia": "gerencia@empresa.com",
    "bodega": "bodega_quito@empresa.com",
    "ventas": "ventas_gye@empresa.com",
}


@pytest.fixture(scope="session")
def client():
    from app.main import app
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="session")
def tokens(client):
    result = {}
    for role, email in SEED_USERS.items():
        r = client.post("/api/v1/auth/login", data={"username": email, "password": SEED_PASSWORD})
        if r.status_code == 200:
            result[role] = r.json()["access_token"]
    return result


@pytest.fixture
def auth_headers(tokens):
    def _headers(role: str) -> dict:
        token = tokens.get(role)
        if not token:
            pytest.skip(f"No hay token para el rol '{role}' -- ¿está sembrada la BD de prueba?")
        return {"Authorization": f"Bearer {token}"}
    return _headers
