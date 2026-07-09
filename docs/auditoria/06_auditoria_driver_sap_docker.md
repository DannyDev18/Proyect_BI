# Auditoría 06 — Driver de conexión a Producción (SAP SQL Anywhere) dentro de Docker

- **Fecha:** 2026-07-08
- **Alcance:** `etl/Dockerfile`, `etl/connectors/sqlany_connector.py`, `etl/config/settings.py`,
  `docker-compose.yml`, `.env` / `.env.example`. No se toca la lógica de extracción/transformación.
- **Método:** revisión estática de código + validación de build/conectividad. Contra Producción
  **solo `SELECT`** (prueba de conectividad con `SELECT TOP 1`). **No se ejecutó ninguna
  escritura al ERP.**
- **Objetivo:** que el ETL pueda conectarse a Producción ejecutándose 100% dentro del contenedor,
  sin depender del driver ODBC instalado en la máquina anfitriona.

---

## 1. Diagnóstico del estado actual

### Cómo se ejecuta el ETL hoy

- Servicio `etl` en `docker-compose.yml` (perfil `etl`, ejecución manual con
  `docker compose run etl`), imagen `python:3.11-slim`, `CMD python orchestrator.py`.
- En la práctica el ETL se ha venido ejecutando **en el host Windows** (venv local, ver
  `.agent/workflows/ejecutar-etl.md`), porque el contenedor **no puede conectarse a SAP**.

### Driver utilizado

| Aspecto | Valor |
|---|---|
| Lenguaje | Python 3.11 (pyodbc + SQLAlchemy + pandas) |
| Driver actual | **"SQL Anywhere 12"** — driver ODBC nativo del cliente SQL Anywhere **instalado solo en Windows (host)**, referenciado por nombre en `DB_DRIVER` (`.env`) |
| Carga del driver | `pyodbc.connect("Driver={SQL Anywhere 12};ENG=...;DBN=...;Links=tcpip(Host=...;Port=...)")` en `etl/connectors/sqlany_connector.py::_build_connection_string` |
| Gestor ODBC en la imagen | El Dockerfile instala `unixodbc unixodbc-dev gcc`, pero **ningún driver**: dentro del contenedor no existe ninguna librería capaz de hablar con SQL Anywhere |
| Dependencias Python | `pyodbc>=5`, `sqlalchemy>=2`, `psycopg2-binary`, `pandas` (todas con wheels precompilados para cp311/linux — `gcc`/`unixodbc-dev` no son necesarios en build) |

### Qué parte depende del host

Únicamente la **capa ODBC del origen SAP**: el nombre `SQL Anywhere 12` resuelve contra el
registro ODBC de Windows y las DLLs del cliente SQL Anywhere instalado localmente. La conexión al
EDW (psycopg2 → PostgreSQL) ya es autónoma. Dentro del contenedor, `pyodbc.connect` falla con
`Can't open lib 'SQL Anywhere 12'` porque `/etc/odbcinst.ini` está vacío.

### Evidencia adicional

- `.env.example` declara variables `SQLANY_*` que **nadie lee**; `etl/config/settings.py` lee
  `DB_*` (`DB_DRIVER`, `DB_SERVER`, `DB_HOST`…). El `.env` real usa `DB_*`. Inconsistencia ya
  señalada en CLAUDE.md § Observaciones.
- `orchestrator.py` importa `etl/loaders/`, actualmente **borrado del working tree** (hallazgo
  previo, fuera de alcance de esta auditoría): el `CMD` del contenedor fallará al importar hasta
  restaurar esos archivos. La validación de conectividad se hace con un script que no importa
  loaders (`etl/connectors/test_sap.py`).

## 2. Alternativas evaluadas

| Opción | Evaluación |
|---|---|
| **A. Cliente nativo SQL Anywhere para Linux** dentro de la imagen | Es el driver "oficial", pero el instalador es propietario de SAP, no está en repositorios apt y su descarga requiere cuenta SAP. Vendorizar el binario en el repo compromete la reproducibilidad ("clonar y ejecutar") y la licencia. **Descartada.** |
| **B. FreeTDS (ODBC) vía protocolo TDS** | SQL Anywhere soporta nativamente el protocolo TDS en su listener tcpip (es el mecanismo que usan jConnect/Open Client). FreeTDS (`tdsodbc`) se instala con `apt` en el build — 100% reproducible, imagen pequeña, sin binarios propietarios. **Elegida.** |
| **C. sqlanydb (driver Python de SAP)** | Requiere `libdbcapi` del cliente nativo → mismo problema que A. **Descartada.** |

### Riesgos de la migración a FreeTDS (opción B)

1. **Dialecto/protocolo TDS 5.0:** algunos tipos extremos (LONG VARCHAR muy grandes, tipos
   Unicode específicos) pueden truncarse o mapear distinto que con el driver nativo.
   *Mitigación:* `text size` amplio en `freetds.conf`; los extractores usan tipos convencionales
   (varchar/numeric/date); validar con la reconciliación estándar (skill `etl-edw-auditor`,
   `references/validaciones_sql.md` §1) tras la primera carga completa vía contenedor.
2. **El servidor debe aceptar TDS en el puerto tcpip** (comportamiento por defecto de SQL
   Anywhere; podría estar deshabilitado con `-sb`). *Mitigación:* prueba de conectividad
   `SELECT TOP 1` incluida en la validación.
3. **Charset:** los datos del ERP suelen estar en cp1252. *Mitigación:* `client charset = UTF-8`
   en `freetds.conf` (FreeTDS convierte del charset del servidor).
4. **Doble ruta de conexión:** el host Windows puede seguir usando el driver nativo
   (`DB_DRIVER=SQL Anywhere 12`) y el contenedor usa `DB_DRIVER=FreeTDS`. El conector debe
   construir la cadena según el driver — es el único cambio de código necesario, acotado a
   `_build_connection_string`.

## 3. Cambios aplicados

1. **`etl/Dockerfile`**
   - Instala `unixodbc`, `tdsodbc` y `freetds-bin` (diagnóstico) con `--no-install-recommends`.
   - Elimina `gcc` y `unixodbc-dev` (innecesarios: todas las dependencias tienen wheel; imagen
     más pequeña).
   - Registra el driver en `/etc/odbcinst.ini` y fija `[global] tds version = 5.0`,
     `text size` y `client charset = UTF-8` en `/etc/freetds/freetds.conf` durante el build.
2. **`etl/connectors/sqlany_connector.py`** — `_build_connection_string()` detecta si
   `DB_DRIVER` es FreeTDS y arma la cadena TDS (`Server/Port/Database/TDS_Version`); si no,
   conserva la cadena nativa (`ENG/DBN/Links=tcpip`) para ejecución en el host. Sin ningún otro
   cambio de lógica.
3. **`docker-compose.yml`** — el servicio `etl` fija `DB_DRIVER: FreeTDS` (override sobre
   `env_file`), de modo que el mismo `.env` sirve para host y contenedor.
4. **`.env.example`** — corregido para usar las variables reales (`DB_*`) que lee
   `etl/config/settings.py` (elimina las `SQLANY_*` muertas) y documenta `DB_DRIVER` para ambos
   entornos. Sin credenciales reales.

Configuración 100% por variables de entorno; no queda ningún usuario, contraseña, IP, servidor
ni ruta absoluta hardcodeado en código o imagen.

## 4. Validación

- [x] La imagen construye correctamente (`docker compose build etl`) — incluida la
      eliminación de `gcc`/`unixodbc-dev` (todas las dependencias instalaron desde wheel).
- [x] El driver queda registrado dentro del contenedor: `odbcinst -q -d` → `[FreeTDS]`;
      `pyodbc.drivers()` → `['FreeTDS']` (pyodbc 5.3.0).
- [x] El conector construye la cadena TDS correcta dentro del contenedor (verificado con
      `connectors/test_sap.py`, password enmascarado):
      `Driver={FreeTDS};Server=<DB_HOST>;Port=<DB_PORT>;Database=<DB_DATABASE>;UID=...;TDS_Version=5.0;`
- [x] Sin dependencia del driver del host: la imagen no monta nada del host; toda la capa ODBC
      vive en la imagen.
- [x] `py_compile` OK sobre los archivos modificados.
- [x] La ruta nativa del host quedó intacta (misma cadena `ENG/DBN/Links` de siempre cuando
      `DB_DRIVER` no es FreeTDS).
- [ ] **PENDIENTE DE RED — handshake real contra Producción:** al momento de la validación este
      equipo no alcanza `172.16.50.5:4016` (verificado con test TCP desde el contenedor Y desde
      el host: timeout en ambos → no es un problema del contenedor sino de que la máquina no
      está en la red de la empresa/VPN). El error observado
      (`FreeTDS ... Unable to connect (20009)`) corresponde a red inalcanzable, no a rechazo del
      protocolo. **Cómo completar cuando haya red:**
      `docker compose run --rm etl python connectors/test_sap.py`
      (ejecuta un `SELECT TOP 1` de solo lectura; exit code 0 = OK). Si el servidor rechazara el
      protocolo TDS (poco probable, es el mecanismo de jConnect), el plan B documentado es
      vendorizar el cliente Linux de SQL Anywhere en la imagen.

Nota: `connectors/test_sap.py` duplicaba la construcción de la cadena de conexión con el formato
nativo (daría falso negativo en Docker aunque hubiera red). Se corrigió para que use el mismo
`SQLAnywhereConnector` del pipeline — así la prueba valida la ruta real de conexión en ambos
entornos.

## 5. Impacto y prioridad

- **Prioridad Alta (portabilidad/reproducibilidad):** sin este cambio el servicio `etl`
  dockerizado no puede extraer de SAP y el pipeline depende de una máquina concreta.
- **Riesgo residual Medio:** diferencias de tipos vía TDS → ejecutar la reconciliación
  Producción vs EDW tras la primera carga completa desde el contenedor y comparar contra una
  carga previa desde el host.

## 6. Guía operativa (documentación)

### Qué driver se usa y cómo fue instalado

- **En Docker:** FreeTDS (`tdsodbc`, Debian bookworm — FreeTDS 1.3.x) + `unixodbc`, instalados
  con `apt` durante el build (`etl/Dockerfile`). El driver se registra en `/etc/odbcinst.ini`
  como `[FreeTDS]` y `/etc/freetds/freetds.conf` fija `tds version = 5.0`, `text size` amplio y
  `client charset = UTF-8`. Se conecta al listener tcpip de SQL Anywhere vía protocolo TDS.
- **En el host (opcional, solo desarrollo):** driver ODBC nativo del cliente SQL Anywhere
  (`DB_DRIVER=SQL Anywhere 12` en `.env`). Ya no es un requisito del proyecto.

### Variables de entorno requeridas (leídas por `etl/config/settings.py`)

`DB_DRIVER`, `DB_SERVER` (ENG, solo ruta nativa), `DB_DATABASE`, `DB_USER`, `DB_PASSWORD`,
`DB_HOST`, `DB_PORT` — más las de EDW (`PG_*`) y control (`CODEMP`, `ESTADO_VALIDO`,
`FECHA_*`, `PII_SALT`, `BATCH_SIZE`, `MODO_INCREMENTAL`). Plantilla en `.env.example`
(corregida en esta auditoría: antes declaraba variables `SQLANY_*` que ningún código leía).
En Docker, `docker-compose.yml` fuerza `DB_DRIVER=FreeTDS` para el servicio `etl`; el resto
sale del `.env`.

### Cómo probar la conexión

```bash
docker compose run --rm etl python connectors/test_sap.py   # SELECT TOP 1, solo lectura
```

Diagnóstico de bajo nivel (protocolo, sin pyodbc): `docker compose run --rm etl tsql -H <DB_HOST> -p <DB_PORT> -U <DB_USER>`.

### Cómo reconstruir la imagen

```bash
docker compose build etl            # build normal (usa caché)
docker compose build --no-cache etl # build limpio
docker compose run --rm etl         # ejecuta el pipeline completo (orchestrator.py)
```

### Requisito para ejecutar en cualquier equipo

Solo Docker + Docker Compose + un `.env` basado en `.env.example`. Ningún driver local.

## 7. Pendientes relacionados (fuera de alcance)

- Completar el handshake real contra Producción cuando el equipo esté en la red corporativa
  (checklist §4) y, tras la primera carga completa vía contenedor, correr la reconciliación
  Producción vs EDW (skill `etl-edw-auditor`) para descartar diferencias de tipos por TDS.
- `etl/loaders/` sigue borrado del working tree (hallazgo previo): `orchestrator.py` no puede
  importar; restaurar con `git checkout -- etl/loaders/` o confirmar la intención del borrado.
