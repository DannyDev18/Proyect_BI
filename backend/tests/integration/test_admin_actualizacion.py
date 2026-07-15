# backend/tests/integration/test_admin_actualizacion.py
"""Fase 1 de docs/features/plan_actualizacion_modulo_admin.md (ver auditoría
docs/auditoria/36_actualizacion_modulo_admin.md): filtros/paginación de audit-logs,
política de contraseña por API directa, colisión de email en update de usuario y RBAC
`admin_only`. Requiere Postgres real (ver tests/integration/conftest.py)."""
import uuid

import pytest

pytestmark = pytest.mark.integration


# ── H2: audit-logs con filtros + paginación ─────────────────────────────────
def test_audit_logs_devuelve_pagina_tipada(client, auth_headers):
    r = client.get("/api/v1/analytics/admin/audit-logs", headers=auth_headers("administrador"))
    assert r.status_code == 200
    body = r.json()
    assert set(body.keys()) >= {"items", "total", "page", "page_size", "total_pages"}


def test_audit_logs_acepta_filtros_de_fecha_y_modulo(client, auth_headers):
    r = client.get(
        "/api/v1/analytics/admin/audit-logs",
        params={"fecha_desde": "2020-01-01", "fecha_hasta": "2026-12-31", "modulo": "analytics", "page_size": 10},
        headers=auth_headers("administrador"),
    )
    assert r.status_code == 200
    assert r.json()["page_size"] == 10


def test_audit_logs_rechaza_roles_no_admin(client, auth_headers):
    r = client.get("/api/v1/analytics/admin/audit-logs", headers=auth_headers("ventas"))
    assert r.status_code == 403


# ── H4: política de contraseña enforced en backend, no solo en el pattern del frontend ──
def test_crear_usuario_con_password_debil_es_rechazado_por_api(client, auth_headers):
    r = client.post(
        "/api/v1/users/",
        json={
            "nombre": "Test Password Débil", "email": "debil_test@empresa.com",
            "password": "password123", "rol_id": 3,
        },
        headers=auth_headers("administrador"),
    )
    assert r.status_code == 422


def test_crear_usuario_con_password_conforme_es_aceptado_y_se_limpia(client, auth_headers):
    # Email único por corrida: DELETE /users/{id} es soft-delete (es_activo=False, no
    # borra la fila -- users.py:92-107), así que un email fijo reutilizado entre
    # corridas de la suite colisiona consigo mismo (UNIQUE) en la siguiente ejecución.
    email = f"fuerte_test_{uuid.uuid4().hex[:8]}@empresa.com"
    r = client.post(
        "/api/v1/users/",
        json={
            "nombre": "Test Password Fuerte", "email": email,
            "password": "Password123!", "rol_id": 1,  # gerencia: sin enlace EDW obligatorio
        },
        headers=auth_headers("administrador"),
    )
    assert r.status_code == 201
    user_id = r.json()["id"]
    client.delete(f"/api/v1/users/{user_id}", headers=auth_headers("administrador"))


# ── H6: colisión de email en update ─────────────────────────────────────────
def test_actualizar_usuario_con_email_de_otro_usuario_devuelve_error_de_negocio(client, auth_headers):
    r = client.put(
        "/api/v1/users/1",
        json={"email": "gerencia@empresa.com"},
        headers=auth_headers("administrador"),
    )
    assert r.status_code in (400, 409)
    assert r.status_code != 500
