# CAPÍTULO III. RESULTADOS Y DISCUSIÓN

## 3.1 Análisis y discusión de los resultados

### 3.1.1 Proceso de aprovechamiento de datos previo al proyecto

Antes del desarrollo de la plataforma, la información generada por la operación comercial de la empresa objeto de estudio residía exclusivamente en el sistema transaccional ERP, sin ningún mecanismo de consolidación histórica ni de análisis multidimensional. Las consultas analíticas —cuando se requerían— se ejecutaban de forma directa contra la base de datos operativa (SAP SQL Anywhere 17), compitiendo por recursos con la operación diaria de facturación, inventario y cobranza, y quedando limitadas a la estructura relacional normalizada del ERP, no orientada a consulta analítica.

### 3.1.2 Problemas generales del proceso actual

Consistente con lo expuesto en el planteamiento del problema (1.1.1), el diagnóstico técnico confirmó tres carencias estructurales: (a) ausencia de indicadores clave de desempeño unificados y comparables entre sucursales; (b) ausencia de un mecanismo de proyección de demanda que anticipara la reposición de inventario; y (c) ausencia de herramientas de apoyo a la gestión comercial (venta cruzada, identificación de riesgo de abandono, priorización de cartera) basadas en evidencia histórica. Estas tres carencias definieron el alcance funcional de la plataforma desarrollada, descrita en los apartados siguientes.

## 3.2 Sistema ERP de origen

### 3.2.1 Arquitectura del sistema transaccional

La empresa objeto de estudio opera sobre SAP SQL Anywhere 17 como motor de base de datos transaccional, soportando de forma centralizada los módulos de ventas, inventario, cartera, caja, compras y nómina para la totalidad de sus sucursales bajo un único código de empresa (`codemp = '01'`). Este sistema constituye la fuente única y de solo lectura de todos los datos operativos consumidos por la plataforma desarrollada.

### 3.2.2 Gestor de base de datos de origen

SAP SQL Anywhere 17 es un motor de base de datos relacional optimizado para el procesamiento transaccional de alta concurrencia (OLTP), con más de 500 tablas operativas identificadas en el catálogo de la instalación (ver `docs/identificacion_bd.md` del repositorio del proyecto). La conexión desde el proceso ETL se estableció mediante el driver ODBC nativo en entorno host y FreeTDS/TDS 5.0 en el entorno containerizado de desarrollo, dado que SAP SQL Anywhere no dispone de un driver ODBC oficial para contenedores Linux.

## 3.3 Diseño de la arquitectura del subsistema

El diseño del repositorio analítico se desarrolló bajo el Ciclo de Vida Dimensional de Kimball (Kimball & Ross, 2013), siguiendo sus cuatro decisiones de diseño: selección del proceso de negocio, declaración de la granularidad, identificación de las dimensiones e identificación de los hechos.

### 3.3.1 Selección de los procesos de negocio

Se seleccionaron seis áreas operativas para su modelado dimensional conformado: ventas y devoluciones, logística y movimiento de inventarios, compras y abastecimiento, cuentas por cobrar y cuentas por pagar, finanzas y caja, y recursos humanos (nómina).

### 3.3.2 Declaración de la granularidad

Se adoptó la granularidad más fina disponible en el sistema de origen para cada proceso: línea de detalle individual por comprobante en ventas, devoluciones y compras; movimiento físico unitario por transacción en el kardex de inventario; snapshot diario consolidado de existencias; movimiento individual de cobro o pago en cartera; y registro mensual individualizado por empleado en nómina.

### 3.3.3 Identificación de las dimensiones

El modelo se estructuró en once dimensiones conformadas: tiempo (`dim_fecha`, generada algorítmicamente con granularidad diaria), producto (`dim_producto`, SCD tipo 2 para preservar el historial de cambios de precio y clasificación), cliente (`dim_cliente`, SCD tipo 2 y anonimizado mediante hash con sal), sucursal, almacén, proveedor, vendedor, empleado, usuario, forma de pago y geografía.

### 3.3.4 Identificación de los hechos

Se definieron once tablas de hechos: ventas de detalle (hecho principal), movimientos de inventario (kardex), snapshot de inventario, compras, cobros de cartera, pagos a proveedores, movimientos de caja, nómina, metas comerciales, devoluciones y logs de auditoría. La Tabla 3.1 sintetiza la matriz de bus dimensional, mapeando la correspondencia entre las dimensiones conformadas y las tablas de hechos.

**Tabla 3.1**
*Matriz de bus dimensional (dimensiones conformadas × tablas de hechos)*

| Tabla de hechos | Tiempo | Sucursal | Almacén | Producto | Cliente | Proveedor | Vendedor |
|---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| `fact_ventas_detalle` | X | X | | X | X | | X |
| `fact_inventario_snapshot` | X | X | X | X | | | |
| `fact_movimientos_inventario` | X | X | X | X | | | |
| `fact_compras` | X | X | X | X | | X | |
| `fact_cobros_cxc` | X | X | | | X | | X |
| `fact_pagos_cxp` | X | X | | | | X | |
| `fact_nomina` | X | X | | | | | |
| `fact_devoluciones` | X | X | X | X | X | | |

*Nota.* Elaboración propia a partir del modelo dimensional implementado, documentado en `docs/tesis/05_desarrollo_metodologico.md` y `docs/arquitectura_dw.md` del repositorio del proyecto. Se omiten las dimensiones empleado, usuario, forma de pago y geografía por razones de espacio; su mapeo completo consta en el documento fuente.

### 3.3.5 Anonimización de datos personales

Dado que la dimensión cliente contiene información de carácter personal, el proceso ETL aplica una función de hash unidireccional con sal (`PII_SALT`) para desasociar la identidad real del cliente de su historial transaccional dentro del Data Warehouse, aislando la única tabla con información personal identificable (`public.cliente_lookup`) fuera del esquema analítico (`edw`). El proceso ETL aborta su ejecución si la variable de entorno `PII_SALT` no está definida o conserva un valor por defecto inseguro, como salvaguarda ante un despliegue mal configurado.

### 3.3.6 Verificación retrospectiva del diseño mediante las fases de Hefesto

> **[BORRADOR — falta profundizar].** Esta subsección aplica la metodología Hefesto (Bernabeu, 2010) de forma **retrospectiva**: a diferencia del uso convencional de Hefesto (guiar el diseño del Data Warehouse desde cero), aquí se emplea como marco de verificación sobre un sistema que ya fue construido siguiendo el Ciclo de Vida Dimensional de Kimball (3.3.1–3.3.4). El objetivo es confirmar que cada una de las cuatro fases que exige Hefesto tiene un entregable real y auditable dentro de lo ya desarrollado, no repetir el diseño ni fabricar artefactos nuevos. La comparación cualitativa entre Kimball, Hefesto y otras metodologías de construcción de Data Warehouse (SAS Rapid Data Warehousing, entre otras) fue evaluada empíricamente por Silva Peñafiel et al. (2019), cuyo resultado favoreció a Hefesto 2.0 frente a Kimball y SAS en los criterios que compararon — esta tesis no reproduce ni fabrica un puntaje propio de esa comparación, se remite a dicho estudio como respaldo bibliográfico.

La Tabla 3.1bis mapea las cuatro fases de Hefesto contra las secciones de este documento donde el entregable equivalente ya está descrito, con la evidencia técnica real que lo respalda.

**Tabla 3.1bis**
*Fases de Hefesto mapeadas contra el desarrollo ya documentado del proyecto*

| Fase Hefesto | Entregable esperado | Equivalente ya construido | Evidencia / sección |
|---|---|---|---|
| F1. Análisis de requerimientos | Preguntas de negocio, indicadores clave, perspectivas de análisis | Tres carencias estructurales diagnosticadas (KPIs unificados, proyección de demanda, apoyo a gestión comercial) que definieron el alcance funcional de los cuatro dashboards por rol | 3.1.2, 1.4 (objetivos específicos) |
| F2. Análisis de los OLTP | Identificación de hechos e indicadores en el sistema fuente, mapeo de campos origen→DW, definición de granularidad | Análisis del esquema OLTP de SAP SQL Anywhere 17 (>500 tablas) y validación empírica de reglas de negocio del origen (dirección de movimientos de kardex, estados de documento, mecánica de transferencias) mediante `SELECT` de solo lectura antes de codificar cada extractor | 3.2, 2.1.1, 3.3.2 |
| F3. Modelo lógico del Data Warehouse | Esquema en estrella o constelación: tablas de dimensiones y de hechos, jerarquías | Ciclo de Vida Dimensional de Kimball ya aplicado: 11 dimensiones conformadas y 11 tablas de hechos en constelación, con matriz de bus dimensional (Tabla 3.1) | 3.3.1–3.3.4 |
| F4. Integración de datos | Proceso ETL: extracción, limpieza/transformación, carga, periodicidad de actualización | ETL en Python con 24 extractores SQL tokenizados, carga incremental e idempotente controlada por `edw.etl_control`, resolución de SCD tipo 2 y anonimización de PII | 3.4.1, 3.3.5 |

*Nota.* Elaboración propia a partir del mapeo de las cuatro fases de Hefesto (Bernabeu, 2010) contra el desarrollo real del proyecto, ya descrito en las secciones referenciadas de este mismo capítulo. No se introduce ningún dato, tabla o proceso nuevo en esta subsección: cada celda de la columna "Evidencia / sección" remite a contenido ya redactado y verificable en el repositorio.

**Decisión de thesis-advisor (2026-07-17):** no declarar en el capítulo de Metodología (2.2) que el proyecto "combinó Kimball y Hefesto" como metodología de diseño conjunta — el diseño real ya estaba tomado con Kimball antes de mapearlo contra Hefesto, y afirmar una combinación de diseño sería contradictorio en la defensa. Se mantiene la lectura retrospectiva/de verificación de esta subsección, más honesta con la cronología real del proyecto. Ver registro completo en `docs/tesis/memoria_tesis.md`.

**Qué falta para profundizar esta subsección** (no resuelto en esta sesión):

1. Ampliar el desarrollo de cada fila de la Tabla 3.1bis con mayor detalle narrativo (actualmente es una tabla de mapeo compacta; el formato de referencia dedica una subsección por fase).
2. Evaluar con el tutor si conviene mover esta subsección a un anexo separado (ver nota en `docs/tesis/capitulos/05_anexos.md`) en vez de dejarla embebida en el capítulo de Resultados, si al profundizarla resulta demasiado extensa.
3. Si el tutor exige una matriz de selección metodológica cuantitativa (Kimball vs. Hefesto vs. otra, con puntaje por criterio, al estilo de la Tabla 17 del formato de referencia), **no fabricarla aquí**: requiere criterios de evaluación y una decisión real del equipo del proyecto, no disponibles en esta sesión.

### 3.3.7 Modelo conceptual: mapeo de fuentes y fórmulas de indicadores

> **[BORRADOR — falta profundizar].** Esta subsección documenta, con evidencia extraída directamente del código real del proyecto (no de memoria ni de convención genérica de la literatura), dos elementos que la fase F2 de Hefesto (3.3.6) exige y que hasta ahora solo se mencionaban de forma general en 3.3.3/3.3.4: el mapeo campo a campo entre el sistema transaccional de origen y el Data Warehouse, y la fórmula real con la que cada indicador de los dashboards se calcula a partir de las tablas del EDW.

**Mapeo de campos origen (ERP) → Data Warehouse.** La Tabla 3.1ter recoge ejemplos representativos de la transformación aplicada por los *transformers* del ETL (`etl/transformers/fact_transformer.py`, `dim_transformer.py`), no de los extractores SQL crudos (que traen las columnas del ERP mayormente sin renombrar).

**Tabla 3.1ter**
*Ejemplos de mapeo de campos del ERP de origen hacia el Data Warehouse*

| Campo origen (SAP SQL Anywhere) | Campo destino (EDW) | Regla de transformación |
|---|---|---|
| `renglonesfacturas.totren` | `fact_ventas_detalle.subtotal_neto` | Se usa directo (subtotal ya post-descuento calculado por el ERP), sin recalcular a partir de `cantid * preuni`. |
| `renglonesfacturas.porceiva` (fracción decimal) | `fact_ventas_detalle.valor_iva` | `valor_iva = subtotal_neto * porceiva`; se usa el campo de tasa de la línea, no `encabezadofacturas.poriva` (que es un código de tarifa, no una tasa). |
| `renglonesfacturas.desinv` ('S'/'N') | `fact_ventas_detalle.costo_unitario` / `costo_total` / `margen_bruto` | Si `desinv = 'N'` (línea no inventariable, p. ej. un servicio), los tres campos de costo quedan `NULL`: no se traslada el costo de `articulos.ultcos` (regla de negocio 5 del proyecto). |
| `renglonesfacturas.bienser` ('S'/'B'), a nivel de línea | `fact_ventas_detalle.es_linea_servicio` | Se clasifica por la línea de venta, no por `articulos.bienser` del maestro de producto, que resultó poco confiable en producción (1 de 8 152 artículos marcado 'S' frente a 58 407 líneas reales en 'S'). |
| `kardex.cantot` | `fact_movimientos_inventario.cantidad_movimiento` | Se fuerza a magnitud absoluta: `cantot` siempre llega positivo del origen (regla de negocio 3). |
| `kardex.tipdoc` (`EN`/`SA`/`AC`/`AD`) | `fact_movimientos_inventario.es_entrada` / `es_salida` | La dirección del movimiento se deriva del tipo de documento, nunca del signo de la cantidad (regla de negocio 3); si `tipdoc` no viene en el origen, el proceso falla explícitamente en vez de asumir un valor por defecto. |
| `clientes.cupo`, `nomcli`, `rucced`, `codcla` | `dim_cliente.limite_credito`, `nombre_cliente`, `ruc_cedula`, `clase_cliente` | Mapeo directo; `dias_credito` no existe en el origen y se fija a 30 en el extractor, no calculado. |
| `articulos.ultcos` (último costo) | `dim_producto.costo_promedio` | Se conserva el nombre de columna heredado del diseño original del esquema aunque semánticamente el valor sea "último costo", no un promedio real. |

*Nota.* Elaboración propia a partir de `etl/extractors/*.sql`, `etl/transformers/fact_transformer.py` y `dim_transformer.py`, y `docs/arquitectura_dw.md` del repositorio del proyecto. Selección de 8 ejemplos representativos de las tres tablas de hechos/dimensiones principales (ventas, inventario, cliente/producto); el mapeo completo de las 11 dimensiones y 11 hechos consta en el código fuente citado.

**Fórmulas reales de los indicadores por rol.** A diferencia de una fórmula de libro de texto, cada indicador de la Tabla 3.1quater se cita tal como está implementado en el backend, con el servicio/repositorio responsable.

**Tabla 3.1quater**
*Fórmulas de los indicadores principales de cada dashboard, por rol*

| Rol | Indicador | Fórmula | Origen en el código |
|---|---|---|---|
| Gerencia | Ingresos totales | `SUM(subtotal_neto)` de líneas de venta − `SUM(total_linea_devolucion)` | `AnalyticsRepository.get_management_kpis` |
| Gerencia | Margen de utilidad neta (%) | `((ventas_netas − devoluciones) − costo_neto) / (ventas_netas − devoluciones) × 100` | `AnalyticsRepository.get_management_kpis` |
| Gerencia | Ticket promedio | `(ventas_netas − devoluciones) / COUNT(DISTINCT número de factura)` | `AnalyticsRepository.get_management_kpis` |
| Ventas | Cumplimiento de meta individual | `venta_real del período / monto_meta` (deriva el nivel y la tasa de comisión) | `CommissionEngine.calcular_comision` |
| Ventas | Meta proyectada del mes | `cumplimiento_actual / días_transcurridos × 30` | `AnalyticsRepository.get_sales_performance` |
| Ventas | Tasa de conversión de venta cruzada | `sugerencias_aceptadas / sugerencias_mostradas × 100` (0 si no hubo sugerencias mostradas) | `RecommendationEventRepository.get_conversion_kpis` |
| Ventas | Riesgo de abandono (*churn*) | Salida directa del modelo `churn_classifier` sobre 3 variables calculadas en SQL: `frecuencia = COUNT(DISTINCT fecha)`, `valor_monetario = SUM(subtotal_neto)`, `ticket_promedio = valor_monetario / frecuencia` | `PredictionRepository.get_churn_features`, `PredictionService.get_churn_risk` |
| Bodega | Rotación de inventario anualizada | `(costo_de_ventas / inventario_promedio) × 365 / días_del_rango` | `WarehouseService.get_kpis` |
| Bodega | Días de inventario disponibles (global) | `valor_total_inventario / (costo_de_ventas / días_del_rango)` | `WarehouseService.get_kpis` |
| Administrador | Última carga exitosa del Data Warehouse | `MAX(edw.etl_control.ultimo_etl_ok) WHERE estado = 'SUCCESS'` | `SystemRepository.get_ultima_carga_dw` |
| Administrador | Intentos de inicio de sesión fallidos (ventana) | `COUNT(*)` sobre `public.intentos_login_fallidos` en la ventana de horas configurada | `SystemRepository.get_conteo_logins_fallidos` |

*Nota.* Elaboración propia a partir de `backend/app/repositories/` y `backend/app/services/` del repositorio del proyecto. Dos advertencias explícitas de honestidad técnica, verificadas y no asumidas: (a) el campo `roi_estimado` del dashboard de Gerencia **no es un ROI real** — el propio código lo documenta como una simulación (`margen_utilidad_neta × 1.15`), no una relación costo/beneficio de una inversión o campaña real, y así debe describirse si se cita en el cuerpo del capítulo; (b) no existe en el backend una fórmula que combine el riesgo de abandono (*churn*) y el segmento RFM del cliente en un solo "nivel de riesgo" — son dos modelos independientes que se muestran por separado en el dashboard de Ventas, sin una fórmula de combinación publicada.

**Qué falta para profundizar esta subsección** (no resuelto en esta sesión):

1. Cubrir el resto de los indicadores de cada dashboard, no solo los 2-3 principales por rol listados aquí.
2. Si el formato final admite figuras, un diagrama de mapeo OLTP→DW (equivalente a la Figura 6 del formato de referencia) haría más legible la Tabla 3.1ter que su forma tabular actual — pendiente de decisión, dado que el usuario indicó no generar contenido LaTeX en esta sesión.

## 3.4 Desarrollo del subsistema

### 3.4.1 Proceso ETL

El proceso ETL se implementó en Python como un módulo orquestado (`etl/orchestrator.py`), con 24 extractores SQL tokenizados (`{CODEMP}`, `{ESTADO}`, `{FECHA_DESDE}`) verificados individualmente contra el sistema de origen. La carga de hechos es incremental e idempotente: antes de cargar, se elimina el rango de fechas afectado mediante `dim_fecha` y se realiza un *append* controlado por una tabla de control de ejecuciones (`edw.etl_control`), evitando la duplicación de registros ante reejecuciones del proceso.

### 3.4.2 Arquitectura del backend

La API backend se desarrolló en FastAPI siguiendo una arquitectura en capas (`routes` → `services` → `repositories`), con autenticación JWT y control de acceso basado en roles (RBAC) para los cuatro roles de negocio definidos (gerencia, ventas, bodega, administrador), conforme al marco descrito en 1.3.9. Los servicios lanzan excepciones de dominio, traducidas a respuestas HTTP por manejadores globales, manteniendo la lógica de negocio fuera de los controladores de ruta.

### 3.4.3 Modelos de Machine Learning

Se entrenaron y publicaron seis modelos de Machine Learning sobre el Data Warehouse: predicción de ventas (Random Forest), predicción de demanda de reposición (Gradient Boosting), segmentación de clientes mediante K-means sobre variables RFM, clasificación de riesgo de abandono de clientes (Random Forest), recomendación de venta cruzada (filtrado colaborativo item-item por similitud coseno) y detección de anomalías transaccionales (Isolation Forest, no supervisado). Cada modelo se serializa como artefacto `.pkl` y se sirve mediante el backend a través de un volumen de solo lectura, desacoplando el ciclo de reentrenamiento del ciclo de vida del servicio web.

### 3.4.4 Interfaz web

El frontend se desarrolló como una aplicación de página única (SPA) en React 19 con TypeScript, con gestión de estado mediante Zustand y sincronización de datos remotos mediante TanStack Query. Cada uno de los cuatro roles de negocio accede a un dashboard propio que integra indicadores descriptivos y las predicciones del modelo correspondiente a sus decisiones operativas, conforme al enfoque de BI operacional descrito en 1.3.2:

- **Gerencia**: indicadores clave de desempeño consolidados por sucursal (ingresos, margen, ticket promedio) y la predicción de ventas del modelo de Random Forest, con filtros de sucursal, vendedor y granularidad temporal.
- **Ventas**: cartera de clientes con la probabilidad de abandono (*churn*) calculada por cliente, el segmento RFM al que pertenece, y un asistente de venta cruzada que sugiere productos complementarios a partir del modelo de filtrado colaborativo item-item, además del avance de metas y comisiones del vendedor autenticado.
- **Bodega**: proyección de demanda de reposición por producto y almacén, matriz de rotación de inventario y sugerencias de transferencia entre bodegas derivadas del modelo de predicción de demanda.
- **Administrador**: gestión de usuarios y roles, bitácora de auditoría del sistema, y panel de anomalías transaccionales detectadas por el modelo de Isolation Forest.

Todos los dashboards comparten un componente de notificaciones inteligentes que consolida alertas generadas por los propios modelos (por ejemplo, desviación del pronóstico de ventas o clientes con riesgo de abandono alto) y las presenta de forma segmentada según el rol del usuario autenticado.

### 3.4.5 Metodología de gestión del desarrollo por fases

> **[BORRADOR — falta profundizar].** A diferencia del formato de referencia de esta tesis, que documenta la adopción formal de Kanban como metodología de gestión (tablero, historias de usuario con criterios de aceptación, distribución de entregas), este proyecto **no utilizó un marco ágil con nombre propio ni una herramienta de tablero** (Trello, Jira u otra) — no existe esa evidencia en el repositorio y esta subsección no la fabrica. Lo que sí existe, verificable directamente en el repositorio, es una práctica de gestión propia y consistente a lo largo de todo el desarrollo: **entrega incremental por fases numeradas dentro de cada módulo de negocio, cada una gatillada por un diagnóstico verificado en código y cerrada con una auditoría antes de pasar a la siguiente.**

Cada actualización de un módulo (Gerencia, Ventas, Bodega, Administrador, Metas y Comisiones) comenzó con un documento de planificación en `docs/features/plan_actualizacion_modulo_*.md`, estructurado siempre de la misma forma: una sección "0. Diagnóstico verificado en código (no supuesto)" que identifica defectos concretos (numerados `D1`, `D2`, ...) mediante lectura directa del código, no supuestos; seguida de una "Fase 1", "Fase 2", etc., cada una dirigida a cerrar uno o más de esos defectos. La Tabla 3.4bis muestra un ejemplo real y completo de esta estructura, tomado del plan de actualización del módulo Bodega.

**Tabla 3.4bis**
*Ejemplo real de fases de un plan de actualización de módulo (Bodega)*

| Fase | Defecto(s) atendido(s) | Alcance |
|---|---|---|
| Fase 1 | D1, D2 | Filtros consistentes de punta a punta |
| Fase 2 | D3 | Valores monetarios condicionados al tipo de movimiento |
| Fase 3 | D4, D5 | Reorganización del dashboard |
| Fase 4 | D6 | Motivo de transferencias con fundamento estadístico |
| Fase 5 | D7 | Rediseño de reportes |

*Nota.* Elaboración propia a partir de `docs/features/plan_actualizacion_modulo_bodega.md` del repositorio del proyecto, verificado con `docs/auditoria/32_actualizacion_modulo_bodega.md`, que documenta el cierre real de las 5 fases. El mismo patrón (diagnóstico numerado → fases → auditoría de cierre) se repite en los planes de actualización de los módulos de Gerencia, Ventas, Administrador y Metas y Comisiones (`docs/features/plan_actualizacion_modulo_*.md`, auditorías 32 a 37).

Un segundo ejemplo, esta vez en el frontend, es directamente verificable en el historial de control de versiones del repositorio: el 16 de julio de 2026 se registraron siete confirmaciones de código consecutivas (`git log`), cada una etiquetada explícitamente como una fase de un mismo plan (`F1` a `F7`) del rediseño visual del sistema de diseño de la interfaz ("Signal Deck 3.0"): F1 paleta de colores por capas, F2 componentes primitivos de interacción, F3 estructura de navegación, F4 formularios, F5 tablas, F6 instrumentación de la pantalla de inicio de sesión, F7 tarjetas de indicadores y gráficos — seguidas ese mismo día de cuatro confirmaciones adicionales de ajuste (`fix`) sobre lo recién entregado, evidencia de un ciclo real de entrega y corrección inmediata, no de una única entrega monolítica.

**Qué falta para profundizar esta subsección** (no resuelto en esta sesión):

1. Reconstruir una tabla cronológica completa de todas las fases de los ~6 planes de actualización de módulo (no solo el ejemplo de Bodega), cruzando fecha real del commit correspondiente con el número de auditoría que la cierra.
2. Decidir con el tutor si esta práctica ad hoc debe presentarse simplemente como lo que es (un método propio, pragmático, sin marco formal con nombre) o si conviene compararla explícitamente contra Kanban/Scrum en una tabla de características, citando literatura real sobre metodologías ágiles ligeras — sin declarar una adopción formal que no ocurrió.

### 3.4.6 Stack tecnológico institucional

La Tabla 3.4ter formaliza en una única tabla el conjunto tecnológico ya descrito de forma narrativa en el apartado de Materiales (2.1), agrupado por capa de la arquitectura.

**Tabla 3.4ter**
*Stack tecnológico del proyecto, por capa de la arquitectura*

| Capa | Tecnología | Rol en el proyecto |
|---|---|---|
| Origen de datos | SAP SQL Anywhere 17 | Sistema ERP transaccional (OLTP), fuente única de solo lectura |
| ETL | Python 3, pandas, SQLAlchemy 2, pyodbc/psycopg2, python-dotenv | Extracción, transformación y carga hacia el Data Warehouse |
| Almacenamiento analítico | PostgreSQL 16 | Motor del Data Warehouse dimensional (esquemas `edw`, `public`, `ml`) |
| Machine Learning | scikit-learn, XGBoost, LightGBM, CatBoost, Optuna, mlxtend, joblib | Entrenamiento, ajuste de hiperparámetros y serialización de los 6 modelos |
| Backend / API | FastAPI, Pydantic v2, SQLAlchemy 2, python-jose, passlib+bcrypt, uvicorn | Exposición de la API REST, autenticación JWT y control de acceso por rol |
| Frontend | React 19, TypeScript, Vite, Tailwind CSS 4, Zustand, TanStack Query, React Router 7, Recharts, Axios | Interfaz web (SPA) con dashboards diferenciados por rol |
| Infraestructura | Docker, Docker Compose | Orquestación de los servicios (`postgres_edw`, `backend`, `frontend`, perfiles `etl`/`ml`) |
| Control de esquema | Alembic | Migraciones versionadas del esquema `public` de la aplicación |
| Pruebas | pytest | Pruebas automatizadas de reglas de negocio del backend |

*Nota.* Elaboración propia a partir de `CLAUDE.md` §Tecnologías del repositorio del proyecto; ver 2.1 para el detalle narrativo de cada capa.

### 3.4.7 Requisitos funcionales y no funcionales

> **[BORRADOR — falta profundizar].** Al igual que la subsección 3.3.6 (Hefesto), esta tabla de requisitos se reconstruye de forma **retrospectiva** a partir del sistema ya entregado (los cuatro dashboards por rol descritos en 3.4.4, los endpoints reales de la API, y las reglas de negocio validadas en 2.2.3), no de un levantamiento formal de requisitos previo a la construcción con historias de usuario y criterios de aceptación firmados por un cliente — ese artefacto no existe en el repositorio y no se fabrica aquí. La Tabla 3.4quater resume los requisitos funcionales principales, agrupados por rol de negocio, y la Tabla 3.4quinquies los requisitos no funcionales, ambos verificables contra el sistema real.

**Tabla 3.4quater**
*Requisitos funcionales principales, por rol de negocio*

| Rol | Requisito funcional | Verificable en |
|---|---|---|
| Gerencia | Consultar indicadores clave (ingresos, margen, ticket promedio) filtrados por sucursal y periodo | `GET /analytics` (§3.4.2), Tabla 3.1quater |
| Gerencia | Consultar la predicción de ventas del modelo entrenado, con desglose por categoría cuando aplique | `AnalyticsService`, modelo `sales_rf`/`sales_best` (1.3.5) |
| Ventas | Consultar la cartera de clientes propia con riesgo de abandono y segmento RFM, restringida a los clientes del vendedor autenticado | `PredictionService.get_churn_risk`/`get_customer_segment`, validación de pertenencia por RLS (regla de negocio RN-V4) |
| Ventas | Recibir sugerencias de venta cruzada y registrar la telemetría de aceptación/rechazo | `/analytics/ventas/cross-selling` (`sugerencias`, `eventos`) |
| Ventas | Consultar el avance de meta y comisión propia, con desglose de la meta sugerida | `/analytics/ventas/goals`, `/gerencia/goals/commissions` |
| Bodega | Consultar proyección de demanda de reposición por producto y almacén | `/analytics/bodega/salidas-forecast`, `/prediccion-compras-mes` |
| Bodega | Consultar sugerencias de transferencia entre bodegas con justificación estadística | `/analytics/bodega/transferencias-sugeridas` (RN-B9) |
| Administrador | Gestionar usuarios y roles del sistema | `/users`, `/roles` |
| Administrador | Consultar la bitácora de auditoría del sistema con filtros de fecha/usuario/módulo | `/analytics/admin/audit-logs` |
| Administrador | Consultar anomalías transaccionales detectadas por el modelo de Isolation Forest | `/analytics/admin/anomalies` |
| Todos los roles | Recibir notificaciones segmentadas por rol, generadas por los propios modelos del sistema | `/notificaciones` |

**Tabla 3.4quinquies**
*Requisitos no funcionales principales*

| Categoría | Requisito | Verificable en |
|---|---|---|
| Seguridad | Autenticación sin estado mediante JWT y control de acceso basado en 4 roles cerrados | 1.3.9, `Jones et al., 2015`; `Sandhu et al., 2000` |
| Seguridad | La base de datos de producción del ERP se trata en todo momento como de solo lectura | Restricción del proyecto (§Restricciones de `CLAUDE.md`) |
| Privacidad | Anonimización de datos personales de clientes mediante hash con sal antes de su ingreso al Data Warehouse | 3.3.5 |
| Disponibilidad/Idempotencia | La carga del ETL es incremental e idempotente: reejecuciones no duplican registros | 3.4.1, `edw.etl_control` |
| Trazabilidad | Toda intervención sobre un componente del sistema queda documentada en un informe de auditoría antes de aplicarse | 2.1.1, Anexo B (`docs/tesis/capitulos/05_anexos.md`) |
| Mantenibilidad | Evolución del esquema de la aplicación mediante migraciones versionadas, con una prueba de guardia automatizada que impide el desfase entre modelos y migraciones | 3.7.2 |
| Portabilidad/Despliegue | Orquestación completa de los servicios mediante contenedores, reproducible en cualquier entorno con Docker | 3.6 |

*Nota.* Elaboración propia a partir del sistema real descrito en las secciones referenciadas de este mismo capítulo. Ninguna fila introduce un requisito no verificable contra el repositorio del proyecto.

**Qué falta para profundizar esta subsección** (no resuelto en esta sesión): ampliar ambas tablas con requisitos secundarios (actualmente cubren solo los principales por rol), y decidir con el tutor si el carácter retrospectivo de esta reconstrucción debe declararse tan explícitamente en el cuerpo final del capítulo o solo en esta nota de trabajo.

## 3.5 Pruebas y validación técnica

La validación del sistema se ejecutó de forma continua durante el desarrollo, mediante dos mecanismos complementarios, en lugar de una única fase de pruebas de aceptación al cierre del proyecto: (a) auditoría técnica documentada de cada componente antes de su modificación (más de 30 informes, formato fecha/alcance/método/hallazgos/acción, `docs/auditoria/`), y (b) pruebas automatizadas (`pytest`) sobre las reglas de negocio del backend y la sincronía entre el esquema de base de datos y los modelos de la aplicación.

Este proceso de auditoría continua identificó y corrigió defectos reales de severidad crítica durante el desarrollo, entre ellos: una fuga de control de acceso (RLS) que permitía a un usuario del rol ventas consultar el riesgo de abandono, las recomendaciones y el segmento de cualquier cliente del sistema, no solo de su propia cartera; un error que provocaba una respuesta HTTP 500 en el 100 % de las solicitudes del indicador principal del dashboard de Ventas, causado por un filtro contra una columna inexistente en la tabla de metas comerciales; y una condición de carrera en la inicialización de dependencias del backend que no se manifestaba en el entorno de desarrollo local (Python 3.14) pero sí en la imagen de contenedor real (Python 3.11), detectada únicamente al reconstruir el contenedor de producción antes de dar por válido un cambio. La corrección de estos defectos, documentada en el historial de auditorías del proyecto, se tradujo en el establecimiento de una práctica de validación de extremo a extremo —reconstruir el contenedor real, no solo ejecutar en el entorno de desarrollo— antes de considerar cerrado cualquier cambio sobre el backend.

## 3.6 Implantación

El despliegue de la plataforma se orquestó mediante Docker Compose, con tres servicios principales en ejecución continua (`postgres_edw`, `backend`, `frontend`) y dos perfiles opcionales invocados de forma manual (`etl` y `ml`) para las cargas de datos y el reentrenamiento de modelos, respectivamente. El esquema de la base de datos de aplicación (`public.*`) se gestiona mediante migraciones versionadas con Alembic, aplicadas automáticamente al arrancar el contenedor del backend, tanto en una instalación nueva como en una base de datos ya existente, eliminando la necesidad de intervención manual sobre el esquema en cada despliegue.

## 3.7 Mantenimiento y crecimiento iterativo

### 3.7.1 Conciliación y monitoreo de datos

La trazabilidad operativa de las cargas del ETL se sostiene en la tabla de control `edw.etl_control`, que registra el estado de cada ejecución y habilita la carga incremental por última corrida exitosa, sin requerir reprocesar el histórico completo en cada actualización.

### 3.7.2 Evolución del esquema

El esquema de la aplicación evolucionó de forma controlada mediante migraciones versionadas (Alembic), reemplazando un esquema previo que se generaba de tres fuentes distintas y potencialmente inconsistentes entre sí (DDL de inicialización de volumen, sincronización automática del ORM, y una alteración de esquema codificada de forma fija en el arranque del backend). Un test de guardia automatizado (`backend/tests/integration/test_alembic_schema_sync.py`) verifica que ningún cambio futuro de modelo quede sin su migración correspondiente.

## 3.8 Resultados

### 3.8.1 Volumen del Data Warehouse

Al cierre de la fase de desarrollo documentada en este proyecto, el Data Warehouse consolidó 538 862 registros en la tabla de hechos principal (`fact_ventas_detalle`), cubriendo el período del 2 de enero de 2018 al 8 de julio de 2026, y aproximadamente 948 000 registros en la tabla de movimientos de inventario (`fact_movimientos_inventario`).

### 3.8.2 Desempeño de los modelos de Machine Learning

La Tabla 3.2 presenta las métricas de desempeño finales de los seis modelos de Machine Learning entrenados sobre el Data Warehouse, evaluadas mediante partición cronológica de entrenamiento y prueba (*holdout*) para evitar fuga de información temporal.

**Tabla 3.2**
*Desempeño de los modelos de Machine Learning entrenados*

| Modelo | Algoritmo | Métrica principal | Resultado |
|---|---|---|---|
| Predicción de ventas | Random Forest (500 árboles) | R² / MAE / RMSE | 0.297 / USD 3 789.68 / USD 6 285.43 |
| Predicción de demanda de reposición | Gradient Boosting | R² / RMSE / MAE | 0.959 / 98.66 / 5.22 unidades |
| Segmentación de clientes (RFM) | K-means | Coeficiente de silueta | 0.612 |
| Riesgo de abandono (*churn*) | Random Forest | Exactitud / AUC-ROC | 71 % / 0.701 |
| Recomendación de venta cruzada | Filtrado colaborativo item-item | Precision@5 / Cobertura | 0.077 / 97.9 % |
| Detección de anomalías | Isolation Forest (no supervisado) | Contaminación configurada | 1 % |

*Nota.* Elaboración propia a partir de `ml/REPORTE_MEJORA_MODELOS.md` y `docs/ml_metrics_report.md` del repositorio del proyecto. El modelo de predicción de ventas mejoró desde un R² inicial de -0.029 (peor que una predicción constante) hasta 0.297 mediante el acotamiento de la ventana de entrenamiento a los últimos tres años y la incorporación de variables exógenas rezagadas, calendario cíclico y feriados; el detalle de cada experimento intermedio consta en la fuente citada.

### 3.8.3 Discusión

El resultado más relevante desde la perspectiva metodológica fue la confirmación empírica de que la ventana de entrenamiento, y no la cantidad de variables predictoras, era el factor dominante en el desempeño del modelo de predicción de ventas: el histórico completo de ocho años exhibe una tendencia estructural de crecimiento sostenido (aproximadamente 31 % entre 2018 y 2026) que un modelo entrenado sobre todo el período subestima sistemáticamente al evaluarse contra los períodos más recientes y de mayor escala. Este hallazgo es coherente con la literatura revisada en el apartado de antecedentes (Ganguly & Mukherjee, 2024), que documenta la sensibilidad de los modelos de ensamble basados en árboles a la estacionalidad y a los cambios de régimen en los datos comerciales, aunque en este caso el ajuste decisivo no fue la elección del algoritmo sino la delimitación temporal de los datos de entrenamiento.

El desempeño notablemente superior del modelo de predicción de demanda de reposición (R² = 0.959) frente al de predicción de ventas (R² = 0.297) es consistente con la naturaleza de cada variable objetivo: el movimiento de inventario es una magnitud física con menor varianza exógena que la venta monetaria, que además de la operación interna refleja decisiones de precio, promociones y comportamiento del cliente no capturadas en su totalidad por las variables disponibles en el Data Warehouse actual. El modelo de recomendación de venta cruzada, con una Precision@5 de 0.077 pero una cobertura del 97.9 %, prioriza —siguiendo el hallazgo de Sri Darshan et al. (2024) sobre la utilidad de las relaciones de coocurrencia como insumo directo de personalización— la disponibilidad de al menos una sugerencia razonable en casi la totalidad de las transacciones, sobre la precisión exacta de cada sugerencia individual, una decisión de diseño explícita documentada en el proceso de selección del modelo ganador entre 31 configuraciones evaluadas.

---

## Notas de trazabilidad (no forma parte del cuerpo entregable — eliminar antes de la versión final)

- Todas las cifras de esta sección provienen de archivos reales del repositorio: `ml/REPORTE_MEJORA_MODELOS.md` (ventas v0.3.0, cross-selling v0.2.0), `docs/ml_metrics_report.md` (demanda, segmentación, churn, anomalías — no re-entrenados en la mejora posterior, según el propio `REPORTE_MEJORA_MODELOS.md` §4), `CLAUDE.md` (volumen del EDW, hallazgos de auditoría 34/37 citados en 3.5), `docs/tesis/05_desarrollo_metodologico.md` (modelo dimensional, reutilizado con adaptación de numeración a la estructura UTA).
- **Importante:** las métricas de churn/demanda/segmentación (`docs/ml_metrics_report.md`) tienen fecha de julio 2026 pero podrían haberse re-entrenado desde entonces sin que quede registrado en los documentos revisados en esta sesión — antes de la defensa, verificar contra el estado actual de `ml/models/*.meta.json` o volver a correr `ml/main.py` si el tutor lo exige.
- La Tabla 3.1 (matriz de bus) se truncó a 7 de las 11 dimensiones por espacio; la versión completa debe copiarse de `docs/tesis/05_desarrollo_metodologico.md` §2.5 si el formato final admite una tabla más ancha (o dividirse en dos tablas).
- Los tres defectos descritos en 3.5 (fuga RLS, error 500 en goals, condición de carrera Python 3.14/3.11) están tomados literalmente del changelog de `CLAUDE.md` (entradas de actualización 2026-07-15 y 2026-07-16) — son reales y verificables en el historial de auditoría del proyecto, no ejemplos genéricos.
- Pendiente: esta sección no incluye capturas de pantalla de los dashboards ni diagramas de arquitectura (Figura X); si el formato final los requiere, deben generarse a partir de la aplicación real corriendo, no describirse de memoria.
- Sección 3.8.1: la cifra de `fact_ventas_detalle` (538 862, corte 2026-07-08) es la más reciente y precisa encontrada en el repositorio (`ml/REPORTE_MEJORA_MODELOS.md`); recalcular con `SELECT COUNT(*)` contra el EDW real antes de la entrega final para reportar la cifra exacta a la fecha de cierre del proyecto.
