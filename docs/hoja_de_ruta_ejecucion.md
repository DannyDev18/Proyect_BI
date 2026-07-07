# Hoja de Ruta de Ejecución: Plataforma Inteligente de Analítica Empresarial y Predicción de Ventas

> **Proyecto de Tesis:** Plataforma Inteligente de Analítica Empresarial y Predicción de Ventas para Empresas Multisucursal  
> **Arquitectura:** SAP SQL Anywhere → ETL Python → EDW PostgreSQL → FastAPI → React/TypeScript  
> **Versión del Plan:** 1.0 — Fecha: 2026-06-30  
> **Duración estimada total:** 20–24 semanas

---

## Tabla de Contenido

1. [Fase 1: Configuración del Entorno y Arquitectura Base](#fase-1) — Semanas 1-2
2. [Fase 2: Ingeniería de Datos (ETL y Data Warehouse)](#fase-2) — Semanas 3-6
3. [Fase 3: Ciencia de Datos y Machine Learning](#fase-3) — Semanas 7-10
4. [Fase 4: Desarrollo del Backend (FastAPI)](#fase-4) — Semanas 11-14
5. [Fase 5: Desarrollo del Frontend (React/TypeScript)](#fase-5) — Semanas 15-18
6. [Fase 6: Despliegue e Integración Continua](#fase-6) — Semanas 19-20
7. [Fase 7: Documentación y Validación de la Tesis](#fase-7) — Semanas 21-24

---

## Prerequisitos Globales

Antes de comenzar cualquier fase, verificar que el entorno del desarrollador tiene instalado:

- **Docker Desktop** ≥ 25.x y **Docker Compose** ≥ 2.x
- **Python** ≥ 3.11 + **pip** / **pyenv**
- **Node.js** ≥ 20 LTS + **npm** ≥ 10
- **Git** ≥ 2.40 y acceso a un repositorio remoto (GitHub/GitLab)
- **VS Code** con extensiones: Python, ESLint, Prettier, Docker, PostgreSQL (cweijan)
- **DBeaver** o **pgAdmin 4** para administración del EDW
- Acceso ODBC al servidor SAP SQL Anywhere de la empresa (driver SQL Anywhere 17)

---

<a name="fase-1"></a>

## Fase 1: Configuración del Entorno y Arquitectura Base

> **Duración estimada:** Semanas 1–2  
> **Objetivo:** Tener el entorno de desarrollo local completamente operativo, el repositorio estructurado y los contenedores base corriendo.

---

### 1.1 Estructura del Repositorio (Monorepo)

Se usará un **monorepo** para centralizar el control de versiones de todos los componentes del proyecto.

```bash
# Crear el directorio raíz y entrar
mkdir plataforma-bi-multisucursal && cd plataforma-bi-multisucursal

# Inicializar Git
git init
git branch -M main
```

**Estructura de carpetas final del monorepo:**

```
plataforma-bi-multisucursal/
│
├── .env.example                   # Variables de entorno de referencia
├── .gitignore
├── docker-compose.yml             # Orquestación de todos los servicios
├── docker-compose.override.yml    # Overrides para desarrollo local
│
├── etl/                           # Pipeline ETL (Python)
│   ├── config/
│   │   ├── settings.py
│   │   └── logging_config.py
│   ├── connectors/
│   │   ├── sqlany_connector.py
│   │   └── postgres_connector.py
│   ├── extractors/
│   │   ├── dim_extractor.py
│   │   └── fact_extractor.py
│   ├── transformers/
│   │   ├── dim_transformer.py
│   │   ├── fact_transformer.py
│   │   └── dim_tiempo.py
│   ├── loaders/
│   │   └── pg_loader.py
│   ├── tests/
│   │   ├── test_transformers.py
│   │   └── test_loaders.py
│   ├── orchestrator.py
│   ├── Dockerfile
│   └── requirements.txt
│
├── ml/                            # Modelos de Machine Learning
│   ├── notebooks/                 # Jupyter Notebooks para EDA y prototipado
│   ├── models/                    # Modelos serializados (.joblib)
│   ├── src/
│   │   ├── features/              # Feature engineering
│   │   ├── training/              # Scripts de entrenamiento
│   │   └── prediction/            # Lógica de inferencia
│   ├── Dockerfile
│   └── requirements.txt
│
├── backend/                       # API REST (FastAPI)
│   ├── app/
│   │   ├── api/
│   │   │   ├── v1/
│   │   │   │   ├── endpoints/
│   │   │   │   │   ├── auth.py
│   │   │   │   │   ├── kpis.py
│   │   │   │   │   ├── predictions.py
│   │   │   │   │   └── admin.py
│   │   │   │   └── router.py
│   │   ├── core/
│   │   │   ├── config.py
│   │   │   ├── security.py        # JWT + hashing
│   │   │   └── dependencies.py    # RBAC dependencies
│   │   ├── db/
│   │   │   └── session.py         # SQLAlchemy engine
│   │   ├── models/                # ORM models (EDW read-only)
│   │   ├── schemas/               # Pydantic schemas
│   │   ├── services/              # Business logic
│   │   └── main.py
│   ├── Dockerfile
│   └── requirements.txt
│
├── frontend/                      # SPA React + TypeScript
│   ├── public/
│   ├── src/
│   │   ├── api/                   # Axios clients
│   │   ├── components/            # Componentes reutilizables
│   │   ├── pages/                 # Vistas por rol
│   │   ├── store/                 # Estado global (Zustand/Redux)
│   │   ├── hooks/
│   │   └── types/
│   ├── Dockerfile
│   ├── nginx.conf
│   └── package.json
│
├── edw/                           # Scripts DDL del Data Warehouse
│   ├── 01_schema.sql
│   ├── 02_dimensiones.sql
│   ├── 03_hechos.sql
│   ├── 04_indices.sql
│   └── 05_etl_control.sql
│
└── docs/                          # Documentación técnica y de tesis
    ├── propuesta_tesis.md
    ├── EDW_Diseno_Completo.md
    └── hoja_de_ruta_ejecucion.md  ← Este documento
```

**Archivos base iniciales:**

```bash
# .gitignore esencial
cat > .gitignore << 'EOF'
# Python
__pycache__/
*.py[cod]
.venv/
*.egg-info/
dist/
.env

# Node
node_modules/
dist/
.next/

# ML
*.joblib
*.pkl
ml/models/*.joblib

# Docker
*.log

# IDE
.vscode/settings.json
.idea/
EOF
```

---

### 1.2 Variables de Entorno Centralizadas

Crear el archivo `.env.example` que servirá como plantilla. **Nunca versionar el `.env` real.**

```bash
# .env.example — Copiar a .env y rellenar valores reales
# ── SAP SQL Anywhere (Origen) ──────────────────────────────────
SQLANY_DSN=MyDSN_Empresa
SQLANY_HOST=192.168.1.100
SQLANY_PORT=2638
SQLANY_DB=empresa_prod
SQLANY_USER=dba
SQLANY_PASSWORD=CHANGE_ME
CODEMP=01

# ── PostgreSQL EDW ──────────────────────────────────────────────
PG_HOST=postgres_edw
PG_PORT=5432
PG_DB=edw
PG_USER=etl_user
PG_PASSWORD=CHANGE_ME
PG_SCHEMA=edw

# ── Backend (FastAPI) ───────────────────────────────────────────
SECRET_KEY=CHANGE_ME_32CHARS_RANDOM
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=480
BACKEND_CORS_ORIGINS=["http://localhost:5173","http://localhost:80"]

# ── PostgreSQL App (Usuarios/Auth del sistema BI) ───────────────
APP_DB_HOST=postgres_app
APP_DB_PORT=5432
APP_DB_NAME=bi_app
APP_DB_USER=bi_user
APP_DB_PASSWORD=CHANGE_ME

# ── ETL Control ─────────────────────────────────────────────────
BATCH_SIZE=10000
FECHA_DESDE=2020-01-01
MODO_INCREMENTAL=true

# ── Cloudinary (avatares/assets) ────────────────────────────────
CLOUDINARY_CLOUD_NAME=
CLOUDINARY_API_KEY=
CLOUDINARY_API_SECRET=
```

---

### 1.3 Configuración de Docker Compose

Este es el corazón del entorno local. Define todos los servicios necesarios.

```yaml
# docker-compose.yml
version: "3.9"

services:
  # ── 1. PostgreSQL — Data Warehouse (EDW) ────────────────────────
  postgres_edw:
    image: postgres:16-alpine
    container_name: bi_postgres_edw
    restart: unless-stopped
    environment:
      POSTGRES_DB: edw
      POSTGRES_USER: etl_user
      POSTGRES_PASSWORD: ${PG_PASSWORD}
    volumes:
      - edw_data:/var/lib/postgresql/data
      - ./edw:/docker-entrypoint-initdb.d # Ejecuta DDL al iniciar
    ports:
      - "5433:5432" # Expone en 5433 para no colisionar con PG local
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U etl_user -d edw"]
      interval: 10s
      timeout: 5s
      retries: 5

  # ── 2. PostgreSQL — Base de datos de la Aplicación (Auth/Usuarios) ─
  postgres_app:
    image: postgres:16-alpine
    container_name: bi_postgres_app
    restart: unless-stopped
    environment:
      POSTGRES_DB: bi_app
      POSTGRES_USER: bi_user
      POSTGRES_PASSWORD: ${APP_DB_PASSWORD}
    volumes:
      - app_data:/var/lib/postgresql/data
    ports:
      - "5434:5432"
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U bi_user -d bi_app"]
      interval: 10s
      timeout: 5s
      retries: 5

  # ── 3. Backend FastAPI ──────────────────────────────────────────
  backend:
    build:
      context: ./backend
      dockerfile: Dockerfile
    container_name: bi_backend
    restart: unless-stopped
    env_file: .env
    depends_on:
      postgres_edw:
        condition: service_healthy
      postgres_app:
        condition: service_healthy
    ports:
      - "8000:8000"
    volumes:
      - ./backend:/app # Hot-reload en desarrollo
      - ./ml/models:/app/ml_models:ro

  # ── 4. Frontend React ────────────────────────────────────────────
  frontend:
    build:
      context: ./frontend
      dockerfile: Dockerfile
    container_name: bi_frontend
    restart: unless-stopped
    ports:
      - "5173:5173"
    volumes:
      - ./frontend/src:/app/src # Hot-reload Vite
    depends_on:
      - backend

  # ── 5. ETL Runner (ejecución manual o programada) ───────────────
  etl:
    build:
      context: ./etl
      dockerfile: Dockerfile
    container_name: bi_etl
    env_file: .env
    depends_on:
      postgres_edw:
        condition: service_healthy
    # No se inicia automáticamente; se ejecuta con: docker compose run etl
    profiles: ["etl"]

volumes:
  edw_data:
  app_data:
```

**Levantar el entorno base:**

```bash
# Copiar variables de entorno
cp .env.example .env
# Editar .env con tus credenciales reales

# Levantar solo los servicios de base de datos y backend
docker compose up -d postgres_edw postgres_app backend frontend

# Verificar estado
docker compose ps
docker compose logs -f backend
```

---

### 1.4 Dockerfiles de cada Servicio

**ETL y ML — `etl/Dockerfile`:**

```dockerfile
FROM python:3.11-slim

WORKDIR /app

# Instalar dependencias del sistema (ODBC para SAP SQL Anywhere)
RUN apt-get update && apt-get install -y \
    unixodbc unixodbc-dev gcc \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["python", "orchestrator.py"]
```

**Backend — `backend/Dockerfile`:**

```dockerfile
FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y libpq-dev gcc \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
```

**Frontend — `frontend/Dockerfile` (dev):**

```dockerfile
FROM node:20-alpine

WORKDIR /app

COPY package*.json ./
RUN npm ci

COPY . .

EXPOSE 5173
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0"]
```

---

### 1.5 Control de Versiones — Estrategia de Branching

Usar **Git Flow simplificado**:

| Rama                   | Propósito                                   |
| ---------------------- | ------------------------------------------- |
| `main`                 | Código estable, solo merges desde `develop` |
| `develop`              | Integración continua de features            |
| `feature/etl-pipeline` | Desarrollo del ETL                          |
| `feature/ml-models`    | Desarrollo de modelos ML                    |
| `feature/backend-api`  | Desarrollo de la API                        |
| `feature/frontend-ui`  | Desarrollo del frontend                     |

```bash
git checkout -b develop
git checkout -b feature/etl-pipeline
```

**Entregable de la Fase 1:** Repositorio inicializado, `docker compose up` levanta PostgreSQL (EDW + App), backend corriendo en `http://localhost:8000/docs` con respuesta `{"status": "ok"}`.

---

<a name="fase-2"></a>

## Fase 2: Ingeniería de Datos — ETL y Data Warehouse

> **Duración estimada:** Semanas 3–6  
> **Objetivo:** Tener el EDW completamente creado en PostgreSQL, el pipeline ETL funcional extrayendo datos desde SAP SQL Anywhere, y la primera carga histórica completada.

---

### 2.1 Creación del Schema DDL en PostgreSQL

Los scripts DDL se ubican en `edw/` y son ejecutados automáticamente por Docker al inicializar el contenedor `postgres_edw`.

**Paso 1 — Crear el schema aislado:**

```sql
-- edw/01_schema.sql
CREATE SCHEMA IF NOT EXISTS edw;
COMMENT ON SCHEMA edw IS 'Enterprise Data Warehouse — Constelación de Hechos';

-- Usuario de solo lectura para el backend
CREATE ROLE bi_readonly LOGIN PASSWORD 'CHANGE_ME_READONLY';
GRANT CONNECT ON DATABASE edw TO bi_readonly;
GRANT USAGE ON SCHEMA edw TO bi_readonly;
ALTER DEFAULT PRIVILEGES IN SCHEMA edw
    GRANT SELECT ON TABLES TO bi_readonly;
```

**Paso 2 — Dimensiones (orden de creación obligatorio, sin FKs cruzadas entre dims):**

```sql
-- edw/02_dimensiones.sql
-- Ejecutar en este orden exacto:
-- 1. Dim_Tiempo (sin dependencias)
-- 2. Dim_Sucursal
-- 3. Dim_Cliente (SCD-2)
-- 4. Dim_Producto (SCD-2)
-- 5. Dim_Categoria
-- 6. Dim_Vendedor
-- 7. Dim_Proveedor
-- 8. Dim_Almacen
-- 9. Dim_Empleado
-- 10. Dim_FormaPago
-- 11. Dim_Geografia
-- 12. Dim_Usuario
```

> ⚠️ **Nota crítica:** Los scripts DDL completos están definidos en `docs/EDW_Diseno_Completo.md` sección 1.2.  
> Copiar cada bloque `CREATE TABLE edw.Dim_*` en el orden listado arriba.

**Paso 3 — Tablas de Hechos (dependen de las dimensiones):**

```sql
-- edw/03_hechos.sql
-- Orden de creación (respetar FKs):
-- 1. Fact_Ventas_Detalle      (FK: 6 dimensiones)
-- 2. Fact_Devoluciones
-- 3. Fact_Compras
-- 4. Fact_Movimientos_Inventario
-- 5. Fact_Inventario_Snapshot
-- 6. Fact_Cobros_CXC
-- 7. Fact_Pagos_CXP
-- 8. Fact_Movimientos_Caja
-- 9. Fact_Metas_Comerciales
-- 10. Fact_Logs_Auditoria
-- 11. Fact_Nomina
```

**Paso 4 — Índices para rendimiento de consultas analíticas:**

```sql
-- edw/04_indices.sql
-- Ya incluidos en el DDL de Fact_Ventas_Detalle, Fact_Movimientos_Inventario y Fact_Logs_Auditoria
-- Agregar índices compuestos para patrones de consulta frecuentes:

CREATE INDEX idx_fvd_tiempo_sucursal
    ON edw.Fact_Ventas_Detalle(tiempo_sk, sucursal_sk);

CREATE INDEX idx_fvd_producto_tiempo
    ON edw.Fact_Ventas_Detalle(producto_sk, tiempo_sk);

CREATE INDEX idx_fis_producto_almacen
    ON edw.Fact_Inventario_Snapshot(producto_sk, almacen_sk, tiempo_sk);

-- Índice parcial para registros vigentes en dimensiones SCD-2
CREATE INDEX idx_dim_cliente_vigente
    ON edw.Dim_Cliente(codcli) WHERE es_vigente = TRUE;

CREATE INDEX idx_dim_producto_vigente
    ON edw.Dim_Producto(codart) WHERE es_vigente = TRUE;
```

**Paso 5 — Tabla de control ETL:**

```sql
-- edw/05_etl_control.sql
CREATE TABLE edw.etl_control (
    id              SERIAL PRIMARY KEY,
    tabla_destino   VARCHAR(60) NOT NULL,
    ultimo_etl_ok   TIMESTAMP,
    registros_carg  BIGINT DEFAULT 0,
    estado          VARCHAR(15),
    duracion_seg    INTEGER,
    mensaje_error   TEXT,
    fecha_ejecucion TIMESTAMP DEFAULT NOW()
);
```

**Verificar la estructura creada:**

```bash
# Conectar al contenedor y verificar
docker exec -it bi_postgres_edw psql -U etl_user -d edw \
  -c "\dt edw.*" \
  -c "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = 'edw';"
```

---

### 2.2 Implementar el Pipeline ETL en Python

**Paso 1 — Configurar el entorno virtual del ETL:**

```bash
cd etl/
python -m venv .venv
source .venv/bin/activate    # Linux/macOS
# .venv\Scripts\activate     # Windows

pip install -r requirements.txt
```

**`etl/requirements.txt`:**

```
pyodbc>=5.0.0
sqlalchemy>=2.0.0
psycopg2-binary>=2.9.0
pandas>=2.0.0
numpy>=1.26.0
python-dotenv>=1.0.0
pytest>=7.4.0
pytest-mock>=3.11.0
```

**Paso 2 — Módulo de configuración (`etl/config/settings.py`):**

El código completo está definido en `docs/EDW_Diseno_Completo.md` sección 4.2. Puntos clave:

- Todas las variables provienen de variables de entorno (`.env`)
- `MODO_INCREMENTAL=true` controla la carga diferencial
- `FECHA_DESDE` define la ventana temporal mínima de extracción para hechos

**Paso 3 — Conector SAP SQL Anywhere (`etl/connectors/sqlany_connector.py`):**

> Código completo en `docs/EDW_Diseno_Completo.md` sección 4.3.

Consideraciones críticas de implementación:

```python
# Verificar que el driver ODBC esté instalado en el sistema
import pyodbc
print(pyodbc.drivers())
# Debe aparecer: ['SQL Anywhere 17'] o similar

# String de conexión para SQL Anywhere vía ODBC directo (sin DSN)
connstr = (
    "DRIVER={SQL Anywhere 17};"
    f"HOST={host}:{port};"
    f"DBN={db_name};"
    f"UID={user};"
    f"PWD={password};"
    "CHARSET=UTF-8;"
    "COMMLINKS=tcpip;"   # Forzar protocolo TCP/IP
)
```

**Paso 4 — Conector PostgreSQL (`etl/connectors/postgres_connector.py`):**

> Código completo en `docs/EDW_Diseno_Completo.md` sección 4.4.

Los tres modos de carga implementados:

| Modo       | Cuándo usarlo                              | Tablas objetivo                                      |
| ---------- | ------------------------------------------ | ---------------------------------------------------- |
| `truncate` | Dimensiones pequeñas, recargas completas   | `Dim_Vendedor`, `Dim_FormaPago`, `Dim_Almacen`       |
| `upsert`   | Dimensiones SCD-2, hechos actualizables    | `Dim_Cliente`, `Dim_Producto`, `Fact_Ventas_Detalle` |
| `append`   | Hechos de solo inserción (logs, auditoria) | `Fact_Logs_Auditoria`, `Fact_Movimientos_Inventario` |

**Paso 5 — Transformadores de Dimensiones (`etl/transformers/dim_transformer.py`):**

```python
# etl/transformers/dim_transformer.py
import pandas as pd
import numpy as np
from .utils import normalizar_fechas, normalizar_numericos, normalizar_strings, deduplicar

def transformar_clientes(df: pd.DataFrame) -> pd.DataFrame:
    """Transforma el DataFrame extraído de SAP → modelo Dim_Cliente."""
    df = deduplicar(df, clave_natural=['codemp', 'codcli'])
    df = normalizar_strings(df, ['nomcli', 'dircli', 'ciucli', 'mail'])
    df = normalizar_fechas(df, ['fecnac', 'fecult'])
    df = normalizar_numericos(df, ['limcre', 'dias'])

    # Renombrar columnas al esquema del EDW
    df = df.rename(columns={
        'nomcli':    'nombre_cliente',
        'rucced':    'ruc_cedula',
        'tiprucced': 'tipo_id',
        'codcla':    'clase_cliente',
        'nomcla':    'nombre_clase',
        'codzona':   'zona',
        'nomzon':    'nombre_zona',
        'ciucli':    'ciudad',
        'dircli':    'direccion',
        'telcli':    'telefono',
        'mail':      'email',
        'limcre':    'limite_credito',
        'dias':      'dias_credito',
        'lispre':    'lista_precio',
        'codven':    'vendedor_asig',
        'codcob':    'cobrador_asig',
        'sexo':      'sexo',
        'fecnac':    'fecha_nacimiento',
        'parterel':  'parte_relacionada',
    })

    # SCD Tipo 2: marcar todos como vigentes en la carga inicial
    df['fecha_inicio_vigencia'] = pd.Timestamp.today().date()
    df['fecha_fin_vigencia']    = None
    df['es_vigente']            = True

    return df


def transformar_productos(df: pd.DataFrame) -> pd.DataFrame:
    """Transforma el DataFrame de artículos → modelo Dim_Producto."""
    df = deduplicar(df, clave_natural=['codemp', 'codart'])
    df = normalizar_strings(df, ['nomart', 'codalt', 'codbar'])
    df = normalizar_numericos(df, [
        'prec01', 'prec02', 'prec03', 'prec04',
        'precio', 'cospro', 'ultcos', 'exiact',
        'eximin', 'eximax', 'punreo', 'peso', 'poriva'
    ])

    df = df.rename(columns={
        'nomart':    'nombre_articulo',
        'codalt':    'codigo_alterno',
        'codbar':    'codigo_barra',
        'nomcla':    'nombre_clase',
        'nomsubcla': 'nombre_subclase',
        'coduni':    'unidad',
        'nomuni':    'nombre_unidad',
        'codiva':    'aplica_iva',
        'poriva':    'porcentaje_iva',
        'prec01':    'precio_1',
        'prec02':    'precio_2',
        'prec03':    'precio_3',
        'prec04':    'precio_4',
        'precio':    'precio_oficial',
        'cospro':    'costo_promedio',
        'produ':     'es_produccion',
        'bienser':   'es_servicio',
    })

    df['aplica_ice'] = df.get('codice', pd.Series(dtype=str)).notna()
    df['es_produccion'] = df['es_produccion'].map({'S': True, 'N': False}).fillna(False)
    df['es_servicio']   = df['es_servicio'].map({'S': True, 'N': False}).fillna(False)
    df['fecha_inicio_vigencia'] = pd.Timestamp.today().date()
    df['fecha_fin_vigencia']    = None
    df['es_vigente']            = True

    return df
```

**Paso 6 — Transformador de Hechos (`etl/transformers/fact_transformer.py`):**

> Código base en `docs/EDW_Diseno_Completo.md` sección 3.1.4.

Lógica adicional para `transformar_ventas`:

```python
def transformar_ventas(df: pd.DataFrame) -> pd.DataFrame:
    """Pipeline de transformación para Fact_Ventas_Detalle."""
    df = normalizar_fechas(df, ['fecha_factura'])
    df = normalizar_numericos(df, [
        'cantidad', 'precio_unitario', 'costo_unitario',
        'pct_descuento', 'valor_iva', 'valor_ice', 'costo_total'
    ])

    # Calcular campos derivados
    df['subtotal_neto']  = df['cantidad'] * df['precio_unitario'] * (1 - df['pct_descuento'] / 100)
    df['valor_descuento']= df['cantidad'] * df['precio_unitario'] * (df['pct_descuento'] / 100)
    df['total_linea']    = df['subtotal_neto'] + df['valor_iva'] + df['valor_ice']
    df['margen_bruto']   = df['subtotal_neto'] - df['costo_total']
    df['pct_margen']     = np.where(
        df['subtotal_neto'] != 0,
        (df['margen_bruto'] / df['subtotal_neto'] * 100).round(4),
        0.0
    )

    # Filtrar registros inválidos
    df = df[df['cantidad'] != 0].copy()
    df['es_devolucion'] = df['cantidad'] < 0
    df['cantidad']      = df['cantidad'].abs()

    # Renombrar clave natural
    df = df.rename(columns={'numfac': 'num_factura', 'numren': 'num_renglon'})

    return df
```

**Paso 7 — Generador de Dim_Tiempo (`etl/transformers/dim_tiempo.py`):**

> Código completo en `docs/EDW_Diseno_Completo.md` sección 3.1.3.

```bash
# Probar el generador de forma aislada
python -c "
from etl.transformers.dim_tiempo import generar_dim_tiempo
df = generar_dim_tiempo('2010-01-01', '2030-12-31')
print(f'Filas generadas: {len(df)}')
print(df.head())
"
```

---

### 2.3 Estrategia de Carga: Histórica vs. Incremental

#### Carga Histórica (Primera Ejecución)

Ejecutar una sola vez para poblar el EDW con todo el historial disponible:

```bash
# Configurar variables para carga completa
export MODO_INCREMENTAL=false
export FECHA_DESDE=2015-01-01   # Ajustar al inicio del historial disponible

# Ejecutar el orquestador
cd etl/
python orchestrator.py

# O via Docker
docker compose run --rm etl python orchestrator.py
```

**Orden recomendado para la carga histórica:**

1. `Dim_Tiempo` (generación algorítmica — sin conexión SAP)
2. `Dim_Sucursal`, `Dim_Almacen`, `Dim_FormaPago` (tablas pequeñas)
3. `Dim_Cliente`, `Dim_Producto`, `Dim_Vendedor`, `Dim_Proveedor`
4. `Dim_Categoria`, `Dim_Empleado`, `Dim_Usuario`
5. `Fact_Movimientos_Inventario` (Kardex — tabla más grande, procesar en chunks)
6. `Fact_Ventas_Detalle` (segunda tabla más grande)
7. `Fact_Compras`, `Fact_Devoluciones`
8. `Fact_Cobros_CXC`, `Fact_Pagos_CXP`
9. `Fact_Movimientos_Caja`, `Fact_Metas_Comerciales`
10. `Fact_Inventario_Snapshot` (snapshot del estado actual)
11. `Fact_Logs_Auditoria`

#### Carga Incremental (Ejecuciones Diarias)

```python
# etl/orchestrator.py — Función de carga incremental
def get_fecha_desde_control(pg: PostgresConnector, tabla: str) -> str:
    """Obtiene la fecha del último ETL exitoso para una tabla."""
    engine = pg.connect()
    result = engine.execute(
        "SELECT ultimo_etl_ok FROM edw.etl_control "
        "WHERE tabla_destino = %s AND estado = 'SUCCESS' "
        "ORDER BY fecha_ejecucion DESC LIMIT 1",
        (tabla,)
    ).fetchone()
    if result:
        return result[0].strftime('%Y-%m-%d')
    return "2020-01-01"  # Fallback
```

**Frecuencias de carga por tabla** (definidas en `docs/EDW_Diseno_Completo.md` sección 4.7):

| Tabla                         | Frecuencia   | Modo                     |
| ----------------------------- | ------------ | ------------------------ |
| `Dim_Tiempo`                  | Anual        | Generación algorítmica   |
| `Dim_Cliente`, `Dim_Producto` | Diaria       | Upsert SCD-2             |
| `Fact_Ventas_Detalle`         | Diaria       | Upsert por ventana fecha |
| `Fact_Movimientos_Inventario` | Cada 4 horas | Append incremental       |
| `Fact_Inventario_Snapshot`    | Mensual      | Truncate + Snapshot      |
| `Fact_Logs_Auditoria`         | Cada hora    | Append                   |

---

### 2.4 Pruebas Unitarias del ETL

```python
# etl/tests/test_transformers.py
import pytest
import pandas as pd
import numpy as np
from transformers.dim_transformer import transformar_clientes, transformar_productos
from transformers.fact_transformer import transformar_ventas

# ── Fixtures ────────────────────────────────────────────────────────────────
@pytest.fixture
def raw_clientes():
    return pd.DataFrame({
        'codemp': ['01', '01', '01'],
        'codcli': ['C001', 'C002', 'C001'],   # C001 duplicado
        'nomcli': ['  cliente uno  ', 'CLIENTE DOS', None],
        'rucced': ['1234567890001', '0987654321001', None],
        'tiprucced': ['04', '05', None],
        'limcre': ['1500.50', None, '0'],
        'dias': ['30', '60', None],
        'fecnac': ['1990-05-15', '1985-11-30', None],
        'fecult': ['2024-01-10', '2024-01-11', '2024-01-09'],
        # ... resto de columnas requeridas
    })

@pytest.fixture
def raw_ventas():
    return pd.DataFrame({
        'codemp': ['01', '01', '01'],
        'numfac': ['F001', 'F001', 'F002'],
        'numren': [1, 2, 1],
        'codcli': ['C001', 'C001', 'C002'],
        'codven': ['V01', 'V01', 'V02'],
        'codart': ['A001', 'A002', 'A001'],
        'establ': ['001', '001', '002'],
        'codalm': ['01', '01', '02'],
        'codforpag': ['EF', 'EF', 'CR'],
        'fecha_factura': ['2024-01-15', '2024-01-15', '2024-01-16'],
        'cantidad':       [10.0, 0.0, -5.0],    # 0=inválido, negativo=dev
        'precio_unitario':[25.5, 10.0, 30.0],
        'costo_unitario': [15.0, 6.0, 18.0],
        'pct_descuento':  [0.0, 0.0, 10.0],
        'valor_iva':      [3.06, 0.0, 3.24],
        'valor_ice':      [0.0, 0.0, 0.0],
        'costo_total':    [150.0, 0.0, 90.0],
        'subtotal_neto':  [255.0, 0.0, 135.0],
        'estado':         ['A', 'A', 'A'],
        'estadow':        ['A', 'A', 'A'],
    })

# ── Tests de Transformación de Clientes ─────────────────────────────────────
class TestTransformarClientes:
    def test_deduplicacion_mantiene_mas_reciente(self, raw_clientes):
        result = transformar_clientes(raw_clientes)
        assert result['codcli'].duplicated().sum() == 0

    def test_strings_normalizados(self, raw_clientes):
        result = transformar_clientes(raw_clientes)
        assert 'CLIENTE UNO' in result['nombre_cliente'].values

    def test_nulos_en_numericos_rellenados(self, raw_clientes):
        result = transformar_clientes(raw_clientes)
        assert result['limite_credito'].isna().sum() == 0

    def test_columnas_requeridas_presentes(self, raw_clientes):
        result = transformar_clientes(raw_clientes)
        required = ['codemp', 'codcli', 'nombre_cliente', 'es_vigente']
        for col in required:
            assert col in result.columns, f"Falta columna: {col}"

# ── Tests de Transformación de Ventas ───────────────────────────────────────
class TestTransformarVentas:
    def test_filas_con_cantidad_cero_eliminadas(self, raw_ventas):
        result = transformar_ventas(raw_ventas)
        assert (result['cantidad'] == 0).sum() == 0

    def test_cantidad_negativa_marcada_como_devolucion(self, raw_ventas):
        result = transformar_ventas(raw_ventas)
        dev_rows = result[result['es_devolucion'] == True]
        assert len(dev_rows) > 0
        assert (dev_rows['cantidad'] > 0).all()

    def test_pct_margen_calculado(self, raw_ventas):
        result = transformar_ventas(raw_ventas)
        assert 'pct_margen' in result.columns
        assert result['pct_margen'].notna().all()

    def test_margen_bruto_coherente(self, raw_ventas):
        result = transformar_ventas(raw_ventas)
        validos = result[result['subtotal_neto'] > 0]
        assert (validos['pct_margen'] >= -100).all()

# ── Ejecutar tests ───────────────────────────────────────────────────────────
# cd etl && pytest tests/ -v --tb=short
```

**Ejecutar el suite de pruebas:**

```bash
cd etl/
pytest tests/ -v --tb=short --cov=transformers --cov-report=term-missing
```

**Entregable de la Fase 2:** EDW completamente poblado con datos históricos desde SAP. Tabla `edw.etl_control` con registros `SUCCESS` para todas las tablas. Suite de pruebas unitarias del ETL con cobertura ≥ 80%.

---

<a name="fase-3"></a>

## Fase 3: Ciencia de Datos y Machine Learning

> **Duración estimada:** Semanas 7–10  
> **Objetivo:** Desarrollar, entrenar, evaluar y exportar los modelos predictivos de mayor impacto para el negocio, listos para ser servidos por la API.

---

### 3.1 Análisis Exploratorio de Datos (EDA)

El EDA se realiza en **Jupyter Notebooks** conectados al EDW (`ml/notebooks/`). Configurar el entorno:

```bash
cd ml/
python -m venv .venv && source .venv/bin/activate
pip install jupyter pandas numpy matplotlib seaborn plotly sqlalchemy psycopg2-binary scikit-learn xgboost joblib shap
jupyter lab
```

**Notebooks recomendados (uno por dominio):**

| Notebook                  | Tablas del EDW                                                  | Análisis clave                                  |
| ------------------------- | --------------------------------------------------------------- | ----------------------------------------------- |
| `01_eda_ventas.ipynb`     | `Fact_Ventas_Detalle`, `Dim_Tiempo`, `Dim_Producto`             | Tendencias, estacionalidad, top productos       |
| `02_eda_clientes.ipynb`   | `Fact_Ventas_Detalle`, `Dim_Cliente`, `Fact_Cobros_CXC`         | Frecuencia, RFM, comportamiento de pago         |
| `03_eda_inventario.ipynb` | `Fact_Inventario_Snapshot`, `Fact_Movimientos_Inventario`       | Rotación, alertas de stock, correlación demanda |
| `04_eda_sucursales.ipynb` | `Fact_Ventas_Detalle`, `Dim_Sucursal`, `Fact_Metas_Comerciales` | Comparativa de desempeño entre sucursales       |

**Preguntas clave del EDA:**

```python
# Conexión al EDW desde Jupyter
from sqlalchemy import create_engine
import pandas as pd

engine = create_engine("postgresql+psycopg2://bi_readonly:pass@localhost:5433/edw")

# ── 1. Distribución temporal de ventas ──────────────────────────────────────
df_ventas_mes = pd.read_sql("""
    SELECT
        t.anio, t.mes, t.nombre_mes,
        s.nombre_sucursal,
        SUM(f.total_linea)   AS total_ventas,
        SUM(f.margen_bruto)  AS margen_total,
        COUNT(DISTINCT f.num_factura) AS num_facturas
    FROM edw.fact_ventas_detalle f
    JOIN edw.dim_tiempo t   ON t.tiempo_sk = f.tiempo_sk
    JOIN edw.dim_sucursal s ON s.sucursal_sk = f.sucursal_sk
    WHERE f.es_devolucion = FALSE
    GROUP BY t.anio, t.mes, t.nombre_mes, s.nombre_sucursal
    ORDER BY t.anio, t.mes
""", engine)

# ── 2. Top 20 productos por ingresos ────────────────────────────────────────
df_top_prod = pd.read_sql("""
    SELECT
        p.nombre_articulo,
        p.nombre_clase,
        SUM(f.total_linea) AS ingresos,
        SUM(f.cantidad)    AS unidades_vendidas,
        AVG(f.pct_margen)  AS margen_promedio
    FROM edw.fact_ventas_detalle f
    JOIN edw.dim_producto p ON p.producto_sk = f.producto_sk AND p.es_vigente
    GROUP BY p.nombre_articulo, p.nombre_clase
    ORDER BY ingresos DESC
    LIMIT 20
""", engine)

# ── 3. Análisis RFM de clientes ─────────────────────────────────────────────
df_rfm = pd.read_sql("""
    SELECT
        c.codcli,
        c.nombre_cliente,
        MAX(t.fecha_completa)           AS ultima_compra,
        COUNT(DISTINCT f.num_factura)   AS frecuencia,
        SUM(f.total_linea)              AS valor_monetario,
        CURRENT_DATE - MAX(t.fecha_completa) AS recencia_dias
    FROM edw.fact_ventas_detalle f
    JOIN edw.dim_cliente c ON c.cliente_sk = f.cliente_sk AND c.es_vigente
    JOIN edw.dim_tiempo t  ON t.tiempo_sk = f.tiempo_sk
    WHERE f.es_devolucion = FALSE
    GROUP BY c.codcli, c.nombre_cliente
""", engine)
```

---

### 3.2 Feature Engineering

Crear el módulo de features en `ml/src/features/feature_engineering.py`:

```python
# ml/src/features/feature_engineering.py
import pandas as pd
import numpy as np
from sqlalchemy import create_engine

def crear_features_ventas_serie_temporal(engine, codemp: str = '01') -> pd.DataFrame:
    """
    Crea un dataset de series temporales por producto y sucursal
    para el modelo de predicción de ventas.
    Granularidad: semana × producto × sucursal
    """
    df = pd.read_sql("""
        SELECT
            t.anio, t.semana_anio,
            DATE_TRUNC('week', t.fecha_completa) AS semana_inicio,
            p.codart, p.nombre_articulo,
            p.nombre_clase, p.nombre_subclase,
            s.codigo_sucursal, s.nombre_sucursal,
            SUM(f.cantidad)    AS unidades_semana,
            SUM(f.total_linea) AS monto_semana,
            COUNT(DISTINCT f.num_factura) AS transacciones,
            AVG(f.precio_unitario) AS precio_promedio
        FROM edw.fact_ventas_detalle f
        JOIN edw.dim_tiempo t    ON t.tiempo_sk   = f.tiempo_sk
        JOIN edw.dim_producto p  ON p.producto_sk = f.producto_sk AND p.es_vigente
        JOIN edw.dim_sucursal s  ON s.sucursal_sk = f.sucursal_sk
        WHERE f.es_devolucion = FALSE
        GROUP BY t.anio, t.semana_anio, DATE_TRUNC('week', t.fecha_completa),
                 p.codart, p.nombre_articulo, p.nombre_clase, p.nombre_subclase,
                 s.codigo_sucursal, s.nombre_sucursal
        ORDER BY semana_inicio, p.codart, s.codigo_sucursal
    """, engine)

    # Lags y rolling statistics como featuers temporales
    df = df.sort_values(['codart', 'codigo_sucursal', 'semana_inicio'])
    grp = df.groupby(['codart', 'codigo_sucursal'])

    df['lag_1_semana']   = grp['unidades_semana'].shift(1)
    df['lag_2_semanas']  = grp['unidades_semana'].shift(2)
    df['lag_4_semanas']  = grp['unidades_semana'].shift(4)
    df['lag_8_semanas']  = grp['unidades_semana'].shift(8)
    df['lag_52_semanas'] = grp['unidades_semana'].shift(52)    # mismo período año anterior

    df['roll_4w_mean']   = grp['unidades_semana'].transform(lambda x: x.shift(1).rolling(4).mean())
    df['roll_4w_std']    = grp['unidades_semana'].transform(lambda x: x.shift(1).rolling(4).std())
    df['roll_12w_mean']  = grp['unidades_semana'].transform(lambda x: x.shift(1).rolling(12).mean())

    # Tendencia (semana del año como proxy de estacionalidad)
    df['semana_sin']     = np.sin(2 * np.pi * df['semana_anio'] / 52)
    df['semana_cos']     = np.cos(2 * np.pi * df['semana_anio'] / 52)

    return df.dropna(subset=['lag_1_semana', 'lag_4_semanas'])


def crear_features_rfm(engine) -> pd.DataFrame:
    """Genera scores RFM normalizados para segmentación de clientes."""
    df = pd.read_sql("""
        SELECT codcli, recencia_dias, frecuencia, valor_monetario
        FROM (
            SELECT c.codcli,
                CURRENT_DATE - MAX(t.fecha_completa) AS recencia_dias,
                COUNT(DISTINCT f.num_factura) AS frecuencia,
                SUM(f.total_linea) AS valor_monetario
            FROM edw.fact_ventas_detalle f
            JOIN edw.dim_cliente c ON c.cliente_sk = f.cliente_sk AND c.es_vigente
            JOIN edw.dim_tiempo t  ON t.tiempo_sk = f.tiempo_sk
            WHERE f.es_devolucion = FALSE
            GROUP BY c.codcli
        ) rfm_base
    """, engine)

    # Quintiles RFM (1=peor, 5=mejor)
    df['r_score'] = pd.qcut(df['recencia_dias'].rank(method='first'),
                             5, labels=[5,4,3,2,1]).astype(int)
    df['f_score'] = pd.qcut(df['frecuencia'].rank(method='first'),
                             5, labels=[1,2,3,4,5]).astype(int)
    df['m_score'] = pd.qcut(df['valor_monetario'].rank(method='first'),
                             5, labels=[1,2,3,4,5]).astype(int)
    df['rfm_score'] = df['r_score'] + df['f_score'] + df['m_score']
    return df
```

---

### 3.3 Modelo 1: Predicción de Ventas (XGBoost Regressor)

Este es el modelo de **mayor impacto** para el rol de Gerente.

```python
# ml/src/training/train_ventas_prediccion.py
import pandas as pd
import numpy as np
import joblib
from sqlalchemy import create_engine
from sklearn.model_selection import TimeSeriesSplit
from sklearn.metrics import mean_absolute_error, mean_squared_error
from xgboost import XGBRegressor
from ml.src.features.feature_engineering import crear_features_ventas_serie_temporal

def entrenar_modelo_ventas(db_url: str, output_path: str = "ml/models/"):
    engine   = create_engine(db_url)
    df       = crear_features_ventas_serie_temporal(engine)

    FEATURES = [
        'lag_1_semana', 'lag_2_semanas', 'lag_4_semanas',
        'lag_8_semanas', 'lag_52_semanas',
        'roll_4w_mean', 'roll_4w_std', 'roll_12w_mean',
        'semana_sin', 'semana_cos', 'anio'
    ]
    TARGET   = 'unidades_semana'

    # Codificación de variables categóricas
    df['sucursal_enc'] = pd.Categorical(df['codigo_sucursal']).codes
    df['clase_enc']    = pd.Categorical(df['nombre_clase']).codes
    FEATURES += ['sucursal_enc', 'clase_enc']

    X = df[FEATURES]
    y = df[TARGET]

    # Validación cruzada temporal (evita data leakage)
    tscv = TimeSeriesSplit(n_splits=5)

    model = XGBRegressor(
        n_estimators=500,
        learning_rate=0.05,
        max_depth=6,
        subsample=0.8,
        colsample_bytree=0.8,
        random_state=42,
        n_jobs=-1,
        early_stopping_rounds=20,
        eval_metric='mae'
    )

    scores_mae, scores_rmse = [], []
    for fold, (train_idx, val_idx) in enumerate(tscv.split(X)):
        X_train, X_val = X.iloc[train_idx], X.iloc[val_idx]
        y_train, y_val = y.iloc[train_idx], y.iloc[val_idx]

        model.fit(X_train, y_train,
                  eval_set=[(X_val, y_val)],
                  verbose=False)

        y_pred = model.predict(X_val).clip(min=0)
        mae    = mean_absolute_error(y_val, y_pred)
        rmse   = np.sqrt(mean_squared_error(y_val, y_pred))
        scores_mae.append(mae);  scores_rmse.append(rmse)
        print(f"  Fold {fold+1}: MAE={mae:.2f}, RMSE={rmse:.2f}")

    print(f"\nMAE promedio: {np.mean(scores_mae):.2f} ± {np.std(scores_mae):.2f}")
    print(f"RMSE promedio: {np.mean(scores_rmse):.2f} ± {np.std(scores_rmse):.2f}")

    # Entrenamiento final con todos los datos
    model.fit(X, y, eval_set=[(X, y)], verbose=False)

    # Exportar modelo + metadatos
    metadata = {
        'model':    model,
        'features': FEATURES,
        'encoder_sucursal': dict(enumerate(pd.Categorical(df['codigo_sucursal']).categories)),
        'encoder_clase':    dict(enumerate(pd.Categorical(df['nombre_clase']).categories)),
    }
    joblib.dump(metadata, f"{output_path}ventas_xgb.joblib")
    print(f"Modelo guardado en {output_path}ventas_xgb.joblib")
    return model

if __name__ == "__main__":
    import os
    DB_URL = f"postgresql+psycopg2://bi_readonly:pass@localhost:5433/edw"
    entrenar_modelo_ventas(DB_URL)
```

---

### 3.4 Modelo 2: Segmentación de Clientes (K-Means + RFM)

```python
# ml/src/training/train_segmentacion_clientes.py
import pandas as pd
import joblib
from sqlalchemy import create_engine
from sklearn.preprocessing import StandardScaler
from sklearn.cluster import KMeans
from sklearn.metrics import silhouette_score
from ml.src.features.feature_engineering import crear_features_rfm

def entrenar_segmentacion_clientes(db_url: str, n_clusters: int = 5,
                                    output_path: str = "ml/models/"):
    engine = create_engine(db_url)
    df_rfm = crear_features_rfm(engine)

    FEATURES = ['recencia_dias', 'frecuencia', 'valor_monetario']
    X = df_rfm[FEATURES].fillna(0)

    # Normalización
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)

    # Método del codo para validar n_clusters
    inertias = {}
    for k in range(2, 11):
        km = KMeans(n_clusters=k, random_state=42, n_init=10)
        km.fit(X_scaled)
        inertias[k] = km.inertia_

    # Modelo final
    km_final = KMeans(n_clusters=n_clusters, random_state=42, n_init=10)
    df_rfm['segmento'] = km_final.fit_predict(X_scaled)
    silhouette = silhouette_score(X_scaled, df_rfm['segmento'])
    print(f"Silhouette Score: {silhouette:.4f}")

    # Etiquetas interpretables para el negocio
    centros = pd.DataFrame(
        scaler.inverse_transform(km_final.cluster_centers_),
        columns=FEATURES
    ).sort_values('valor_monetario', ascending=False)
    labels = ['VIP', 'Leal', 'Potencial', 'En Riesgo', 'Perdido']
    label_map = {centros.index[i]: labels[i] for i in range(n_clusters)}
    df_rfm['segmento_label'] = df_rfm['segmento'].map(label_map)

    # Exportar
    metadata = {
        'model':    km_final,
        'scaler':   scaler,
        'features': FEATURES,
        'label_map': label_map,
        'silhouette': silhouette,
    }
    joblib.dump(metadata, f"{output_path}segmentacion_clientes.joblib")
    df_rfm[['codcli', 'segmento', 'segmento_label', 'rfm_score']].to_csv(
        f"{output_path}segmentos_clientes.csv", index=False)
    print(f"Segmentación exportada. Distribución:\n{df_rfm['segmento_label'].value_counts()}")
    return km_final, df_rfm

if __name__ == "__main__":
    DB_URL = "postgresql+psycopg2://bi_readonly:pass@localhost:5433/edw"
    entrenar_segmentacion_clientes(DB_URL)
```

---

### 3.5 Modelo 3: Predicción de Demanda para Bodega (Random Forest)

```python
# ml/src/training/train_prediccion_demanda.py
import pandas as pd, numpy as np, joblib
from sqlalchemy import create_engine
from sklearn.ensemble import RandomForestRegressor
from sklearn.model_selection import cross_val_score
from sklearn.metrics import mean_absolute_percentage_error

def entrenar_prediccion_demanda(db_url: str, output_path: str = "ml/models/"):
    engine = create_engine(db_url)

    # Dataset: semanas × producto × almacén
    df = pd.read_sql("""
        SELECT
            t.semana_anio, t.anio, t.mes,
            p.codart, p.nombre_clase,
            a.codalm, a.nombre_almacen,
            SUM(ABS(m.cantidad_movimiento)) AS demanda_unidades
        FROM edw.fact_movimientos_inventario m
        JOIN edw.dim_tiempo t    ON t.tiempo_sk   = m.tiempo_sk
        JOIN edw.dim_producto p  ON p.producto_sk = m.producto_sk AND p.es_vigente
        JOIN edw.dim_almacen a   ON a.almacen_sk  = m.almacen_sk
        WHERE m.es_salida = TRUE
        GROUP BY t.semana_anio, t.anio, t.mes, p.codart, p.nombre_clase,
                 a.codalm, a.nombre_almacen
        ORDER BY t.anio, t.semana_anio
    """, engine)

    df['codart_enc'] = pd.Categorical(df['codart']).codes
    df['codalm_enc'] = pd.Categorical(df['codalm']).codes
    df['clase_enc']  = pd.Categorical(df['nombre_clase']).codes

    FEATURES = ['anio', 'mes', 'semana_anio', 'codart_enc', 'codalm_enc', 'clase_enc']
    TARGET   = 'demanda_unidades'

    X, y = df[FEATURES], df[TARGET]

    model = RandomForestRegressor(
        n_estimators=200, max_depth=12,
        min_samples_leaf=5, random_state=42, n_jobs=-1
    )
    # Validación cruzada (5 folds)
    scores = cross_val_score(model, X, y, cv=5,
                             scoring='neg_mean_absolute_error', n_jobs=-1)
    print(f"MAE CV: {-scores.mean():.2f} ± {scores.std():.2f}")

    model.fit(X, y)
    mape = mean_absolute_percentage_error(y, model.predict(X).clip(min=0))
    print(f"MAPE (train): {mape*100:.2f}%")

    metadata = {
        'model': model,
        'features': FEATURES,
        'encoders': {
            'codart': dict(enumerate(pd.Categorical(df['codart']).categories)),
            'codalm': dict(enumerate(pd.Categorical(df['codalm']).categories)),
        }
    }
    joblib.dump(metadata, f"{output_path}demanda_rf.joblib")
    print(f"Modelo de demanda guardado.")
    return model
```

---

### 3.6 Módulo de Inferencia (Carga de Modelos para la API)

```python
# ml/src/prediction/predictor.py
import joblib
import pandas as pd
import numpy as np
from pathlib import Path

MODELS_PATH = Path(__file__).parent.parent.parent / "models"

class VentasPredictor:
    """Clase singleton para cargar el modelo de ventas una sola vez."""
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._load()
        return cls._instance

    def _load(self):
        data = joblib.load(MODELS_PATH / "ventas_xgb.joblib")
        self.model    = data['model']
        self.features = data['features']
        print("[VentasPredictor] Modelo cargado exitosamente.")

    def predecir(self, codart: str, codigo_sucursal: str,
                 semanas_horizonte: int = 4) -> list[dict]:
        """
        Genera predicciones para las próximas N semanas.
        Retorna lista de {'semana': int, 'prediccion_unidades': float}.
        """
        # Construir vector de features (última semana conocida + proyecciones)
        # NOTA: En producción, obtener lags reales desde el EDW
        resultados = []
        for i in range(1, semanas_horizonte + 1):
            X_pred = pd.DataFrame([{
                'lag_1_semana':   0,   # Reemplazar con datos reales del EDW
                'lag_2_semanas':  0,
                'lag_4_semanas':  0,
                'lag_8_semanas':  0,
                'lag_52_semanas': 0,
                'roll_4w_mean':   0,
                'roll_4w_std':    0,
                'roll_12w_mean':  0,
                'semana_sin':     np.sin(2 * np.pi * i / 52),
                'semana_cos':     np.cos(2 * np.pi * i / 52),
                'anio':           2026,
                'sucursal_enc':   0,
                'clase_enc':      0,
            }])[self.features]
            pred = float(self.model.predict(X_pred).clip(min=0)[0])
            resultados.append({'semana_horizonte': i, 'prediccion_unidades': round(pred, 2)})
        return resultados


class SegmentacionPredictor:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._load()
        return cls._instance

    def _load(self):
        data = joblib.load(MODELS_PATH / "segmentacion_clientes.joblib")
        self.model     = data['model']
        self.scaler    = data['scaler']
        self.features  = data['features']
        self.label_map = data['label_map']

    def segmentar(self, recencia: int, frecuencia: int, monetario: float) -> dict:
        X = self.scaler.transform([[recencia, frecuencia, monetario]])
        segmento_id = int(self.model.predict(X)[0])
        return {
            'segmento_id': segmento_id,
            'segmento_label': self.label_map.get(segmento_id, 'Desconocido')
        }
```

**Entrenamiento y exportación de todos los modelos:**

```bash
cd ml/
# Ejecutar en orden:
python src/training/train_ventas_prediccion.py
python src/training/train_segmentacion_clientes.py
python src/training/train_prediccion_demanda.py

# Verificar archivos generados
ls -lh models/
# ventas_xgb.joblib
# segmentacion_clientes.joblib
# demanda_rf.joblib
```

**Entregable de la Fase 3:** 3 modelos exportados en `ml/models/`. Notebooks de EDA documentados. Métricas de evaluación registradas (MAE, RMSE, Silhouette Score). Módulo `predictor.py` probado de forma unitaria.

---

<a name="fase-4"></a>

## Fase 4: Desarrollo del Backend (FastAPI)

> **Duración estimada:** Semanas 11–14  
> **Objetivo:** API REST completamente funcional con autenticación JWT, RBAC por roles, endpoints de KPIs del EDW y endpoints de inferencia ML.

---

### 4.1 Configuración Inicial del Proyecto FastAPI

```bash
cd backend/
python -m venv .venv && source .venv/bin/activate
pip install fastapi uvicorn[standard] sqlalchemy psycopg2-binary \
            pydantic-settings python-jose[cryptography] passlib[bcrypt] \
            slowapi python-multipart httpx pytest pytest-asyncio
```

**`backend/requirements.txt`:**

```
fastapi>=0.111.0
uvicorn[standard]>=0.29.0
sqlalchemy>=2.0.0
psycopg2-binary>=2.9.0
pydantic-settings>=2.0.0
python-jose[cryptography]>=3.3.0
passlib[bcrypt]>=1.7.4
slowapi>=0.1.9
python-multipart>=0.0.9
httpx>=0.27.0
pytest>=7.4.0
pytest-asyncio>=0.23.0
joblib>=1.3.0
pandas>=2.0.0
numpy>=1.26.0
```

**`backend/app/core/config.py`:**

```python
from pydantic_settings import BaseSettings
from functools import lru_cache

class Settings(BaseSettings):
    # Seguridad
    SECRET_KEY:                  str  = "CHANGE_ME"
    ALGORITHM:                   str  = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int  = 480

    # EDW (solo lectura)
    EDW_DB_URL: str = "postgresql+psycopg2://bi_readonly:pass@postgres_edw:5432/edw"

    # App DB (usuarios del sistema BI)
    APP_DB_URL: str = "postgresql+psycopg2://bi_user:pass@postgres_app:5432/bi_app"

    # CORS
    BACKEND_CORS_ORIGINS: list[str] = ["http://localhost:5173"]

    # Rate limiting
    RATE_LIMIT_PER_MINUTE: int = 60

    class Config:
        env_file = ".env"
        extra    = "ignore"

@lru_cache()
def get_settings() -> Settings:
    return Settings()
```

---

### 4.2 Seguridad — JWT y Hashing

```python
# backend/app/core/security.py
from datetime import datetime, timedelta, timezone
from passlib.context import CryptContext
from jose import JWTError, jwt
from .config import get_settings

settings = get_settings()
pwd_ctx  = CryptContext(schemes=["bcrypt"], deprecated="auto")

def hash_password(plain: str) -> str:
    return pwd_ctx.hash(plain)

def verify_password(plain: str, hashed: str) -> bool:
    return pwd_ctx.verify(plain, hashed)

def create_access_token(data: dict, expires_delta: timedelta | None = None) -> str:
    to_encode = data.copy()
    expire    = datetime.now(timezone.utc) + (
        expires_delta or timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)

def decode_token(token: str) -> dict:
    return jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
```

---

### 4.3 Control de Acceso Basado en Roles (RBAC)

Los roles definidos en el sistema son: **admin**, **gerente**, **bodega**, **ventas**.

```python
# backend/app/core/dependencies.py
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from jose import JWTError
from .security import decode_token
from .config import get_settings
from ..db.session import get_app_db
from ..models.user import UserModel

settings     = get_settings()
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/token")

async def get_current_user(
    token: str   = Depends(oauth2_scheme),
    db:   Session = Depends(get_app_db)
) -> UserModel:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Token inválido o expirado",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload  = decode_token(token)
        username = payload.get("sub")
        if not username:
            raise credentials_exception
    except JWTError:
        raise credentials_exception

    user = db.query(UserModel).filter(
        UserModel.username == username,
        UserModel.is_active == True
    ).first()
    if not user:
        raise credentials_exception
    return user

def require_roles(*roles: str):
    """Factory que genera un dependency de FastAPI para validar roles."""
    async def role_checker(current_user: UserModel = Depends(get_current_user)):
        if current_user.role not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Acceso denegado. Roles requeridos: {list(roles)}"
            )
        return current_user
    return role_checker

# Shortcuts para uso en endpoints
AdminOnly   = Depends(require_roles("admin"))
GerenteUp   = Depends(require_roles("admin", "gerente"))
BodegaUp    = Depends(require_roles("admin", "gerente", "bodega"))
AllRoles    = Depends(require_roles("admin", "gerente", "bodega", "ventas"))
```

---

### 4.4 Endpoints de Autenticación

```python
# backend/app/api/v1/endpoints/auth.py
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from ....core.security import verify_password, create_access_token
from ....core.dependencies import get_current_user
from ....db.session import get_app_db
from ....models.user import UserModel
from ....schemas.auth import Token, UserResponse

router = APIRouter(prefix="/auth", tags=["Autenticación"])

@router.post("/token", response_model=Token)
async def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_app_db)
):
    user = db.query(UserModel).filter(
        UserModel.username == form_data.username
    ).first()
    if not user or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Credenciales incorrectas"
        )
    token = create_access_token(data={
        "sub":  user.username,
        "role": user.role,
        "id":   user.id
    })
    return {"access_token": token, "token_type": "bearer"}

@router.get("/me", response_model=UserResponse)
async def get_me(current_user: UserModel = Depends(get_current_user)):
    return current_user
```

---

### 4.5 Endpoints de KPIs del Data Warehouse

```python
# backend/app/api/v1/endpoints/kpis.py
from fastapi import APIRouter, Depends, Query
from sqlalchemy import text
from sqlalchemy.orm import Session
from ....core.dependencies import GerenteUp, BodegaUp, AllRoles
from ....db.session import get_edw_db
from ....schemas.kpis import (
    KpiVentasResumen, TopProducto, VentasSucursal,
    AlertaInventario, EvolucionVentas
)

router = APIRouter(prefix="/kpis", tags=["KPIs del Data Warehouse"])

@router.get("/ventas/resumen", response_model=KpiVentasResumen,
            dependencies=[GerenteUp])
async def kpi_ventas_resumen(
    anio:     int = Query(2025, description="Año de análisis"),
    mes:      int | None = Query(None, description="Mes (1-12), opcional"),
    sucursal: str | None = Query(None, description="codigo_sucursal, opcional"),
    db: Session = Depends(get_edw_db)
):
    """KPI ejecutivo: ventas totales, margen, transacciones del período."""
    filtros = "WHERE f.es_devolucion = FALSE AND t.anio = :anio"
    params  = {"anio": anio}
    if mes:
        filtros += " AND t.mes = :mes"
        params["mes"] = mes
    if sucursal:
        filtros += " AND s.codigo_sucursal = :sucursal"
        params["sucursal"] = sucursal

    result = db.execute(text(f"""
        SELECT
            SUM(f.total_linea)            AS total_ventas,
            SUM(f.margen_bruto)           AS margen_total,
            AVG(f.pct_margen)             AS margen_promedio_pct,
            COUNT(DISTINCT f.num_factura) AS num_transacciones,
            COUNT(DISTINCT f.cliente_sk)  AS clientes_activos,
            SUM(f.cantidad)               AS unidades_vendidas
        FROM edw.fact_ventas_detalle f
        JOIN edw.dim_tiempo   t ON t.tiempo_sk   = f.tiempo_sk
        JOIN edw.dim_sucursal s ON s.sucursal_sk = f.sucursal_sk
        {filtros}
    """), params).mappings().first()
    return dict(result)


@router.get("/ventas/por-sucursal", response_model=list[VentasSucursal],
            dependencies=[GerenteUp])
async def kpi_ventas_sucursal(
    anio: int = Query(2025), mes: int | None = Query(None),
    db: Session = Depends(get_edw_db)
):
    """Ventas comparadas entre sucursales."""
    params = {"anio": anio}
    filtro_mes = "AND t.mes = :mes" if mes else ""
    if mes: params["mes"] = mes

    rows = db.execute(text(f"""
        SELECT
            s.codigo_sucursal,
            s.nombre_sucursal,
            SUM(f.total_linea)            AS total_ventas,
            SUM(f.margen_bruto)           AS margen_total,
            COUNT(DISTINCT f.num_factura) AS transacciones,
            AVG(f.pct_margen)             AS margen_promedio_pct
        FROM edw.fact_ventas_detalle f
        JOIN edw.dim_tiempo   t ON t.tiempo_sk   = f.tiempo_sk
        JOIN edw.dim_sucursal s ON s.sucursal_sk = f.sucursal_sk
        WHERE f.es_devolucion = FALSE AND t.anio = :anio {filtro_mes}
        GROUP BY s.codigo_sucursal, s.nombre_sucursal
        ORDER BY total_ventas DESC
    """), params).mappings().all()
    return [dict(r) for r in rows]


@router.get("/productos/top", response_model=list[TopProducto],
            dependencies=[AllRoles])
async def kpi_top_productos(
    anio: int = Query(2025), limite: int = Query(20, le=100),
    sucursal: str | None = Query(None),
    db: Session = Depends(get_edw_db)
):
    """Top N productos por ingresos/unidades."""
    params  = {"anio": anio, "limite": limite}
    filtro  = "AND s.codigo_sucursal = :sucursal" if sucursal else ""
    if sucursal: params["sucursal"] = sucursal

    rows = db.execute(text(f"""
        SELECT
            p.codart, p.nombre_articulo, p.nombre_clase,
            SUM(f.total_linea)  AS ingresos,
            SUM(f.cantidad)     AS unidades,
            AVG(f.pct_margen)   AS margen_pct
        FROM edw.fact_ventas_detalle f
        JOIN edw.dim_tiempo   t ON t.tiempo_sk   = f.tiempo_sk
        JOIN edw.dim_producto p ON p.producto_sk = f.producto_sk AND p.es_vigente
        JOIN edw.dim_sucursal s ON s.sucursal_sk = f.sucursal_sk
        WHERE f.es_devolucion = FALSE AND t.anio = :anio {filtro}
        GROUP BY p.codart, p.nombre_articulo, p.nombre_clase
        ORDER BY ingresos DESC
        LIMIT :limite
    """), params).mappings().all()
    return [dict(r) for r in rows]


@router.get("/inventario/alertas", response_model=list[AlertaInventario],
            dependencies=[BodegaUp])
async def kpi_alertas_inventario(db: Session = Depends(get_edw_db)):
    """Productos con alerta de desabastecimiento o sobrestock en snapshot más reciente."""
    rows = db.execute(text("""
        WITH ultimo_snapshot AS (
            SELECT MAX(tiempo_sk) AS ultimo_sk FROM edw.fact_inventario_snapshot
        )
        SELECT
            p.codart, p.nombre_articulo, p.nombre_clase,
            a.nombre_almacen,
            s.nombre_sucursal,
            fi.stock_actual, fi.stock_minimo, fi.stock_maximo,
            fi.punto_reorden, fi.valor_inventario,
            fi.alerta_desabastecimiento, fi.alerta_sobrestock
        FROM edw.fact_inventario_snapshot fi
        JOIN ultimo_snapshot us ON us.ultimo_sk = fi.tiempo_sk
        JOIN edw.dim_producto p  ON p.producto_sk  = fi.producto_sk AND p.es_vigente
        JOIN edw.dim_almacen  a  ON a.almacen_sk   = fi.almacen_sk
        LEFT JOIN edw.dim_sucursal s ON s.sucursal_sk = fi.sucursal_sk
        WHERE fi.alerta_desabastecimiento = TRUE OR fi.alerta_sobrestock = TRUE
        ORDER BY fi.alerta_desabastecimiento DESC, fi.stock_actual ASC
    """)).mappings().all()
    return [dict(r) for r in rows]


@router.get("/ventas/evolucion-mensual", response_model=list[EvolucionVentas],
            dependencies=[GerenteUp])
async def kpi_evolucion_ventas(
    anios: int = Query(3, description="Últimos N años"),
    sucursal: str | None = Query(None),
    db: Session = Depends(get_edw_db)
):
    """Serie temporal mensual de ventas para gráficos de tendencia."""
    params  = {"anios": anios}
    filtro  = "AND s.codigo_sucursal = :sucursal" if sucursal else ""
    if sucursal: params["sucursal"] = sucursal

    rows = db.execute(text(f"""
        SELECT
            t.anio, t.mes, t.nombre_mes,
            t.anio || '-' || LPAD(t.mes::text, 2, '0') AS periodo,
            SUM(f.total_linea)  AS total_ventas,
            SUM(f.margen_bruto) AS margen_total,
            COUNT(DISTINCT f.num_factura) AS transacciones
        FROM edw.fact_ventas_detalle f
        JOIN edw.dim_tiempo   t ON t.tiempo_sk   = f.tiempo_sk
        JOIN edw.dim_sucursal s ON s.sucursal_sk = f.sucursal_sk
        WHERE f.es_devolucion = FALSE
          AND t.anio >= EXTRACT(YEAR FROM CURRENT_DATE) - :anios {filtro}
        GROUP BY t.anio, t.mes, t.nombre_mes
        ORDER BY t.anio, t.mes
    """), params).mappings().all()
    return [dict(r) for r in rows]
```

---

### 4.6 Endpoints de Predicciones ML

```python
# backend/app/api/v1/endpoints/predictions.py
from fastapi import APIRouter, Depends, HTTPException
from ....core.dependencies import GerenteUp, BodegaUp, AllRoles
from ....schemas.predictions import (
    PredVentasRequest, PredVentasResponse,
    SegmentacionRequest, SegmentacionResponse,
    PredDemandaRequest, PredDemandaResponse
)
from ml.src.prediction.predictor import VentasPredictor, SegmentacionPredictor

router = APIRouter(prefix="/predictions", tags=["Predicciones ML"])

# Instanciar predictores al inicio (los modelos se cargan una sola vez)
ventas_pred      = VentasPredictor()
segmento_pred    = SegmentacionPredictor()

@router.post("/ventas", response_model=PredVentasResponse,
             dependencies=[GerenteUp])
async def predecir_ventas(req: PredVentasRequest):
    """
    Predicción de unidades a vender para un producto y sucursal
    en las próximas N semanas.
    """
    try:
        predicciones = ventas_pred.predecir(
            codart           = req.codart,
            codigo_sucursal  = req.codigo_sucursal,
            semanas_horizonte = req.semanas_horizonte
        )
        return {"codart": req.codart, "sucursal": req.codigo_sucursal,
                "predicciones": predicciones}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/segmentacion-cliente", response_model=SegmentacionResponse,
             dependencies=[AllRoles])
async def segmentar_cliente(req: SegmentacionRequest):
    """Clasifica un cliente en un segmento RFM."""
    try:
        resultado = segmento_pred.segmentar(
            recencia    = req.recencia_dias,
            frecuencia  = req.frecuencia_compras,
            monetario   = req.valor_monetario_total
        )
        return {"codcli": req.codcli, **resultado}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
```

---

### 4.7 Ensamble del Router Principal y Aplicación

```python
# backend/app/api/v1/router.py
from fastapi import APIRouter
from .endpoints import auth, kpis, predictions, admin

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(auth.router)
api_router.include_router(kpis.router)
api_router.include_router(predictions.router)
api_router.include_router(admin.router)
```

```python
# backend/app/main.py
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from .api.v1.router import api_router
from .core.config import get_settings

settings = get_settings()
limiter  = Limiter(key_func=get_remote_address,
                   default_limits=[f"{settings.RATE_LIMIT_PER_MINUTE}/minute"])

app = FastAPI(
    title="Plataforma BI Multisucursal — API",
    version="1.0.0",
    description="API REST para analítica empresarial y predicciones ML",
    docs_url="/docs",
    redoc_url="/redoc"
)

# Middlewares
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.BACKEND_CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router)

@app.get("/health", tags=["Health"])
async def health():
    return {"status": "ok", "version": "1.0.0"}
```

**Verificar la API:**

```bash
# Iniciar en modo desarrollo
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# Verificar
curl http://localhost:8000/health
# Swagger UI disponible en: http://localhost:8000/docs
```

**Entregable de la Fase 4:** API FastAPI completa con autenticación JWT funcionando, endpoints de KPIs respondiendo datos reales del EDW, endpoints de predicciones retornando resultados de los modelos ML. Colección Postman/Bruno exportada para pruebas.

---

<a name="fase-5"></a>

## Fase 5: Desarrollo del Frontend (React / TypeScript)

> **Duración estimada:** Semanas 15–18  
> **Objetivo:** SPA React con dashboards dinámicos, segmentados por rol de usuario, consumiendo la API REST y visualizando gráficos analíticos y predicciones.

---

### 5.1 Inicialización del Proyecto

```bash
cd frontend/
npm create vite@latest . -- --template react-ts
npm install

# Dependencias principales
npm install axios react-router-dom@6 zustand \
            recharts @radix-ui/react-dialog \
            @radix-ui/react-select lucide-react \
            date-fns clsx tailwindcss @tailwindcss/vite

# (Opcional: si decides usar Tailwind, confirmar versión con tutor)
```

**Estructura de carpetas `frontend/src/`:**

```
src/
├── api/
│   ├── axiosClient.ts       # Instancia Axios con interceptores JWT
│   ├── authApi.ts
│   ├── kpisApi.ts
│   └── predictionsApi.ts
├── components/
│   ├── layout/
│   │   ├── Sidebar.tsx
│   │   ├── Topbar.tsx
│   │   └── ProtectedRoute.tsx
│   ├── charts/
│   │   ├── LineChartVentas.tsx
│   │   ├── BarChartSucursales.tsx
│   │   ├── PieChartSegmentos.tsx
│   │   └── KpiCard.tsx
│   └── ui/
│       ├── Button.tsx
│       ├── Loading.tsx
│       └── AlertaBadge.tsx
├── hooks/
│   ├── useAuth.ts
│   ├── useKpis.ts
│   └── usePredictions.ts
├── pages/
│   ├── LoginPage.tsx
│   ├── admin/
│   │   └── AdminDashboard.tsx
│   ├── gerente/
│   │   ├── GerenteDashboard.tsx
│   │   ├── VentasSucursales.tsx
│   │   └── PrediccionVentas.tsx
│   ├── bodega/
│   │   ├── BodegaDashboard.tsx
│   │   └── AlertasInventario.tsx
│   └── ventas/
│       ├── VentasDashboard.tsx
│       └── SegmentacionClientes.tsx
├── store/
│   └── authStore.ts
├── types/
│   ├── api.types.ts
│   └── dashboard.types.ts
├── App.tsx
└── main.tsx
```

---

### 5.2 Cliente Axios con Interceptores JWT

```typescript
// frontend/src/api/axiosClient.ts
import axios from "axios";
import { useAuthStore } from "../store/authStore";

const API_BASE = import.meta.env.VITE_API_URL || "http://localhost:8000/api/v1";

export const apiClient = axios.create({
  baseURL: API_BASE,
  timeout: 15000,
  headers: { "Content-Type": "application/json" },
});

// Interceptor de request: inyecta el token JWT automáticamente
apiClient.interceptors.request.use((config) => {
  const token = useAuthStore.getState().token;
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

// Interceptor de response: manejo de 401 (token expirado)
apiClient.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      useAuthStore.getState().logout();
      window.location.href = "/login";
    }
    return Promise.reject(error);
  },
);
```

---

### 5.3 Estado Global de Autenticación (Zustand)

```typescript
// frontend/src/store/authStore.ts
import { create } from "zustand";
import { persist } from "zustand/middleware";

interface User {
  id: number;
  username: string;
  role: "admin" | "gerente" | "bodega" | "ventas";
  fullName: string;
}

interface AuthState {
  token: string | null;
  user: User | null;
  isAuth: boolean;
  login: (token: string, user: User) => void;
  logout: () => void;
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set) => ({
      token: null,
      user: null,
      isAuth: false,
      login: (token, user) => set({ token, user, isAuth: true }),
      logout: () => set({ token: null, user: null, isAuth: false }),
    }),
    { name: "bi-auth-storage" },
  ),
);
```

---

### 5.4 Enrutamiento y Protección por Roles

```typescript
// frontend/src/components/layout/ProtectedRoute.tsx
import { Navigate, Outlet } from 'react-router-dom';
import { useAuthStore } from '../../store/authStore';

interface Props {
  allowedRoles: string[];
}

export const ProtectedRoute = ({ allowedRoles }: Props) => {
  const { isAuth, user } = useAuthStore();

  if (!isAuth) return <Navigate to="/login" replace />;
  if (!allowedRoles.includes(user!.role)) return <Navigate to="/unauthorized" replace />;

  return <Outlet />;
};
```

```typescript
// frontend/src/App.tsx
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { ProtectedRoute } from './components/layout/ProtectedRoute';
import { LoginPage }         from './pages/LoginPage';
import { GerenteDashboard }  from './pages/gerente/GerenteDashboard';
import { PrediccionVentas }  from './pages/gerente/PrediccionVentas';
import { BodegaDashboard }   from './pages/bodega/BodegaDashboard';
import { AlertasInventario } from './pages/bodega/AlertasInventario';
import { VentasDashboard }   from './pages/ventas/VentasDashboard';
import { AdminDashboard }    from './pages/admin/AdminDashboard';

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/login" element={<LoginPage />} />

        {/* Gerente */}
        <Route element={<ProtectedRoute allowedRoles={['admin','gerente']} />}>
          <Route path="/gerente" element={<GerenteDashboard />} />
          <Route path="/gerente/predicciones" element={<PrediccionVentas />} />
        </Route>

        {/* Bodega */}
        <Route element={<ProtectedRoute allowedRoles={['admin','gerente','bodega']} />}>
          <Route path="/bodega" element={<BodegaDashboard />} />
          <Route path="/bodega/alertas" element={<AlertasInventario />} />
        </Route>

        {/* Ventas */}
        <Route element={<ProtectedRoute allowedRoles={['admin','gerente','bodega','ventas']} />}>
          <Route path="/ventas" element={<VentasDashboard />} />
        </Route>

        {/* Admin */}
        <Route element={<ProtectedRoute allowedRoles={['admin']} />}>
          <Route path="/admin" element={<AdminDashboard />} />
        </Route>

        <Route path="/" element={<Navigate to="/login" replace />} />
      </Routes>
    </BrowserRouter>
  );
}
```

---

### 5.5 Hooks para Consumo de la API

```typescript
// frontend/src/hooks/useKpis.ts
import { useQuery } from "@tanstack/react-query";
import { apiClient } from "../api/axiosClient";

export interface KpiVentasResumen {
  total_ventas: number;
  margen_total: number;
  margen_promedio_pct: number;
  num_transacciones: number;
  clientes_activos: number;
  unidades_vendidas: number;
}

export const useKpiVentasResumen = (
  anio: number,
  mes?: number,
  sucursal?: string,
) =>
  useQuery<KpiVentasResumen>({
    queryKey: ["kpi-ventas-resumen", anio, mes, sucursal],
    queryFn: async () => {
      const params: Record<string, unknown> = { anio };
      if (mes) params.mes = mes;
      if (sucursal) params.sucursal = sucursal;
      const { data } = await apiClient.get("/kpis/ventas/resumen", { params });
      return data;
    },
    staleTime: 5 * 60 * 1000, // 5 minutos de caché
  });

export const useTopProductos = (anio: number, limite = 20, sucursal?: string) =>
  useQuery({
    queryKey: ["top-productos", anio, limite, sucursal],
    queryFn: async () => {
      const params: Record<string, unknown> = { anio, limite };
      if (sucursal) params.sucursal = sucursal;
      const { data } = await apiClient.get("/kpis/productos/top", { params });
      return data;
    },
  });

export const useAlertasInventario = () =>
  useQuery({
    queryKey: ["alertas-inventario"],
    queryFn: async () => {
      const { data } = await apiClient.get("/kpis/inventario/alertas");
      return data;
    },
    refetchInterval: 30 * 60 * 1000, // Refrescar cada 30 min
  });
```

---

### 5.6 Dashboard del Gerente (Ejemplo de Vista Completa)

```typescript
// frontend/src/pages/gerente/GerenteDashboard.tsx
import { useState } from 'react';
import { useKpiVentasResumen, useTopProductos } from '../../hooks/useKpis';
import { KpiCard } from '../../components/charts/KpiCard';
import { LineChartVentas } from '../../components/charts/LineChartVentas';
import { BarChartSucursales } from '../../components/charts/BarChartSucursales';

export const GerenteDashboard = () => {
  const [anio] = useState(new Date().getFullYear());
  const { data: kpis, isLoading: loadingKpis } = useKpiVentasResumen(anio);
  const { data: topProductos }                  = useTopProductos(anio, 10);

  if (loadingKpis) return <div className="loading">Cargando datos...</div>;

  return (
    <div className="dashboard-layout">
      <h1 className="page-title">Dashboard Ejecutivo — Gerencia</h1>

      {/* ── Fila 1: KPI Cards ─────────────────────────────────────── */}
      <div className="kpi-grid">
        <KpiCard
          title="Ventas Totales"
          value={`$${kpis?.total_ventas?.toLocaleString('es-EC', {minimumFractionDigits: 2})}`}
          icon="💰" color="emerald"
        />
        <KpiCard
          title="Margen Bruto"
          value={`$${kpis?.margen_total?.toLocaleString('es-EC', {minimumFractionDigits: 2})}`}
          icon="📈" color="blue"
        />
        <KpiCard
          title="Margen %"
          value={`${kpis?.margen_promedio_pct?.toFixed(1)}%`}
          icon="%" color="violet"
        />
        <KpiCard
          title="Transacciones"
          value={kpis?.num_transacciones?.toLocaleString()}
          icon="🧾" color="amber"
        />
        <KpiCard
          title="Clientes Activos"
          value={kpis?.clientes_activos?.toLocaleString()}
          icon="👥" color="cyan"
        />
      </div>

      {/* ── Fila 2: Gráficos ──────────────────────────────────────── */}
      <div className="charts-grid">
        <div className="chart-card chart-wide">
          <h2>Evolución Mensual de Ventas</h2>
          <LineChartVentas anio={anio} />
        </div>
        <div className="chart-card">
          <h2>Ventas por Sucursal</h2>
          <BarChartSucursales anio={anio} />
        </div>
      </div>

      {/* ── Fila 3: Tabla Top Productos ───────────────────────────── */}
      <div className="table-card">
        <h2>Top 10 Productos por Ingresos</h2>
        <table className="data-table">
          <thead>
            <tr>
              <th>Código</th><th>Producto</th><th>Clase</th>
              <th className="text-right">Ingresos</th>
              <th className="text-right">Unidades</th>
              <th className="text-right">Margen %</th>
            </tr>
          </thead>
          <tbody>
            {topProductos?.map((p: any, i: number) => (
              <tr key={p.codart}>
                <td>{i+1}. {p.codart}</td>
                <td>{p.nombre_articulo}</td>
                <td><span className="badge">{p.nombre_clase}</span></td>
                <td className="text-right">${p.ingresos?.toFixed(2)}</td>
                <td className="text-right">{p.unidades?.toFixed(0)}</td>
                <td className="text-right">{p.margen_pct?.toFixed(1)}%</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
};
```

---

### 5.7 Dashboards por Rol — Resumen de Vistas

| Rol               | Ruta       | Componentes clave                                                          | KPIs / Predicciones                                             |
| ----------------- | ---------- | -------------------------------------------------------------------------- | --------------------------------------------------------------- |
| **Administrador** | `/admin`   | Logs de auditoría, usuarios activos, errores ETL                           | `Fact_Logs_Auditoria`, estado ETL                               |
| **Gerente**       | `/gerente` | Evolución ventas, comparativa sucursales, top productos, predicción ventas | `Fact_Ventas_Detalle`, `Fact_Metas_Comerciales`, modelo XGBoost |
| **Bodega**        | `/bodega`  | Alertas de inventario, rotación, predicción de demanda                     | `Fact_Inventario_Snapshot`, modelo Random Forest                |
| **Ventas**        | `/ventas`  | Segmentación de clientes, productos recomendados, cumplimiento de metas    | `Dim_Cliente`, `Fact_Ventas_Detalle`, modelo K-Means            |

**Librería de gráficos recomendada — Recharts (integrada con React):**

```typescript
// frontend/src/components/charts/LineChartVentas.tsx
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid,
  Tooltip, Legend, ResponsiveContainer
} from 'recharts';
import { useQuery } from '@tanstack/react-query';
import { apiClient } from '../../api/axiosClient';

export const LineChartVentas = ({ anio }: { anio: number }) => {
  const { data } = useQuery({
    queryKey: ['evolucion-ventas', anio],
    queryFn: async () => {
      const { data } = await apiClient.get('/kpis/ventas/evolucion-mensual', {
        params: { anios: 2 }
      });
      return data;
    }
  });

  return (
    <ResponsiveContainer width="100%" height={300}>
      <LineChart data={data ?? []}>
        <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
        <XAxis dataKey="periodo" stroke="#9CA3AF" fontSize={12} />
        <YAxis stroke="#9CA3AF" fontSize={12} tickFormatter={(v) => `$${(v/1000).toFixed(0)}k`} />
        <Tooltip
          contentStyle={{ backgroundColor: '#1F2937', border: '1px solid #374151' }}
          formatter={(value: number) => [`$${value.toLocaleString()}`, 'Ventas']}
        />
        <Legend />
        <Line type="monotone" dataKey="total_ventas" stroke="#10B981"
              strokeWidth={2} dot={{ fill: '#10B981', r: 4 }} name="Ventas" />
        <Line type="monotone" dataKey="margen_total" stroke="#6366F1"
              strokeWidth={2} dot={{ fill: '#6366F1', r: 4 }} name="Margen" />
      </LineChart>
    </ResponsiveContainer>
  );
};
```

**Entregable de la Fase 5:** SPA React completamente integrada con la API. 4 dashboards operativos (admin, gerente, bodega, ventas). Gráficos interactivos con datos reales. Sistema de rutas protegidas por rol funcionando.

---

<a name="fase-6"></a>

## Fase 6: Despliegue e Integración Continua (DevOps)

> **Duración estimada:** Semanas 19–20  
> **Objetivo:** Contenerizar la aplicación completa, desplegarla en un servidor Linux VPS y configurar la carga incremental automática del ETL.

---

### 6.1 Dockerfiles de Producción

**Backend — Producción (`backend/Dockerfile.prod`):**

```dockerfile
FROM python:3.11-slim AS builder
WORKDIR /app
RUN apt-get update && apt-get install -y libpq-dev gcc && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

FROM python:3.11-slim
WORKDIR /app
COPY --from=builder /root/.local /root/.local
COPY . .
ENV PATH=/root/.local/bin:$PATH

EXPOSE 8000
# Sin --reload en producción
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "4"]
```

**Frontend — Producción con Nginx (`frontend/Dockerfile.prod`):**

```dockerfile
# Stage 1: Build
FROM node:20-alpine AS builder
WORKDIR /app
COPY package*.json ./
RUN npm ci --only=production
COPY . .
ARG VITE_API_URL=https://api.tudominio.com/api/v1
ENV VITE_API_URL=$VITE_API_URL
RUN npm run build

# Stage 2: Serve con Nginx
FROM nginx:1.25-alpine
COPY --from=builder /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
```

**`frontend/nginx.conf`:**

```nginx
server {
    listen 80;
    server_name _;
    root /usr/share/nginx/html;
    index index.html;

    # Soporte SPA: redirigir 404 a index.html
    location / {
        try_files $uri $uri/ /index.html;
    }

    # Proxy inverso hacia el backend
    location /api/ {
        proxy_pass         http://backend:8000;
        proxy_http_version 1.1;
        proxy_set_header   Upgrade $http_upgrade;
        proxy_set_header   Connection 'upgrade';
        proxy_set_header   Host $host;
        proxy_cache_bypass $http_upgrade;
    }

    # Optimizaciones de caché para assets estáticos
    location ~* \.(js|css|png|jpg|jpeg|gif|ico|svg|woff2)$ {
        expires 30d;
        add_header Cache-Control "public, immutable";
    }
}
```

---

### 6.2 Docker Compose de Producción

```yaml
# docker-compose.prod.yml
version: "3.9"

services:
  postgres_edw:
    image: postgres:16-alpine
    restart: always
    environment:
      POSTGRES_DB: edw
      POSTGRES_USER: ${PG_USER}
      POSTGRES_PASSWORD: ${PG_PASSWORD}
    volumes:
      - edw_data:/var/lib/postgresql/data
    # NO exponer puertos en producción (acceso solo interno)
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ${PG_USER} -d edw"]
      interval: 30s
      timeout: 10s
      retries: 3

  postgres_app:
    image: postgres:16-alpine
    restart: always
    environment:
      POSTGRES_DB: bi_app
      POSTGRES_USER: ${APP_DB_USER}
      POSTGRES_PASSWORD: ${APP_DB_PASSWORD}
    volumes:
      - app_data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ${APP_DB_USER} -d bi_app"]
      interval: 30s
      timeout: 10s
      retries: 3

  backend:
    build:
      context: ./backend
      dockerfile: Dockerfile.prod
    restart: always
    env_file: .env.prod
    depends_on:
      postgres_edw:
        condition: service_healthy
      postgres_app:
        condition: service_healthy
    volumes:
      - ./ml/models:/app/ml_models:ro # Modelos compartidos (solo lectura)
    # Sin puertos expuestos — Nginx hace proxy

  frontend:
    build:
      context: ./frontend
      dockerfile: Dockerfile.prod
      args:
        VITE_API_URL: ${VITE_API_URL}
    restart: always
    ports:
      - "80:80"
      - "443:443"
    depends_on:
      - backend
    volumes:
      - ./ssl:/etc/nginx/ssl:ro # Certificados SSL

  # ETL programado con cron interno
  etl_scheduler:
    build:
      context: ./etl
      dockerfile: Dockerfile
    restart: always
    env_file: .env.prod
    depends_on:
      postgres_edw:
        condition: service_healthy
    command: >
      sh -c "
        echo '0 2 * * * python /app/orchestrator.py >> /var/log/etl.log 2>&1' | crontab - &&
        crond -f
      "

volumes:
  edw_data:
  app_data:
```

---

### 6.3 Despliegue en Servidor Linux VPS

**Paso 1 — Preparar el servidor (Ubuntu 22.04 LTS):**

```bash
# Conectar al VPS
ssh user@IP_DEL_VPS

# Actualizar el sistema
sudo apt-get update && sudo apt-get upgrade -y

# Instalar Docker y Docker Compose
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker $USER
newgrp docker

# Instalar Git
sudo apt-get install -y git

# Clonar el repositorio
git clone https://github.com/tu-usuario/plataforma-bi-multisucursal.git
cd plataforma-bi-multisucursal
```

**Paso 2 — Configurar variables de producción:**

```bash
# Crear .env.prod con credenciales seguras
cp .env.example .env.prod
nano .env.prod

# Generar SECRET_KEY seguro
python3 -c "import secrets; print(secrets.token_hex(32))"
```

**Paso 3 — Desplegar la aplicación:**

```bash
# Primera vez: levantar todos los servicios
docker compose -f docker-compose.prod.yml up -d --build

# Verificar que todos los servicios están UP
docker compose -f docker-compose.prod.yml ps

# Verificar logs
docker compose -f docker-compose.prod.yml logs -f backend
docker compose -f docker-compose.prod.yml logs -f etl_scheduler

# Ejecutar carga histórica inicial (única vez)
docker compose -f docker-compose.prod.yml run --rm etl \
    python orchestrator.py --modo completo
```

**Paso 4 — SSL con Let's Encrypt (Certbot):**

```bash
sudo apt-get install -y certbot
sudo certbot certonly --standalone -d tudominio.com -d www.tudominio.com

# Configurar renovación automática
echo "0 12 * * * root certbot renew --quiet --post-hook 'docker compose -f /ruta/docker-compose.prod.yml restart frontend'" | sudo tee /etc/cron.d/certbot-renew
```

---

### 6.4 Estrategia de CI/CD con GitHub Actions

```yaml
# .github/workflows/deploy.yml
name: Deploy to Production

on:
  push:
    branches: [main]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "3.11" }
      - name: Test ETL transformers
        run: |
          cd etl/
          pip install -r requirements.txt
          pytest tests/ -v --tb=short

  deploy:
    needs: test
    runs-on: ubuntu-latest
    if: github.ref == 'refs/heads/main'
    steps:
      - name: Deploy via SSH
        uses: appleboy/ssh-action@master
        with:
          host: ${{ secrets.VPS_HOST }}
          username: ${{ secrets.VPS_USER }}
          key: ${{ secrets.VPS_SSH_KEY }}
          script: |
            cd /srv/plataforma-bi-multisucursal
            git pull origin main
            docker compose -f docker-compose.prod.yml up -d --build backend frontend
            docker compose -f docker-compose.prod.yml exec backend \
                python -c "print('Health check OK')"
```

**Entregable de la Fase 6:** Aplicación completamente desplegada y accesible en `https://tudominio.com`. ETL ejecutándose automáticamente cada noche. Pipeline de CI/CD activo en GitHub Actions.

---

<a name="fase-7"></a>

## Fase 7: Redacción y Validación de la Tesis

> **Duración estimada:** Semanas 21–24  
> **Objetivo:** Documentar el proyecto según estándares académicos, validar el sistema con métricas técnicas y de negocio, y preparar la presentación final.

---

### 7.1 Estructura del Documento de Tesis

Siguiendo la estructura típica de tesis de Ingeniería en TI:

```
TESIS: Plataforma Inteligente de Analítica Empresarial y Predicción de Ventas
│
├── PORTADA
├── DECLARACIÓN DE AUTORÍA
├── CERTIFICACIÓN DEL TUTOR
├── DEDICATORIA Y AGRADECIMIENTOS
├── RESUMEN (Español e Inglés)
│
├── CAPÍTULO 1: INTRODUCCIÓN
│   ├── 1.1 Antecedentes
│   ├── 1.2 Problema de investigación
│   ├── 1.3 Justificación
│   ├── 1.4 Objetivos (general y específicos)
│   └── 1.5 Alcance y limitaciones
│
├── CAPÍTULO 2: MARCO TEÓRICO
│   ├── 2.1 Business Intelligence y Data Warehousing
│   ├── 2.2 Arquitectura de constelación de hechos (Kimball)
│   ├── 2.3 Procesos ETL
│   ├── 2.4 Machine Learning supervisado y no supervisado
│   ├── 2.5 Desarrollo de APIs REST (FastAPI)
│   └── 2.6 Estado del arte (trabajos relacionados)
│
├── CAPÍTULO 3: METODOLOGÍA
│   ├── 3.1 Enfoque de investigación (aplicada, incremental)
│   ├── 3.2 Herramientas y tecnologías utilizadas
│   ├── 3.3 Diseño del EDW (Constelación de hechos)
│   ├── 3.4 Diseño del pipeline ETL
│   └── 3.5 Diseño de los modelos de ML
│
├── CAPÍTULO 4: DESARROLLO E IMPLEMENTACIÓN
│   ├── 4.1 Fase 1: Configuración del entorno
│   ├── 4.2 Fase 2: Ingeniería de datos (ETL y EDW)
│   ├── 4.3 Fase 3: Ciencia de Datos y ML
│   ├── 4.4 Fase 4: Backend API
│   ├── 4.5 Fase 5: Frontend y dashboards
│   └── 4.6 Fase 6: Despliegue
│
├── CAPÍTULO 5: RESULTADOS Y VALIDACIÓN
│   ├── 5.1 Métricas del ETL
│   ├── 5.2 Métricas de los modelos ML
│   ├── 5.3 Pruebas de rendimiento de la API
│   ├── 5.4 Validación con usuarios finales
│   └── 5.5 KPIs de negocio obtenidos
│
├── CAPÍTULO 6: CONCLUSIONES Y RECOMENDACIONES
│
├── BIBLIOGRAFÍA
└── ANEXOS
    ├── Anexo A: Diagrama EDW completo
    ├── Anexo B: Diccionario de datos
    ├── Anexo C: Manual de usuario por rol
    └── Anexo D: Código fuente (URL repositorio)
```

---

### 7.2 Pruebas de Validación del Sistema

#### 7.2.1 Pruebas de Calidad del ETL

```python
# Ejecutar después de la carga histórica:

# 1. Validar integridad referencial
SELECT COUNT(*) AS huerfanos
FROM edw.fact_ventas_detalle f
WHERE f.tiempo_sk   NOT IN (SELECT tiempo_sk FROM edw.dim_tiempo)
   OR f.producto_sk NOT IN (SELECT producto_sk FROM edw.dim_producto)
   OR f.cliente_sk  NOT IN (SELECT cliente_sk FROM edw.dim_cliente);
-- Resultado esperado: 0 huérfanos

# 2. Validar consistencia de totales
-- Comparar suma de la BD origen vs EDW
SELECT SUM(totnet) FROM sistema_origen.encabezadofacturas WHERE estadow='A';
SELECT SUM(total_linea) FROM edw.fact_ventas_detalle WHERE es_devolucion=FALSE;
-- Diferencia esperada: < 0.1%

# 3. Cobertura temporal
SELECT MIN(t.fecha_completa), MAX(t.fecha_completa),
       COUNT(DISTINCT t.fecha_completa)
FROM edw.fact_ventas_detalle f
JOIN edw.dim_tiempo t ON t.tiempo_sk = f.tiempo_sk;
```

#### 7.2.2 Métricas de los Modelos ML

Documentar en la tesis las siguientes métricas para cada modelo:

| Modelo                          | Métrica principal     | Valor objetivo     | Métrica secundaria  |
| ------------------------------- | --------------------- | ------------------ | ------------------- |
| Predicción de Ventas (XGBoost)  | MAE (unidades/semana) | ≤ 15% del promedio | RMSE, R²            |
| Predicción de Demanda (RF)      | MAPE                  | ≤ 20%              | MAE                 |
| Segmentación Clientes (K-Means) | Silhouette Score      | ≥ 0.35             | Inercia, n_clusters |

```python
# Script de evaluación final — ejecutar con datos de holdout (últimos 3 meses)
from sklearn.metrics import (mean_absolute_error, mean_squared_error,
                             mean_absolute_percentage_error, r2_score)
import numpy as np

def reporte_metricas_modelo(y_true, y_pred, nombre_modelo: str):
    mae  = mean_absolute_error(y_true, y_pred)
    rmse = np.sqrt(mean_squared_error(y_true, y_pred))
    mape = mean_absolute_percentage_error(y_true, y_pred) * 100
    r2   = r2_score(y_true, y_pred)
    prom = y_true.mean()

    print(f"\n{'='*50}")
    print(f"REPORTE DE MÉTRICAS — {nombre_modelo}")
    print(f"{'='*50}")
    print(f"  MAE  : {mae:.4f} ({(mae/prom)*100:.2f}% del promedio)")
    print(f"  RMSE : {rmse:.4f}")
    print(f"  MAPE : {mape:.2f}%")
    print(f"  R²   : {r2:.4f}")
    print(f"  Promedio variable objetivo: {prom:.4f}")
    return {'mae': mae, 'rmse': rmse, 'mape': mape, 'r2': r2}
```

#### 7.2.3 Pruebas de Rendimiento de la API

```bash
# Instalar herramienta de benchmark
pip install locust

# Crear script de prueba de carga
cat > locustfile.py << 'EOF'
from locust import HttpUser, task, between

class BIUser(HttpUser):
    wait_time = between(1, 3)
    token = None

    def on_start(self):
        resp = self.client.post("/api/v1/auth/token",
                                data={"username": "gerente_test", "password": "test123"})
        self.token = resp.json()["access_token"]

    @task(3)
    def kpi_resumen(self):
        self.client.get("/api/v1/kpis/ventas/resumen?anio=2025",
                        headers={"Authorization": f"Bearer {self.token}"})

    @task(2)
    def top_productos(self):
        self.client.get("/api/v1/kpis/productos/top?anio=2025&limite=10",
                        headers={"Authorization": f"Bearer {self.token}"})

    @task(1)
    def prediccion_ventas(self):
        self.client.post("/api/v1/predictions/ventas",
                         json={"codart": "P001", "codigo_sucursal": "01001",
                               "semanas_horizonte": 4},
                         headers={"Authorization": f"Bearer {self.token}"})
EOF

# Ejecutar prueba de carga: 50 usuarios concurrentes, 5 minutos
locust -f locustfile.py --host=http://localhost:8000 \
       --users 50 --spawn-rate 5 --run-time 5m --headless
```

**Métricas de rendimiento objetivo para la tesis:**

| Endpoint                       | Percentil 95 | RPS objetivo | Error rate |
| ------------------------------ | ------------ | ------------ | ---------- |
| `GET /kpis/ventas/resumen`     | ≤ 500ms      | ≥ 30         | < 1%       |
| `GET /kpis/productos/top`      | ≤ 800ms      | ≥ 20         | < 1%       |
| `POST /predictions/ventas`     | ≤ 2000ms     | ≥ 10         | < 2%       |
| `GET /kpis/inventario/alertas` | ≤ 1000ms     | ≥ 15         | < 1%       |

---

### 7.3 Validación con Usuarios Finales

**Protocolo de validación con usuarios reales:**

1. **Seleccionar 2–3 usuarios por rol** (gerente, bodega, vendedor)
2. **Preparar escenarios de prueba** específicos por rol:
   - Gerente: "¿Cuál sucursal tuvo mayor margen en Q1 2025?"
   - Bodega: "¿Qué productos tienen stock por debajo del mínimo?"
   - Ventas: "¿Cuáles son nuestros clientes VIP activos?"
3. **Aplicar una encuesta de usabilidad** (escala Likert 1-5):
   - Facilidad de navegación
   - Claridad de los gráficos
   - Utilidad de las predicciones
   - Velocidad de respuesta percibida
4. **Documentar feedback** y realizar ajustes menores

```markdown
## Tabla de Resultados de Validación con Usuarios (Template para la Tesis)

| Criterio                    | Gerente (n=2) | Bodega (n=2) | Ventas (n=3) | Promedio |
| --------------------------- | ------------- | ------------ | ------------ | -------- |
| Facilidad de navegación     | 4.5           | 4.0          | 4.2          | 4.2      |
| Claridad de visualizaciones | 4.8           | 4.3          | 4.5          | 4.5      |
| Utilidad de predicciones    | 4.7           | 4.6          | 4.4          | 4.6      |
| Velocidad percibida         | 4.2           | 4.0          | 4.1          | 4.1      |
| **Satisfacción general**    | **4.6**       | **4.2**      | **4.3**      | **4.4**  |

_Escala: 1=Muy malo, 5=Excelente. Meta: promedio ≥ 4.0_
```

---

### 7.4 KPIs de Éxito del Proyecto

Documentar en el capítulo de Resultados los indicadores que demuestran el valor del proyecto:

**KPIs Técnicos:**

| KPI                           | Descripción                             | Meta                  | Resultado obtenido |
| ----------------------------- | --------------------------------------- | --------------------- | ------------------ |
| Tablas del EDW creadas        | Número de tablas implementadas          | 23 (11 Fact + 12 Dim) | —                  |
| Registros históricos cargados | Total de filas en `Fact_Ventas_Detalle` | > 500,000             | —                  |
| Cobertura de pruebas ETL      | Coverage de test unitarios              | ≥ 80%                 | —                  |
| Tiempo de carga incremental   | Duración del ETL diario                 | ≤ 15 min              | —                  |
| Disponibilidad API            | Uptime en producción                    | ≥ 99%                 | —                  |
| MAE modelo ventas             | Error absoluto medio (unidades/semana)  | ≤ 15% del promedio    | —                  |

**KPIs de Negocio (a documentar con la empresa):**

| KPI                                           | Situación antes          | Situación después         |
| --------------------------------------------- | ------------------------ | ------------------------- |
| Tiempo para generar reporte de ventas mensual | ~4 horas manual          | ~30 segundos (automático) |
| Visibilidad de stock crítico                  | Ninguna (proceso manual) | Tiempo real con alertas   |
| Predicción de ventas próximos 30 días         | No disponible            | Disponible con MAE ≤ X%   |
| Comparativa de desempeño entre sucursales     | Proceso manual en Excel  | Dashboard automático      |

---

### 7.5 Checklist Final de Entrega

Verificar que todos los ítems están completos antes de presentar:

```
ENTREGA TÉCNICA:
☐ Repositorio Git limpio y documentado (README.md actualizado)
☐ Docker Compose funcional en ambiente de producción
☐ ETL ejecutándose automáticamente sin errores
☐ Todos los dashboards operativos con datos reales
☐ 3 modelos ML exportados y servidos por la API
☐ Suite de pruebas con cobertura ≥ 80%
☐ Manual de usuario (PDF) por cada rol

ENTREGA ACADÉMICA:
☐ Capítulo 1 (Introducción): aprobado por tutor
☐ Capítulo 2 (Marco Teórico): referencias bibliográficas completas (mínimo 40)
☐ Capítulo 3 (Metodología): diagramas de arquitectura en alta resolución
☐ Capítulo 4 (Desarrollo): capturas de pantalla y fragmentos de código clave
☐ Capítulo 5 (Resultados): tablas de métricas y gráficos de validación
☐ Capítulo 6 (Conclusiones): responde a cada objetivo específico
☐ Anexos: diagrama EDW, diccionario de datos, URL del repositorio
☐ Abstract en inglés revisado
☐ Formato según normativa de la institución
☐ Revisión anti-plagio (Turnitin < 20%)

PRESENTACIÓN:
☐ Demo en vivo funcional (con datos reales o anonimizados)
☐ Slides de la defensa (máximo 20 diapositivas)
☐ Preparar respuestas a preguntas típicas del tribunal
```

---

## Resumen del Cronograma General

| Fase                               | Semanas | Entregable clave                                 |
| ---------------------------------- | ------- | ------------------------------------------------ |
| **Fase 1:** Entorno y Arquitectura | 1–2     | Docker Compose running, repositorio estructurado |
| **Fase 2:** ETL y Data Warehouse   | 3–6     | EDW poblado, ETL con pruebas unitarias           |
| **Fase 3:** Ciencia de Datos y ML  | 7–10    | 3 modelos `.joblib` exportados y validados       |
| **Fase 4:** Backend FastAPI        | 11–14   | API REST con JWT, RBAC, KPIs y predicciones      |
| **Fase 5:** Frontend React         | 15–18   | 4 dashboards operativos por rol                  |
| **Fase 6:** Despliegue DevOps      | 19–20   | Aplicación en producción + CI/CD                 |
| **Fase 7:** Tesis y Validación     | 21–24   | Documento académico completo + defensa           |

---

## Referencias Tecnológicas Clave

| Tecnología     | Versión | Documentación                         |
| -------------- | ------- | ------------------------------------- |
| Python         | 3.11    | https://docs.python.org/3.11          |
| PostgreSQL     | 16      | https://www.postgresql.org/docs/16    |
| pandas         | 2.x     | https://pandas.pydata.org/docs        |
| XGBoost        | 2.x     | https://xgboost.readthedocs.io        |
| scikit-learn   | 1.4     | https://scikit-learn.org/stable       |
| FastAPI        | 0.111   | https://fastapi.tiangolo.com          |
| SQLAlchemy     | 2.x     | https://docs.sqlalchemy.org/en/20     |
| React          | 18      | https://react.dev                     |
| Vite           | 5.x     | https://vitejs.dev                    |
| Recharts       | 2.x     | https://recharts.org                  |
| Docker Compose | 2.x     | https://docs.docker.com/compose       |
| pyodbc         | 5.x     | https://github.com/mkleehammer/pyodbc |

---

_Documento generado el 2026-06-30. Versión 1.0._  
_Arquitectura: SAP SQL Anywhere (origen) → ETL Python/Pandas → PostgreSQL EDW → FastAPI → React/TypeScript_  
_Referencia: `docs/EDW_Diseno_Completo.md` (diseño técnico) y `docs/propuesta_tesis.md` (objetivos académicos)_
