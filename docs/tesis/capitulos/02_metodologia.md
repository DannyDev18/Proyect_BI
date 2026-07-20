# CAPÍTULO II. METODOLOGÍA

## 2.1 Materiales

Dado que la presente investigación consistió en el diseño, desarrollo y validación de una plataforma tecnológica y no en un estudio de campo con sujetos humanos, los materiales empleados correspondieron a dos categorías complementarias: la fuente de datos empresariales sobre la que se construyó y validó la solución, y el conjunto de tecnologías utilizadas para implementarla.

La fuente de datos fue el sistema transaccional en producción de la empresa objeto de estudio, soportado sobre el motor de base de datos SAP SQL Anywhere 17, del cual se validaron directamente las reglas de negocio (estados de documento, dirección de movimientos de inventario, mecánica de transferencias entre bodegas, entre otras) mediante consultas de solo lectura, sin alterar en ningún momento la operación productiva del sistema origen.

El conjunto tecnológico empleado para el desarrollo se organizó en cinco capas: (a) extracción, transformación y carga (ETL) en Python 3, con pandas, SQLAlchemy 2 y pyodbc/psycopg2 para la conexión con el origen y el destino de los datos; (b) almacenamiento analítico en PostgreSQL 16, sobre el cual se estructuró el Data Warehouse dimensional; (c) entrenamiento de modelos de Machine Learning con scikit-learn, XGBoost, LightGBM, CatBoost y Optuna; (d) una API backend desarrollada en FastAPI (Python), con SQLAlchemy 2 para el acceso a datos, Pydantic v2 para la validación de esquemas y python-jose/passlib para la autenticación; y (e) una interfaz web desarrollada en React 19 con TypeScript, Vite, Tailwind CSS, Zustand y TanStack Query. La orquestación de todos los servicios se gestionó mediante contenedores Docker coordinados con Docker Compose.

### 2.1.1 Instrumentos de recolección de la información

A diferencia de una investigación diagnóstica basada en entrevistas o encuestas a personas, el levantamiento de información de este proyecto se realizó mediante instrumentos técnicos aplicados directamente sobre los sistemas informáticos involucrados:

- **Consulta directa de solo lectura (`SELECT`) sobre la base de datos de producción del ERP**, empleada para verificar de forma empírica cada regla de negocio antes de codificarla en el proceso ETL —por ejemplo, confirmar que el campo `cantot` del kardex de inventario siempre almacena la magnitud del movimiento en positivo, y que la dirección (entrada o salida) la determina el tipo de documento (`tipdoc`), no el signo de la cantidad—, en cumplimiento de la restricción de que la base de datos transaccional de producción es de solo lectura para esta investigación.
- **Auditoría técnica documentada**, aplicada de forma sistemática a cada componente del sistema (extractores ETL, modelo dimensional, pipeline de Machine Learning, cada módulo del backend/frontend por rol de usuario) antes de intervenirlo, siguiendo un formato fijo (fecha, alcance, método, hallazgos con nivel de severidad, acción aplicada). Este instrumento generó un registro trazable de más de 30 informes de auditoría a lo largo del desarrollo del proyecto.
- **Pruebas automatizadas (`pytest`)**, empleadas como instrumento de verificación de las reglas de negocio implementadas en el backend y de la integridad del proceso ETL.

*(Nota de trazabilidad: si además se aplicaron entrevistas o encuestas formales a usuarios reales del sistema —personal de gerencia, ventas, bodega o administración— para levantar requerimientos, ese instrumento y sus resultados deben incorporarse aquí con las respuestas reales obtenidas; esta sección no fabrica un instrumento de ese tipo por no contar con evidencia verificable de su aplicación.)*

## 2.2 Métodos

La investigación combinó un método de desarrollo tecnológico —el Ciclo de Vida Dimensional de Kimball (Kimball & Ross, 2013), aplicado a la construcción del Data Warehouse— con un método de trabajo incremental por módulo de negocio. Complementariamente, y dado que el sistema ya estaba construido al momento de documentarlo, se aplicó de forma retrospectiva la metodología Hefesto (Bernabeu, 2010) como marco de verificación de las cuatro fases que exige (análisis de requerimientos, análisis del sistema transaccional origen, modelo lógico del Data Warehouse e integración de datos), confirmando que cada una tiene un entregable real dentro del proyecto ya desarrollado. El detalle del modelado dimensional resultante de aplicar el ciclo de Kimball (selección de procesos de negocio, granularidad, dimensiones y hechos) se presenta en el apartado 3.3, así como el mapeo completo de las fases de Hefesto (3.3.6 — borrador, pendiente de profundizar), siguiendo la convención de esta estructura de tesis en la que el diseño de la arquitectura del subsistema se documenta como resultado del proceso metodológico, no dentro del propio capítulo de Metodología. Cada componente funcional del sistema (Gerencia, Ventas, Bodega, Administrador, Metas y Comisiones, Notificaciones) se desarrolló, auditó y validó de forma independiente y secuencial contra las reglas de negocio reales del ERP, antes de integrarse al conjunto de la plataforma, de modo que cada ciclo de auditoría documentada (ver 2.1.1) funcionó como punto de control de calidad entre módulos.

### 2.2.1 Modalidad de la investigación

La investigación adoptó una modalidad aplicada, con un enfoque predominantemente cuantitativo.

**a. Investigación aplicada.** El proyecto se orientó al diseño, desarrollo e implementación de una plataforma tecnológica funcional —no a la generación de conocimiento teórico nuevo— que resuelve un problema operativo concreto de la empresa objeto de estudio: la falta de aprovechamiento analítico de los datos transaccionales generados por su sistema ERP. El enfoque aplicado se materializó en la construcción de un pipeline ETL, un Data Warehouse dimensional, seis modelos de Machine Learning entrenados y publicados, una API backend con autenticación y control de acceso por rol, y una interfaz web con dashboards diferenciados para los cuatro roles de negocio de la organización.

**b. Enfoque cuantitativo predominante.** La evaluación técnica de cada componente se sustentó en mediciones objetivas: cobertura y volumen de registros cargados por el ETL, coeficiente de determinación (R²) y error absoluto medio (MAE) de los modelos de regresión, exactitud y área bajo la curva ROC de los modelos de clasificación, y tiempos de respuesta de los endpoints de la API. El componente cualitativo se limitó a la fase de análisis de requerimientos y validación de reglas de negocio, documentada mediante el instrumento de auditoría técnica descrito en 2.1.1, sin recurrir a técnicas de investigación social (entrevistas o encuestas) que no fueron aplicadas en el desarrollo de este proyecto.

### 2.2.2 Población y muestra

A diferencia de una investigación con sujetos humanos, la "población" de este estudio corresponde al universo de registros transaccionales históricos disponibles en el sistema ERP de la empresa objeto de estudio, consolidados en el Data Warehouse mediante un proceso de carga censal —es decir, sin muestreo probabilístico—: el ETL incorpora la totalidad de los documentos en estado válido (`estado = 'P'`, Procesada) del período histórico configurado, sin excluir registros por conveniencia. La Tabla 2.1 resume el volumen de las dos tablas de hechos principales del Data Warehouse al cierre de la fase de carga documentada en este proyecto.

**Tabla 2.1**
*Volumen de registros de las tablas de hechos principales del Data Warehouse*

| Tabla de hechos | Registros | Descripción |
|---|---|---|
| `fact_ventas_detalle` | 538 862 | Detalle línea a línea de las transacciones de venta, hecho principal del modelo |
| `fact_movimientos_inventario` | ~948 000 | Movimientos de kardex (entradas, salidas y transferencias) por bodega |

*Nota.* Elaboración propia a partir del estado del Data Warehouse documentado en `ml/REPORTE_MEJORA_MODELOS.md` y `CLAUDE.md` del repositorio del proyecto (corte 2026-07-08 para `fact_ventas_detalle`). La cifra exacta se repite en la Tabla 3.2 de resultados (3.8.1); `fact_movimientos_inventario` se mantiene aproximada por no contar con un recuento exacto documentado en las fuentes revisadas.

Complementariamente, la población de usuarios de la plataforma desarrollada se circunscribe a los cuatro roles de negocio cerrados de la organización —gerencia, ventas, bodega y administrador—, cada uno con acceso a un subconjunto de datos y funcionalidades acorde a sus responsabilidades, conforme al modelo de control de acceso basado en roles descrito en 1.3.9.

### 2.2.3 Recolección de información

La recolección de información técnica se ejecutó en dos frentes complementarios, sintetizados en la Tabla 2.2.

**Tabla 2.2**
*Parámetros de la recolección de información técnica*

| Preguntas básicas | Explicación |
|---|---|
| ¿Para qué? | Para validar empíricamente las reglas de negocio del ERP antes de codificarlas en el ETL, y para verificar la integridad y el desempeño de cada componente desarrollado. |
| ¿Sobre qué aspectos? | Reglas de negocio del sistema transaccional (estados de documento, dirección de movimientos de inventario, mecánica de transferencias, entre otras), estructura del modelo dimensional, y calidad/desempeño de los modelos de Machine Learning. |
| ¿Con qué? | Consultas `SELECT` de solo lectura sobre la base de datos de producción del ERP, revisión de esquema del EDW, y pruebas automatizadas (`pytest`). |
| ¿Cuándo? | De forma iterativa, antes de intervenir cada componente del sistema (ver 2.1.1), a lo largo del desarrollo del proyecto. |
| ¿Con qué restricción? | La base de datos de producción del ERP se trató en todo momento como de solo lectura: ninguna operación de escritura (`INSERT`, `UPDATE`, `DELETE`, `ALTER`) se ejecutó sobre ella durante la investigación. |

Cada regla de negocio validada mediante consulta directa quedó documentada de forma trazable, referenciando la evidencia empírica que la sustenta, en lugar de asumirse a partir del código o la documentación preexistente del sistema.

### 2.2.4 Procesamiento y análisis de datos

El procesamiento de los datos siguió el flujo de extracción, transformación y carga descrito en 1.3.4: la extracción recuperó la información desde el ERP mediante consultas parametrizadas; la transformación aplicó las reglas de negocio validadas en la fase de recolección (2.2.3) y resolvió las dimensiones de variación lenta de tipo 2 para preservar el historial de cambios en productos y clientes; y la carga insertó los datos de forma incremental e idempotente en el modelo dimensional del Data Warehouse, evitando duplicados ante ejecuciones repetidas del proceso.

Sobre el Data Warehouse resultante se entrenaron los modelos de Machine Learning descritos en 1.3.5 a 1.3.8, cada uno evaluado con la métrica apropiada a su tipo de problema: los modelos de regresión (predicción de ventas y de demanda) se evaluaron mediante el coeficiente de determinación (R²) y el error absoluto medio (MAE) sobre una partición de prueba no vista durante el entrenamiento; los modelos de clasificación (predicción de abandono de clientes) se evaluaron mediante exactitud y área bajo la curva ROC; y el modelo de segmentación de clientes (K-means sobre variables RFM) se evaluó mediante inspección de la coherencia interna de los clústeres resultantes. La ventana de entrenamiento del modelo de predicción de ventas se acotó a los últimos tres años de historial, decisión que se justifica y cuantifica en el capítulo de Resultados con la mejora de desempeño observada frente a una ventana de entrenamiento más amplia.

---

## Notas de trazabilidad (no forma parte del cuerpo entregable — eliminar antes de la versión final)

- Este capítulo se redactó reconociendo que el proyecto es una investigación aplicada de desarrollo tecnológico, no un estudio de campo con entrevistas/encuestas a personas (a diferencia del formato de referencia UTA, que sí las aplicó). No se fabricó ningún instrumento ni respuesta de entrevista.
- Fuentes reales usadas: `CLAUDE.md` (stack tecnológico, volumen de `fact_ventas_detalle`/`fact_movimientos_inventario`, regla 9 de RBAC, restricción de solo lectura sobre Producción, flujo de trabajo de 8 pasos con auditoría previa a cada cambio), `docs/auditoria/` (más de 30 informes reales, formato fecha/alcance/método/hallazgos/acción citado literalmente de `CLAUDE.md` §Auditoría), `docs/tesis/05_desarrollo_metodologico.md` (Ciclo de Vida Dimensional de Kimball ya adoptado en el proyecto — el detalle completo del modelado dimensional se remite a 3.3 en el capítulo de Resultados, siguiendo la estructura UTA donde el diseño de arquitectura pertenece a Resultados, no a Metodología).
- **Pendiente de decisión del usuario:** si existieron entrevistas o encuestas reales a usuarios de negocio (gerencia/ventas/bodega/administración) para el levantamiento de requerimientos, deben agregarse en 2.1.1 con las respuestas reales — no se inventaron aquí. Si no existieron, el capítulo puede quedar tal como está.
- La Tabla 2.1 usa las cifras aproximadas de `CLAUDE.md`; deben recalcularse contra el EDW real (`SELECT COUNT(*)`) al cerrar el capítulo de Resultados para reportar la cifra exacta y la fecha de corte.
