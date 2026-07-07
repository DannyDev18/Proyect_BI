# Propuesta de Proyecto de Titulación

Módulo inteligente de análisis, reportes y predicción de ventas basado en Ciencia de Datos y
Machine Learning.

## 1. Resumen del proyecto

El proyecto propone el desarrollo de un módulo complementario a un sistema existente de
ventas e inventario. Este módulo transformará datos transaccionales en información
estratégica mediante análisis de datos y modelos de Machine Learning, permitiendo generar
reportes descriptivos, predictivos y dashboards por roles.

## 2. Problema

La empresa cuenta con un sistema transaccional que almacena ventas, clientes, productos e
inventario, pero no aprovecha estos datos para análisis avanzado ni predicción. Esto limita
la toma de decisiones, planificación de inventario y proyección de ventas.

## 3. Objetivo general

Diseñar e implementar un módulo inteligente de analítica y predicción que permita
transformar datos operativos en conocimiento útil para la toma de decisiones.

## 4. Arquitectura general del sistema

El sistema se divide en capas bien definidas: sistema transaccional, proceso ETL, Data Warehouse, servicios analíticos y de Machine Learning, API backend y la interfaz frontend.

### DIAGRAMA DE ARQUITECTURA GENERAL

```
[Sistema Transaccional] (Fuente)
         │
         ▼
    [ETL Python]
         │
         ▼
[Data Warehouse PostgreSQL]
         │
   ┌─────┴──────────────┐
   ▼                    ▼
[Analytics]       [Machine Learning]
   │                    │
   └─────┬──────────────┘
         ▼
    [Backend API] (FastAPI) ◄─── Auth / JWT
         │
         ▼
    [Frontend] (React + TS) ◄─── Acceso por Roles (Admin, Gerente, Bodega, Ventas)
```

### 4.1. Desacoplamiento de Componentes y Automatización de Flujos

Para implementar una arquitectura profesional que separe responsabilidades y automatice los flujos de datos en el proyecto de titulación, es necesario organizar los componentes para que funcionen de forma independiente pero coordinada, aplicando las siguientes estrategias:

#### A. Desacoplamiento: Separación de Responsabilidades

El objetivo principal es asegurar la alta disponibilidad del sistema, evitando que el **Backend (FastAPI)** colapse o sufra de latencias innecesarias debido a tareas de cálculo intensivo:

- **Lógica de Machine Learning como servicio independiente:**
  - No se incluye el entrenamiento de los modelos dentro del servidor web (el backend).
  - El entrenamiento y re-entrenamiento del modelo reside en scripts dedicados en la carpeta `etl/` (o una carpeta `ml/`), ejecutándose fuera del ciclo de vida del backend.
  - Una vez entrenado, el modelo se guarda como un archivo serializado (ej: `.pkl` o `.joblib`).
  - El backend simplemente **carga este archivo** al iniciar la aplicación (o al recibir señales de actualización) para realizar inferencias (predicciones) rápidas en tiempo real.
  - **Ventaja:** Si el entrenamiento del modelo falla o consume recursos excesivos, el backend continúa sirviendo solicitudes a los usuarios de manera fluida y sin interrupciones.

#### B. Automatización: Orquestación con `docker-compose.yml`

Se utiliza la infraestructura basada en contenedores para orquestar de punta a punta todo el ciclo analítico y predictivo del proyecto de titulación:

- **Estructura de Servicios Contenedorizados:**
  - **`db`:** Contenedor de PostgreSQL que opera como Data Warehouse estructurado (EDW).
  - **`backend`:** API REST en FastAPI que consume el Data Warehouse y los modelos serializados para servir al frontend.
  - **`etl_worker`:** Contenedor dedicado exclusivamente para ejecutar las tareas de extracción, transformación y carga (ETL), así como el entrenamiento de los modelos predictivos.
- **Manejo de Tareas Programadas (Cron Jobs) en Docker:**
  - En lugar de cargar al backend con procesos en segundo plano infinitos, el servicio `etl_worker` se ejecuta de forma periódica.
  - Se puede configurar una imagen liviana con soporte a `cron` para activar el script `main.py` de la carpeta `etl/` en horarios de menor actividad operativa (ej. 3:00 AM), asegurando la constante actualización del Data Warehouse y del modelo predictivo.

#### C. Resumen de la Estructura de Directorios Propuesta

| Carpeta              | Rol y Responsabilidad                                                                                                             |
| -------------------- | --------------------------------------------------------------------------------------------------------------------------------- |
| `backend/`           | Sirve la API REST para el frontend; carga los modelos pre-entrenados para dar respuestas ultra rápidas.                           |
| `etl/`               | Contiene los scripts de Python que hacen el trabajo pesado (limpieza de datos, carga a PostgreSQL y entrenamiento de modelos).    |
| `database/`          | Scripts y configuración para el Data Warehouse en PostgreSQL.                                                                     |
| `docker-compose.yml` | Orquestador que asegura que la base de datos esté lista antes que la API se inicialice, y define la ejecución secuencial del ETL. |

Esta estrategia permite que la plataforma sea altamente **escalable** y robusta. En caso de incrementarse sustancialmente el volumen de datos históricos, es posible asignar recursos adicionales (CPU/RAM) específicamente al contenedor del `etl_worker` sin necesidad de modificar el código de la API ni la interfaz del usuario.

## 5. Sistema transaccional

Es el sistema actual de la empresa. Contiene operaciones de ventas, clientes, productos e
inventario. No será modificado, solo utilizado como fuente de datos.

## 6. Proceso ETL

Se implementará en Python el proceso ETL utilizando un enfoque de **Data-as-Code** integrado en la arquitectura del proyecto para garantizar modularidad, automatización y mantenibilidad.

### 6.1. Organización Modular del Pipeline de Datos (`etl/`)

Para evitar scripts monolíticos y asegurar que el pipeline sea fácilmente escalable, la carpeta `etl/` se estructurará como un módulo de Python subdividido en responsabilidades exclusivas:

- **`etl/extract/`**: Scripts dedicados de forma exclusiva a establecer conexiones con las fuentes transaccionales originales (por ejemplo, SAP SQL Anywhere, bases de datos remotas o archivos planos) para extraer el histórico bruto.
- **`etl/transform/`**: Lógica de limpieza, tratamiento de nulos, normalización de tipos y creación de variables de análisis (mediante librerías como `pandas` y `numpy`).
- **`etl/load/`**: Funciones encargadas de la persistencia directa de los datos transformados en el Data Warehouse estructurado.
- **`etl/main.py`**: El punto de entrada centralizado que orquesta la ejecución secuencial del flujo de extracción, transformación y carga general.
- **`etl/requirements.txt`**: Archivo de dependencias específicas e independientes de las del backend del sistema, garantizando un entorno ligero y acoplado exclusivamente al procesamiento de datos.

### 6.2. Orquestación mediante Docker (Integración con `docker-compose.yml`)

El ciclo de ejecución del pipeline de datos se integra por completo en el orquestador general de contenedores del proyecto:

- **Servicio Dedicado (`etl_job`)**: Configurado como un contenedor en `docker-compose.yml`. Puede funcionar de forma efímera (se despliega en el encendido, procesa los datos y se apaga registrando un código de salida `0`) o de manera de scheduler delegándole tareas cron de actualización nocturna.
- **Variables de Entorno Centralizadas**: El módulo `etl/` lee las credenciales del Data Warehouse y fuentes transaccionales directamente desde el archivo `.env` general de la raíz de la plataforma, impidiendo la dispersión de credenciales sensibles.

### 6.3. Automatización, Logs y Monitoreo del Estado

Con el fin de mitigar fallos silenciosos y auditar el correcto flujo batch, la administración transiciona hacia logs automatizados:

- **Centralización de Registros (Logs)**: Implementación de la librería nativa `logging` en Python que almacena las trazas de ejecución en `/etl/logs/` y registra alertas críticas o excepciones en una tabla dedicada de auditoría en la base de datos PostgreSQL.
- **Registro de Estado (Control de Ejecuciones)**: Gestión de control que guarda detalles de cada corrida (ej: `id_proceso`, `fecha_inicio`, `estado_ejecucion [EXITO/FALLIDO]`, `registros_procesados` y `tiempo_duracion`). Esto permite dar visibilidad al administrador del sistema sobre la consistencia de la ingesta de datos.

## 7. Data Warehouse

Se implementará en PostgreSQL utilizando un modelo estrella.

DIAGRAMA MODELO ESTRELLA:

Dim_Fecha
|

Dim_Producto - Fact_Ventas - Dim_Cliente
|
Dim_Sucursal

Este modelo permite consultas rápidas y análisis eficiente de grandes volúmenes de datos.

## 8. Análisis de datos

Se realizarán análisis descriptivos para responder preguntas como:

- ¿Qué productos se venden más?
- ¿Qué sucursal genera más ingresos?
- ¿Cuál es la tendencia de ventas?

Se generarán KPIs y dashboards ejecutivos.

## 9. Machine Learning

Se desarrollarán modelos predictivos en Python utilizando Scikit-learn o XGBoost.

Casos de uso:

- Predicción de ventas por producto y sucursal.
- Predicción de demanda.
- Segmentación de clientes.

Ejemplo de salida:

Producto X -> Venta estimada: 120 unidades próximas semanas

## 10. Backend

Se implementará una API REST usando FastAPI o Django.

Funciones:

- Autenticación de usuarios.
- Consulta de KPIs.
- Acceso a reportes.
- Consulta de predicciones ML.

## 11. Frontend

Se desarrollará una interfaz en React con dashboards personalizados por rol.

Roles:

- Administrador: visión global.
- Gerente: análisis estratégico.
- Bodega: inventario y alertas.
- Ventas: seguimiento comercial.

## 12. Visualización de datos

Se implementarán dashboards con gráficos de:

- Tendencias de ventas.
- Top productos.
- Predicciones.
- Inventario crítico.

## 13. Justificación de tecnologías

Se utilizarán tecnologías open source:

- Python: análisis y ML.
- PostgreSQL: data warehouse.
- FastAPI/Django: backend.
- React: frontend.

Estas tecnologías permiten escalabilidad, bajo costo y alta compatibilidad.

## 14. Metodología

Se seguirá un enfoque incremental:

1. Análisis del sistema existente.
2. Diseño del modelo de datos.
3. Implementación ETL.

4. Construcción del Data Warehouse.
5. Desarrollo de modelos ML.
6. Desarrollo del backend.
7. Desarrollo del frontend.
8. Integración y pruebas.

## 15. Conclusión

El proyecto propone una solución integral de inteligencia de negocio que combina análisis
de datos y Machine Learning para mejorar la toma de decisiones empresariales.

Ciencia de datos = etl

ML = predicciones de ventas

Desarrollo de software

Backend – frontend

Devops – contendores Docker

La propuesta más completa sería:

**Plataforma Inteligente de Analítica Comercial para Empresas Multisucursal**

Componentes:

ETL desde sistema existente

Data Warehouse en PostgreSQL

KPIs y Business Intelligence

Dashboards por rol

Análisis por sucursal

Predicción de ventas

Predicción de demanda

Segmentación de clientes

Riesgo de abandono de clientes

Alertas inteligentes

Recomendaciones de reposición de inventario

Índice de salud comercial

Con ese alcance, el proyecto deja de ser un "módulo de reportes" y se convierte en una
**plataforma de inteligencia de negocios y apoyo a la toma de decisiones basada en
Ciencia de Datos y Machine Learning** , que tiene un valor empresarial claro y una
profundidad suficiente para una tesis de titulación.

**Propuesta Inicial de Tema de Titulación**

**Título Tentativo**

Diseño e implementación de una plataforma inteligente de Business Intelligence y Machine
Learning para el análisis predictivo de ventas, inventario y comportamiento de clientes en
una empresa comercial multisucursal.

**Antecedentes**

La empresa objeto de estudio dispone actualmente de un sistema transaccional que permite
gestionar ventas, inventario, clientes y productos en múltiples sucursales. Sin embargo, la
información generada es utilizada principalmente para operaciones diarias y reportes
básicos, limitando su aprovechamiento para la toma de decisiones estratégicas.

Actualmente no existe un mecanismo que permita consolidar la información histórica de
todas las sucursales, analizar tendencias, detectar comportamientos relevantes ni generar
predicciones que apoyen la planificación comercial y logística de la organización.

**Problema de Investigación**

¿Cómo mejorar el proceso de toma de decisiones comerciales y operativas mediante la
implementación de una plataforma de análisis de datos y Machine Learning que permita
transformar datos transaccionales en información estratégica para una empresa
multisucursal?

**Objetivo General**

Diseñar e implementar una plataforma inteligente basada en Business Intelligence, Ciencia
de Datos y Machine Learning que permita analizar información histórica y generar
predicciones para apoyar la toma de decisiones en una empresa comercial con múltiples
sucursales.

**Objetivos Específicos**

1. Analizar la estructura y calidad de los datos generados por el sistema transaccional
   existente.
2. Diseñar un proceso ETL para la extracción, transformación e integración de datos
   empresariales.
3. Implementar un Data Warehouse en PostgreSQL para consolidar información
   histórica de ventas, inventario, clientes y sucursales.
4. Desarrollar dashboards interactivos segmentados por roles de usuario.
5. Aplicar técnicas de análisis de datos para la generación de indicadores clave de
   desempeño (KPIs).
6. Implementar modelos de Machine Learning para la predicción de ventas, demanda e
   identificación de patrones de comportamiento.
7. Evaluar la utilidad de la plataforma como herramienta de apoyo a la toma de
   decisiones empresariales.

**Alcance**

La investigación contempla:

- Integración de datos desde el sistema operativo existente.
- Construcción de un Data Warehouse empresarial.
- Implementación de procesos ETL en Python.
- Desarrollo de dashboards web por roles.
- Análisis de información por sucursal.
- Aplicación de modelos predictivos.

- Generación de alertas inteligentes.

No contempla la sustitución del sistema actual ni la automatización de procesos operativos
existentes.

**Arquitectura Propuesta**

Sistema Operacional Existente
→ ETL en Python
→ Data Warehouse PostgreSQL
→ Ciencia de Datos
→ Machine Learning
→ API Backend
→ Dashboards Web por Rol

**Casos de Uso de Mayor Impacto**

**Gerencia**

- Predicción de ventas por sucursal.
- Comparación de desempeño entre sucursales.
- Análisis de rentabilidad.
- Índice de salud comercial.

**Bodega**

- Predicción de demanda.
- Riesgo de desabastecimiento.
- Recomendación de reposición.
- Optimización de inventario entre sucursales.

**Ventas**

- Segmentación de clientes.
- Predicción de abandono de clientes.
- Recomendación de productos.
- Predicción de cumplimiento de metas.

**Administración**

- Auditoría de actividad.

- Detección de anomalías.
- Seguimiento de uso del sistema.

**Aporte Académico**

La investigación integra disciplinas de:

- Ingeniería de Software.
- Bases de Datos.
- Business Intelligence.
- Ciencia de Datos.
- Machine Learning.

Además, propone una arquitectura de integración de datos que transforma información
transaccional en conocimiento estratégico mediante técnicas analíticas y predictivas.

**Beneficios Esperados**

- Mejorar la toma de decisiones.
- Reducir riesgos de desabastecimiento.
- Optimizar inventarios.
- Incrementar la precisión en la planificación de compras.
- Detectar patrones de comportamiento de clientes.
- Comparar el desempeño de sucursales.
- Generar predicciones de ventas y demanda.
- Reducir tiempos de generación de reportes.

**Viabilidad**

El proyecto es técnicamente viable debido a que:

- Existe una fuente de datos real.
- Se utilizarán tecnologías open source.
- La empresa cuenta con información histórica suficiente para análisis y
  entrenamiento de modelos.
- La arquitectura propuesta es escalable y modular.

**Pregunta para Evaluación del Tutor**

¿Considera viable este enfoque como tema de titulación dentro del área de Ciencia de Datos
e Ingeniería de Software? ¿Qué ajustes metodológicos o de alcance recomienda para
fortalecer el aporte académico y la factibilidad del proyecto?
