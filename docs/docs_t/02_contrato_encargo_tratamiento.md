# CONTRATO DE ENCARGO DE TRATAMIENTO DE DATOS PERSONALES (LOPDP)

Conste por el presente documento el **Contrato de Encargo del Tratamiento de Datos Personales** (en adelante, el "Contrato de Encargo"), suscrito al 6 de Julio de 2026 de conformidad con el artículo 41 y siguientes de la **Ley Orgánica de Protección de Datos Personales (LOPDP)** de la República del Ecuador:

## 1. OBJETO Y ALCANCE DEL ENCARGO

El presente Contrato tiene por objeto regular las condiciones bajo las cuales el **Encargado** (el Desarrollador) realizará el tratamiento de datos personales de los clientes de los cuales el **Responsable** (la Empresa) es legítimo custodio.
El tratamiento comprende exclusivamente los siguientes procesos en el monorepo Docker:

- Extracción incremental de datos transaccionales desde el ERP origen SAP SQL Anywhere (campos maestros `codcli`, `ruc_cedula` y `nombre_cliente`).
- Seudonimización criptográfica inmediata en memoria utilizando algoritmos SHA-256 integrados en el pipeline ETL (`etl/orchestrator.py`) empleando una clave de sal `PII_SALT`.
- Carga de datos anonimizados en la tabla de dimensión del Data Warehouse (`edw.dim_cliente`) relacionándolo únicamente con las facturas históricas cruzadas en `edw.fact_ventas_detail`.
- Registro seguro de la correspondencia real en la tabla aislada `public.cliente_lookup` con restricción de consultas externas.

---

## 2. DECLARACIÓN DE LICITUD Y GARANTÍA DEL RESPONSABLE (CLÁUSULA DE EXENCIÓN)

1.  **Garantía de Consentimiento:** El Responsable (la Empresa) declara bajo juramento que los identificadores de clientes (`ruc_cedula`) y de vendedores administradores fueron obtenidos bajo las bases de licitud previstas en el Art. 7 de la LOPDP y con el consentimiento de sus titulares.
2.  **Exención de Responsabilidad:** El Encargado queda exento de toda responsabilidad por multas, sanciones administrativas o reclamos directos interpuestos por la Superintendencia de Protección de Datos en caso de que la Empresa no cuente con las autorizaciones legales vigentes para el tratamiento de su base transaccional original.

---

## 3. INSTRUCCIONES DE TRATAMIENTO

El Encargado se obliga expresamente a:

1.  No procesar la información sensible para fines ajenos al entrenamiento, evaluación e inferencia de los modelos de Machine Learning (tales como predicción de abandono comercial, predicción de ventas o segmentación analítica).
2.  Mantener desacoplado el almacenamiento físico del DW utilizando dos esquemas de datos: el esquema analítico `edw` (del cual se eliminaron las columnas legibles de clientes en `02_dimensiones.sql`) y el esquema operativo `public`.

---

## 4. MEDIDAS DE SEGURIDAD TÉCNICAS E INFRAESTRUCTURA

Se implementan y auditan las siguientes medidas de control técnico dentro de la infraestructura Docker-Compose:

- **Seudonimización en Memoria:** Empleo del protocolo de hashing con sal criptográfica `PII_SALT` para que los nombres reales no se almacenen nunca de forma legible en `edw.dim_cliente`.
- **Autenticación Stateless:** Control de sesiones de usuario mediante JSON Web Tokens (JWT) firmados con algoritmo HS256.
- **Control de Acceso Basado en Roles (RBAC):** Inyección de decoradores de permisos en FastAPI (`PermissionChecker`) para restringir las llamadas a los endpoints de desanonimización (`/ventas/recommendations`, `/ventas/churn-risk`) limitándolos únicamente a los perfiles `administrador` o `gerencia`.

---

## 5. DESTINO Y DESTRUCCIÓN DE LOS DATOS AL FINALIZAR EL ENCARGO

Una vez aprobado el proyecto de titulación y entregado el sistema, el Encargado se compromete a:

1.  Dejar de usar las credenciales de lectura del motor transaccional SQL Anywhere.
2.  Eliminar de su equipo de desarrollo personal cualquier volcado de base de datos SQL (`.sql` o `.backup`) que contenga registros reales de clientes o facturas legibles.
3.  Conservar únicamente las imágenes base de Docker y los códigos fuente desarrollados utilizando conjuntos de datos de prueba sintéticos/ficticios creados para fines de investigación académica.

---

## 6. DECLARACIÓN DE LOPDP Y FIRMAS

Las partes se someten a los juzgados de la ciudad de Quito y la Superintendencia de Protección de Datos Personales del Ecuador, firmando al pie.

```
__________________________________             __________________________________
Representante de la Empresa                    Encargado del Tratamiento
Responsable del Tratamiento                    C.C. 1729XXXXXX
```
