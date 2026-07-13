# Plan de despliegue — ETL + EDW en Windows Server (producción)

> **Fecha:** 2026-07-12
> **Objetivo:** que el ETL corra **todos los días automáticamente dentro de la red de la
> empresa**, acumulando los snapshots diarios de inventario (`fact_inventario_snapshot`)
> sin depender del laptop de desarrollo. Motivación: el snapshot de stock solo se
> construye "hacia adelante" (el ERP no guarda historial de existencias) — cada día que
> el ETL no corre es un día de histórico **irrecuperable**.
> **Alcance:** base de datos EDW (PostgreSQL 16) + ETL programado. El backend/frontend
> pueden desplegarse después en el mismo servidor (el compose ya los trae), pero NO son
> requisito de esta fase.
> **Guía de comandos:** `docs/deploy/instalacion_windows_server_paso_a_paso.md`.

---

## 1. Arquitectura de despliegue

```
Red de la empresa
┌──────────────────────────────────────────────────────────────┐
│  SAP SQL Anywhere 17 (ERP)          Windows Server            │
│  172.16.50.5:4016                   ┌────────────────────────┐│
│  SOLO LECTURA          ◄──TDS 5.0───│ WSL2 (Ubuntu 22.04)    ││
│                                     │  └─ Docker Engine      ││
│                                     │      ├─ postgres_edw   ││
│                                     │      │   (vol edw_data)││
│                                     │      └─ etl (perfil,   ││
│                                     │          corre 1/día)  ││
│                                     │ Task Scheduler Windows ││
│                                     │  ├─ 06:00 → ETL diario ││
│                                     │  ├─ 07:00 → pg_dump    ││
│                                     │  └─ arranque → portproxy│
│                                     └───────────┬────────────┘│
└─────────────────────────────────────────────────┼─────────────┘
                                          VPN     │ 5433 (restringido)
                                   Laptop de desarrollo (solo lectura/consulta)
```

**Decisión principal: Docker sobre WSL2 (recomendada).** El proyecto ya está 100%
dockerizado (`postgres:16-alpine`, imagen ETL con FreeTDS validada en auditoría 06,
DDLs auto-ejecutados por `/docker-entrypoint-initdb.d`). Reusar eso en el servidor
significa **cero cambios de código** y el mismo comportamiento ya probado. Las imágenes
son Linux, así que en Windows Server se ejecutan dentro de WSL2 (soportado en Windows
Server 2022).

**Plan B (sin Docker, si la empresa no permite WSL2/virtualización):** instalación
nativa — PostgreSQL 16 para Windows + Python 3.11 + driver ODBC nativo "SQL Anywhere"
(el `.env.example` ya documenta este modo: `DB_DRIVER=SQL Anywhere 12`). Funciona
porque el ETL soporta ambos drivers, pero pierde: los DDL automáticos (habría que
ejecutar `edw/01..09` a mano), el aislamiento de dependencias y la paridad con el
entorno probado. Solo elegirlo si Docker está vetado. El paso a paso cubre la ruta
Docker; el plan B se documenta como anexo allí.

## 2. Requerimientos

### 2.1 Hardware (mínimos para ETL + PostgreSQL)

| Recurso | Mínimo | Recomendado | Justificación |
|---|---|---|---|
| CPU | 4 vCPU | 8 vCPU | pandas transforma por chunks de 10.000 (`BATCH_SIZE`); WSL2 + Postgres conviven. |
| RAM | 8 GB | 16 GB | WSL2 reserva memoria propia; Postgres + chunks de pandas en paralelo. |
| Disco | 60 GB libres | 120 GB SSD | EDW actual ~1.5M filas de hechos y crece a diario (snapshot añade ~8k filas/día); + backups con retención 30 días. |

### 2.2 Software / sistema operativo

| Requisito | Detalle |
|---|---|
| Windows Server **2022** (Standard o Datacenter) | WSL2 solo está soportado en WS2022+ (build 20348+ con actualizaciones). Si el servidor es 2019 o anterior → usar Plan B nativo o una VM Linux en Hyper-V. |
| Virtualización habilitada en BIOS/hipervisor | WSL2 la necesita. Si el "servidor" es a su vez una VM (VMware/Hyper-V), habilitar **virtualización anidada** en el host. |
| WSL2 + Ubuntu 22.04 | Se instala en el paso a paso. |
| Docker Engine (Community) **dentro de WSL2** | No se usa Docker Desktop (licenciamiento comercial); Docker Engine dentro de la distro es gratuito y suficiente. |
| Git para Windows (o transferencia por zip) | Para clonar/actualizar el repo. |

### 2.3 Red y puertos

| Regla | Dirección | Detalle |
|---|---|---|
| Servidor → SAP `172.16.50.5:4016` | Saliente | **Imprescindible.** El ETL habla TDS 5.0 con el listener tcpip de SQL Anywhere. Validar con `Test-NetConnection` antes de instalar nada. |
| Dev/VPN → Servidor `5433` | Entrante | Solo para que el laptop de desarrollo consulte el EDW. **Restringir por IP de origen** (firewall de Windows). WSL2 usa NAT: requiere `netsh portproxy` (incluido en el paso a paso). |
| Opcional: `8000`/`5173` | Entrante | Solo si después se despliegan backend/frontend en este mismo servidor. |
| IP fija o reserva DHCP para el servidor | — | El Task Scheduler y los accesos remotos dependen de una dirección estable. |

### 2.4 Cuentas y permisos

- Cuenta local de Windows **con privilegios de administrador** solo para la instalación
  (WSL2, firewall, tareas programadas).
- Las tareas programadas se registran para ejecutarse **sin sesión iniciada**
  ("Run whether user is logged on or not") — el ETL no puede depender de que alguien
  haya iniciado sesión en el servidor.
- Usuario SAP de **solo lectura** (el actual `dba` funciona, pero lo correcto en
  producción es solicitar un usuario dedicado con permisos `SELECT` únicamente —
  restricción dura del proyecto: Producción es SOLO LECTURA).

### 2.5 Secretos y configuración (`.env` de producción)

Checklist de valores que **deben** definirse antes de la primera carga (el ETL y el
backend abortan con los defaults inseguros — fail-fast ya implementado):

| Variable | Regla |
|---|---|
| `PG_PASSWORD` | Nueva, fuerte, distinta a la de desarrollo. Se fija al crear el volumen; cambiarla después requiere `ALTER USER` dentro de Postgres. |
| `PII_SALT` | **Único por despliegue y permanente.** Generar 64 caracteres aleatorios. NUNCA cambiarlo tras la primera carga (invalida todos los `hash_anonimo` de `dim_cliente`). Guardarlo en el gestor de contraseñas de la empresa: si se pierde, la correspondencia histórica de clientes anonimizados no se puede regenerar de forma consistente. |
| `DB_HOST/DB_PORT/DB_USER/DB_PASSWORD` | Los reales del ERP (hoy `172.16.50.5:4016`). |
| `JWT_SECRET` | Solo necesario si se despliega el backend; generar igualmente desde ya. |
| `FECHA_DESDE` | Fecha de inicio de la carga histórica inicial (hoy `2020-01-01`). |
| `MODO_INCREMENTAL=true` | Tras la carga inicial, el control incremental usa `edw.etl_control`. |
| `TZ=America/Guayaquil` | Ver §3 — alineación de fechas del snapshot. |

El `.env` de producción **no se versiona** (regla del proyecto). Vive solo en el
servidor con permisos restringidos.

## 3. Decisiones operativas (específicas de este proyecto)

1. **Horario del ETL: 06:00 hora local.** No es arbitrario:
   - El extractor de existencias etiqueta el snapshot con `CURRENT DATE` **del servidor
     SAP** (hora de la empresa), pero la idempotencia del orquestador borra "la foto de
     hoy" usando `date.today()` **del contenedor ETL**, que en Docker corre en UTC.
     Ecuador es UTC−5: entre las 19:00 y las 23:59 locales, la fecha UTC ya es "mañana"
     y ambas fechas divergen → el DELETE de idempotencia borraría un día distinto al
     que inserta (duplicados en re-ejecuciones). **Programando entre 00:00 y 18:59
     locales las dos fechas siempre coinciden**; 06:00 además captura el stock de
     cierre del día anterior antes de que abra la operación.
   - Como refuerzo se define `TZ=America/Guayaquil` en el `.env` (el compose lo pasa al
     contenedor vía `env_file`).
2. **`docker compose run --rm etl`** es el comando de ejecución (el servicio tiene
   `profiles: ["etl"]` y no se levanta con `up`). El `--rm` evita acumular contenedores
   muertos día tras día.
3. **Los DDL de `edw/` solo corren con volumen nuevo.** La primera vez que se levante
   `postgres_edw` en el servidor se ejecutan `01..09` automáticamente; cualquier cambio
   de esquema posterior se aplica a mano (regla ya documentada en CLAUDE.md).
4. **`etl/truncate_edw.py` queda PROHIBIDO en este servidor.** Es destructivo y sin
   salvaguardas; en producción borraría el histórico de snapshots que es justamente lo
   que este despliegue protege.
5. **Carga inicial vs. diaria:** la primera corrida carga desde `FECHA_DESDE` (larga,
   puede tomar horas: ~1.5M filas por TDS). Las siguientes son incrementales desde la
   última corrida `SUCCESS` en `edw.etl_control` (minutos).
6. **El EDW del servidor pasa a ser la fuente oficial.** El EDW local del laptop queda
   como entorno de desarrollo; para desarrollo con datos frescos, apuntar
   `PG_HOST/PG_PORT` del laptop al servidor por VPN (solo lectura recomendable) o
   restaurar un backup reciente en local.

## 4. Respaldos (crítico — el histórico de snapshots es irrecuperable)

| Qué | Cómo | Frecuencia | Retención |
|---|---|---|---|
| Dump lógico del EDW | `pg_dump -Fc` ejecutado vía `docker exec`, copiado a `C:\BI_Backups\` | Diario 07:00 (tras el ETL) | 30 días rotativos |
| Copia externa | El área de TI debe incluir `C:\BI_Backups\` en su respaldo corporativo (cinta/NAS/nube) | Según política de la empresa | ≥ 90 días |
| Prueba de restauración | `pg_restore` contra un contenedor temporal | 1 vez al mes | — |

Razón: `fact_inventario_snapshot` **no puede regenerarse desde el ERP** (el origen no
guarda historial de stock). Todo lo demás del EDW es re-cargable desde SAP; los
snapshots no. Un solo disco dañado sin backup = pérdida definitiva del histórico.

## 5. Monitoreo mínimo

- **Trazabilidad nativa:** `edw.etl_control` registra cada corrida (tabla, estado,
  filas). Query de salud incluida en el paso a paso.
- **Log de ejecución:** la tarea programada redirige stdout/stderr del ETL a
  `C:\BI_Logs\etl_YYYYMMDD.log` (rotación por nombre de archivo).
- **Alerta pasiva:** query semanal (manual o tarea) que detecta huecos de días sin
  snapshot: si `fact_inventario_snapshot` no tiene la fecha de ayer, algo falló.
- Opcional a futuro: acción de correo en el Task Scheduler cuando la tarea termina con
  código ≠ 0.

## 6. Fases de ejecución

| # | Fase | Resultado verificable | Ref. paso a paso |
|---|---|---|---|
| 0 | Verificación previa (hardware, WS2022, conectividad a SAP, IP fija) | `Test-NetConnection 172.16.50.5 -Port 4016` OK | §1 |
| 1 | WSL2 + Ubuntu + Docker Engine | `docker run hello-world` OK dentro de WSL | §2–3 |
| 2 | Despliegue del proyecto + `.env` de producción | Repo en `/opt/proyect_bi`, `.env` con secretos reales | §4–5 |
| 3 | Levantar EDW (DDLs automáticos) | `\dt edw.*` lista 11 dims + 11 hechos; seed de roles OK | §6 |
| 4 | Prueba de conexión a SAP desde el contenedor | `tsql`/test de conexión OK | §7 |
| 5 | Carga histórica inicial | `etl_control` con `SUCCESS` en todas las tablas; verificación `06_verificacion.sql` | §8 |
| 6 | Programación diaria (ETL 06:00 + backup 07:00 + portproxy al arranque) | Tareas visibles en Task Scheduler; corrida de prueba manual OK | §9–10 |
| 7 | Acceso remoto restringido (5433 vía VPN) | Conexión desde el laptop por VPN OK; puerto cerrado para el resto | §11 |
| 8 | Simulacro de falla | Reiniciar el servidor → todo vuelve solo (restart policies + tareas de arranque); restaurar un backup en contenedor temporal | §12 |

## 7. Riesgos y mitigaciones

| Riesgo | Mitigación |
|---|---|
| El servidor es WS2019 o sin virtualización anidada | Plan B nativo (anexo del paso a paso) o VM Linux en Hyper-V. Confirmar la versión ANTES de agendar la instalación. |
| WSL2 no arranca solo tras reinicio del servidor | Las tareas programadas invocan `wsl.exe`, que arranca la distro bajo demanda; Docker se inicia con systemd habilitado en la distro. Simulacro de reinicio en fase 8. |
| IP interna de WSL2 cambia en cada arranque (NAT) | Tarea de arranque que refresca el `netsh portproxy` (script incluido). |
| Corridas después de las 19:00 locales desalinean fechas del snapshot | Horario fijo 06:00 + `TZ` en `.env` (§3.1). |
| Pérdida del disco = pérdida del histórico de snapshots | Backups diarios + copia corporativa externa (§4). |
| FreeTDS trunca tipos exóticos del ERP | Ya auditado (auditoría 06): los 24 extractores se verificaron 24/24 OK contra SAP con FreeTDS. Cualquier extractor nuevo debe re-verificarse. |
| Alguien ejecuta `truncate_edw.py` en el servidor | Prohibido por este plan (§3.4); considerar eliminar el script del deploy de producción. |
