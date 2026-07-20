# ANEXOS

> **Estado: borrador incompleto — falta profundizar.** Este archivo replica en Markdown el contenido ya redactado en `docs/tesis/latex/anexos/anexos.tex` (el entregable oficial, ver §Documento entregable de `docs/tesis/memoria_tesis.md`). Se mantiene como fuente de trabajo editable; cualquier cambio de fondo debe reflejarse en ambos lugares hasta que se automatice la conversión.

## Anexo A. Glosario de términos técnicos

| Término | Definición |
|---|---|
| API | Interfaz de Programación de Aplicaciones; en este proyecto, el conjunto de rutas HTTP expuestas por el backend FastAPI. |
| Constelación de hechos | Modelo dimensional con múltiples tablas de hechos que comparten dimensiones conformadas. |
| Dimensión conformada | Dimensión con significado y estructura consistente, reutilizable entre distintos procesos de negocio. |
| EDW | *Enterprise Data Warehouse*, Almacén de Datos Empresarial; en este documento, sinónimo del Data Warehouse del proyecto. |
| ETL | *Extract, Transform, Load*; proceso de extracción, transformación y carga de datos. |
| Grano | Nivel de detalle mínimo representado por una fila de una tabla de hechos. |
| JWT | *JSON Web Token*; estándar de autenticación sin estado (ver 1.3.9). |
| OLAP | *Online Analytical Processing*; procesamiento analítico orientado a consultas de agregación multidimensional. |
| OLTP | *Online Transaction Processing*; procesamiento transaccional de alta concurrencia, propio de un ERP. |
| RBAC | *Role-Based Access Control*; control de acceso basado en roles (ver 1.3.9). |
| RFM | Recencia, Frecuencia y Valor Monetario; marco de variables para segmentación de clientes (ver 1.3.6). |
| SCD | *Slow Changing Dimension*; dimensión de variación lenta, técnica para preservar el historial de una dimensión. |

*Pendiente de profundizar:* el glosario cubre solo los términos citados explícitamente en el cuerpo del documento hasta la fecha. Debe revisarse contra la versión final de los cuatro capítulos antes del cierre, incorporando cualquier término técnico nuevo que se introduzca (p. ej. términos propios de la metodología Hefesto, ver Anexo D pendiente en 3.3).

## Anexo B. Índice de informes de auditoría técnica

La Tabla B.1 enumera los informes de auditoría técnica generados a lo largo del desarrollo del proyecto, instrumento descrito en 2.1.1 y referenciado en 3.5. Cada informe sigue el formato fecha/alcance/método/hallazgos/acción y consta íntegro en el repositorio del proyecto, bajo `docs/auditoria/`.

**Tabla B.1**
*Índice de informes de auditoría técnica del proyecto*

| N.° | Alcance |
|---|---|
| 00 | Planificación e inventario del proyecto |
| 01 | Auditoría de extractores ETL |
| 02 | Reglas de negocio validadas contra el ERP de producción |
| 03 | Cambios aplicados al pipeline ETL |
| 04 | Auditoría del pipeline Python del ETL |
| 05 | Auditoría de Machine Learning y calidad de datos del EDW |
| 06 | Auditoría del driver de conexión SAP en Docker |
| 07 | Revisión del diseño del EDW |
| 08 | Auditoría de transformadores del ETL |
| 09 | Auditoría del orquestador del ETL |
| 10 | Auditoría del cálculo de `fact_ventas_detalle` |
| 11 | Auditoría técnica de los modelos de Machine Learning |
| 12–17 | Análisis e integración del módulo de Metas y Comisiones |
| 18–19 | Corrección de llaves faltantes y grano de vendedor en metas |
| 20 | Decomisión del modelo `goals_rf` |
| 21–22 | Mejora de *features* y plan de mejora del modelo de ventas |
| 23–24 | Módulo de Bodega y predicción de categoría |
| 25 | Módulo de Venta Cruzada (*Cross-Selling*) |
| 26–29 | Corrección de filtros y rendimiento de la API de Bodega |
| 30 | Comisiones variables por margen y categoría |
| 31 | Módulo de Gerencia (cartera CxC/CxP) y Módulo de Notificaciones |
| 32 | Actualización del módulo de Bodega y Módulo de Ventas (Cartera 360°) |
| 33 | Actualización del módulo de Gerencia y Bodega (compras/proveedores) |
| 34 | Actualización del módulo de Ventas y plan de auditoría de comisiones |
| 35 | Actualización del módulo de Metas y Comisiones |
| 36 | Actualización del módulo de Administrador |
| 37 | Migraciones versionadas del esquema de aplicación (Alembic) |

*Nota.* Al cierre de esta sesión de trabajo el repositorio contenía informes hasta el número 37; si se generan auditorías posteriores (ver `CLAUDE.md` §Auditoría para el listado vivo), esta tabla debe actualizarse antes de la entrega final.

## Anexo C. Manual de usuario y actas de aceptación

> **[PENDIENTE — no fabricado]**
>
> Este anexo requiere un manual de usuario ilustrado con capturas de pantalla reales de la aplicación en ejecución, y actas de aceptación firmadas por usuarios reales de cada rol (gerencia, ventas, bodega, administración). Ninguno de los dos existe todavía como evidencia verificable dentro del alcance de esta sesión de trabajo, por lo que no se fabrica su contenido. Ver recomendación 6 del Capítulo IV (`docs/tesis/capitulos/04_conclusiones.md`).
>
> **Qué falta para cerrar este anexo (profundizar antes de la entrega final):**
>
> 1. **Manual de usuario ilustrado**, uno por rol (gerencia, ventas, bodega, administrador), con:
>    - Captura de la pantalla de inicio de sesión y flujo de autenticación.
>    - Captura del dashboard propio de cada rol (ver los cuatro dashboards descritos en 3.4.4), con anotaciones señalando cada indicador y su origen (modelo ML o KPI calculado).
>    - Captura de al menos un flujo operativo completo por rol (p. ej., en Ventas: consultar cartera 360°, revisar riesgo de abandono de un cliente, aceptar una sugerencia de venta cruzada; en Bodega: revisar sugerencia de transferencia entre bodegas).
>    - Las capturas deben tomarse contra la aplicación real corriendo (`docker compose up`, frontend en `http://localhost:5173`), no simularse ni describirse de memoria.
> 2. **Actas de aceptación firmadas**, una por rol, que documenten como mínimo: fecha, nombre y cargo del usuario que valida, funcionalidades revisadas, observaciones/hallazgos durante la validación, y conformidad (firma física o digital). Requieren la participación de usuarios reales de la empresa objeto de estudio — no pueden sustituirse por una simulación del autor de la tesis.
> 3. Una vez recolectada esta evidencia, este anexo pasa de "PENDIENTE" a un anexo completo, y la recomendación 6 del Capítulo IV puede marcarse como atendida.

---

## Notas de trazabilidad (no forma parte del cuerpo entregable — eliminar antes de la versión final)

- Este archivo es la versión Markdown del entregable oficial `docs/tesis/latex/anexos/anexos.tex` (creado 2026-07-17 en esa sesión). Se agrega ahora en `docs/tesis/capitulos/` para completar el paralelo `.md` de los cuatro capítulos + referencias ya existentes, a pedido explícito del usuario.
- El Anexo C se mantiene deliberadamente sin contenido fabricado: ni las capturas de pantalla ni las actas de aceptación existen como evidencia verificable en esta sesión. No inventar nombres de usuarios, fechas de firma ni observaciones de validación.
- Pendiente de decisión del usuario: si se agrega un **Anexo D** con la documentación de la metodología Hefesto (ver nueva subsección 3.3.6 en `03_resultados.md`), evaluar si conviene moverlo aquí como anexo separado (comparativa de metodologías, tabla de mapeo de fases) en vez de dejarlo embebido en el capítulo de Resultados — depende de qué tan extensa resulte esa sección al profundizarla.
