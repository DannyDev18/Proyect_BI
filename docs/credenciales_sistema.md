# Credenciales y Roles del Sistema (Guía de Pruebas)

Esta guía provee las credenciales sembradas nativamente en la base de datos (mediante scripts idempotentes en el ETL de inicialización) para probar todos los flujos autorizados del sistema.

> [!CAUTION]
> **Modo Pruebas / Desarrollo:** Para todas las cuentas detalladas a continuación, la contraseña unificada estandarizada es:
> **`Admin2024!Seguro`**
>
> _(Nota de seguridad: Esta clave se halla matemáticamente hasheada en la base de datos a través de bcrypt iterado `$2b$12$`). En ambientes de producción, se sugiere forzar el cambio en el primer inicio de sesión._

---

## 1. Perfil: Administrador 🛡️

> Supervisor e Integrador del Sistema Total

- **Email Autenticador:** `admin@empresa.com`
- **Contraseña:** `Admin2024!Seguro`
- **Sucursal:** N/A (Global)
- **Permisos de Pantalla (Rutas Accesibles):**
  - `/admin` (Auditoría de Anomalías de Isolation Forest, Logs).
  - `/users` (Panel global de Control de Acceso CRUD de Empleados).
  - `/gerencia`, `/bodega`, `/ventas` (Observación global delegada).
- **Nivel de Control C.R.U.D:** Absoluto. Único perfil autorizado a modificar o desactivar identidades y configuraciones operativas del Backend.

## 2. Perfil: Gerencia 📊

> Visión Ejecutiva Superior Analítica

- **Email Autenticador:** `gerencia@empresa.com`
- **Contraseña:** `Admin2024!Seguro`
- **Sucursal:** N/A (Global)
- **Permisos de Pantalla (Rutas Accesibles):**
  - `/gerencia` (Predicciones Estadísticas de Volúmenes por Random Forest).
  - `/bodega`, `/ventas` (KPIs Directos).
- **Restricciones Exclusivas (Seguridad UI/UX):** La aplicación no filtra la analítica a una sucursal en específico, sin embargo, los botones transaccionales (como "Solicitar Traspaso") son deshabilitados nativamente. Además, recibe un bloqueo explícito (`HTTP 403 Forbidden` / `<AccessDenied>`) hacia módulos administrativos.

## 3. Perfil: Bodega / Almacén Central 📦

> Jefe de Operaciones Logísticas Focalizadas

- **Email Autenticador:** `bodega_quito@empresa.com`
- **Contraseña:** `Admin2024!Seguro`
- **Sucursal Parametrizada:** "Matriz Quito" (Las tablas se filtrarán según la disponibilidad en su centro físico)
- **Permisos de Pantalla (Rutas Accesibles):**
  - `/bodega` (Dashboard de control).
- **Características Técnicas y Modelos (ML):** Activa notificaciones sobre "Puntos de Críticos de Rotación" impulsados por estimaciones de Time Series de demanda diaria.

## 4. Perfil: Comercial / Ventas 🎯

> Fuerza Comercial Desplegada Sectorizada

- **Email Autenticador:** `ventas_gye@empresa.com`
- **Contraseña:** `eno`
- **Sucursal Parametrizada:** "Sucursal Guayaquil"
- **Codven SAP Emulado:** ID=`102` (Vincula este hash analítico a su billetera de comisiones).
- **Permisos de Pantalla (Rutas Accesibles):**
  - `/ventas` (Panel comercial).
- **Características Técnicas y Modelos (ML):** Expone motores de recomendación K-Means de perfilado (Segmentación VIP vs Críticos), probabilidad de "Churn Rate" del cliente consultado al instante y Reglas de Asociación de Apriori (Cross-Selling de caja).

---

> [!TIP]
> **Modificando Registros Semilla:** Todos los insertos de esta lista son resguardados por lógica `ON CONFLICT (email) DO NOTHING`. Puede regenerar la DB con `docker-compose down -v && docker-compose up db -d` sin temor a duplicidad de IDs, garantizando que este registro de roles sea la fuente eterna de la verdad.
