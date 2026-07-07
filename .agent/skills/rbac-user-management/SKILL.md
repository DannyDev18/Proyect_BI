---
name: rbac-user-management
description: Implementing User Management & Role-Based Access Control (RBAC) securely on Backend (FastAPI scopes/dependencies) and Frontend (React route guards/conditional rendering) matching the defined project roles.
risk: unknown
source: community
date_added: "2026-07-02"
---

## Use this skill when

- Designing or implementing User authentication and authorization models.
- Implementing Role-Based Access Control (RBAC) or Attribute-Based Access Control (ABAC).
- Creating FastAPI dependencies for checking user roles/scopes (`backend/app/core/dependencies.py`).
- Creating protected routes, menus, or conditionally rendering UI elements on the React frontend based on permissions.

## Do not use this skill when

- The task is unrelated to user roles, permissions, or access control.
- Implementing server-level firewall or low-level docker network isolation.

---

## Instructions

- Clearly define user roles, resource scopes, and hierarchical inheritance model.
- Restrict endpoints using dependency-injection checks on the backend (fail securely by default).
- Ensure client-side route-guards sync with backend token claims to prevent layout bypasses.
- Proactively write audit logs on permission failures.

---

## Capabilities & Architecture

### 1. Modelos de Roles del Proyecto (Tesis Analítica Comercial)

De acuerdo con la propuesta de tesis (`docs/propuesta_tesis.md`), la plataforma protege la información y personaliza los dashboards de la interfaz según los siguientes cuatro roles funcionales:

- **Administrador (admin / administrador):**
  - **Ámbito:** Visión global del sistema, gestión técnica y mantenimiento.
  - **Casos de uso clave:** Auditoría de actividad de los usuarios, detección de anomalías operativas y de datos, visualización y descarga de logs de la plataforma.
- **Gerente (gerente):**
  - **Ámbito:** Análisis estratégico y desempeño general de la empresa.
  - **Casos de uso clave:** visualización de KPIs de ingresos totales, comparación de rendimiento inter-sucursal, análisis de rentabilidad agregada, índice de salud comercial y predicción de ventas mensuales.
- **Bodega (bodega / bodeguero):**
  - **Ámbito:** Logística, inventario e insumos.
  - **Casos de uso clave:** Monitoreo de stock actual, reportes de riesgo de desabastecimiento, predicción de demanda de artículos y recomendaciones inteligentes de reposición / transferencias entre sucursales.
- **Ventas (ventas / vendedor):**
  - **Ámbito:** Gestión y seguimiento puramente comercial.
  - **Casos de uso clave:** Cumplimiento y predicción de metas comerciales, reportes de segmentación de clientes, predicción/tasa de abandono (churn probability) de clientes y recomendaciones de productos cruzados.

### 2. Control de Acceso en Backend (FastAPI RBAC)

- **Decoupled Dependency Injection:** Utilizar middlewares o dependencias parametrizadas en FastAPI para proteger recursos. Solo el rol `admin` puede llamar endpoints del sistema o inicializadores ETL.

```python
# Ejemplo de verificación de permisos en backend/app/core/dependencies.py
from fastapi import HTTPException, Depends, status
from app.core.security import get_current_user
from app.models.usuario import Usuario

class PermissionChecker:
    def __init__(self, allowed_roles: list[str]):
        self.allowed_roles = allowed_roles

    def __call__(self, current_user: Usuario = Depends(get_current_user)):
        if current_user.rol not in self.allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Acceso denegado. Privilegios insuficientes para el rol asignado."
            )
        return current_user
```

- **Aplicación en Controladores:**
  - Filtros de auditoría / logs: `Depends(PermissionChecker(["admin"]))`
  - Endpoints de predicción/análisis de ventas: `Depends(PermissionChecker(["admin", "gerente", "ventas"]))`
  - Consultas de stock/reposición: `Depends(PermissionChecker(["admin", "gerente", "bodega"]))`

### 3. Control de Acceso en Frontend (React Guards)

- **Filtro por Rol en Vistas:** Renderizado condicional del menú lateral (Sidebar Navigation) para ocultar las pestañas de "Inventario Crítico" a Ventas o "Metas Comerciales" a Bodega.
  ```tsx
  // Condicionando visibilidad de menús en el Frontend
  <Authorize allowedRoles={["admin", "gerente", "bodega"]}>
    <SidebarItem label="Inventario y Reposición" path="/inventario" />
  </Authorize>
  ```
- **Rutas Protegidas:** Utilizar componentes de ruta superior (ej: `<ProtectedRoute allowedRoles={['admin', 'gerente']}>`) para interceptar la navegación no autorizada a nivel de cliente.

### 4. Seguridad de Datos a nivel de Fila (Multi-tenancy)

- Para usuarios con rol `gerente` asignados a una sucursal específica, la API backend debe filtrar semánticamente los datos adjuntando cláusulas `f.sucursal_sk = :sucursal` automáticas basadas en la cuenta asociada.

### 5. Auditoría y Registro (Audit Logging)

- Toda excepción HTTP 403 Forbidden interceptada debe loggearse con severidad WARNING, persistiendo el ID de usuario, la IP remota, el endpoint bloqueado y la fecha/hora.

---

## Behavior & Best Practices

- **Fail-Secure por defecto:** Si una ruta no tiene restricciones configuradas explícitamente, bloquea el paso o requiere rol de `admin`.
- **Validación Backend Primaria:** Las dependencias del backend representan el único origen de la verdad; nunca confíes ciegamente en ocultar elementos visuales en el front.
- **Limpieza de Tokens (Logout):** Destruir la cookie del token o vaciar el Storage tras el cierre de sesión inmediatamente.
