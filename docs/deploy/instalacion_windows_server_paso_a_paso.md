# Instalación en Windows Server — paso a paso (ETL + EDW)

> **Guía operativa** del plan `docs/deploy/plan_despliegue_windows_server.md`.
> Ejecutar en orden. Los comandos PowerShell van en una consola **como Administrador**;
> los comandos `$` van dentro de la distro **Ubuntu (WSL2)**.
> Convenciones: proyecto en `/opt/proyect_bi` (dentro de WSL), backups en
> `C:\BI_Backups`, logs en `C:\BI_Logs`, scripts en `C:\BI_Scripts`.

---

## 1. Verificación previa (no instalar nada todavía)

```powershell
# 1.1 Versión de Windows: debe ser Windows Server 2022 (build 20348+)
systeminfo | Select-String "OS Name", "OS Version"

# 1.2 Virtualización disponible (requisito de WSL2).
#     Si el servidor es una VM, pedir a TI habilitar "virtualización anidada".
systeminfo | Select-String "Hyper-V"

# 1.3 Conectividad al ERP SAP (imprescindible — si esto falla, detenerse aquí)
Test-NetConnection 172.16.50.5 -Port 4016

# 1.4 IP fija del servidor (anotarla; se usa en VPN/firewall)
ipconfig | Select-String "IPv4"

# 1.5 Windows Update al día (WSL2 en WS2022 requiere KB5014021 o posterior)
```

Si el servidor es **Windows Server 2019 o anterior**: no continuar con esta guía —
usar el Anexo A (instalación nativa sin Docker).

## 2. Instalar WSL2 + Ubuntu 22.04

```powershell
# 2.1 Instalación moderna (WS2022 actualizado; --web-download porque Server no trae Store)
wsl --install --web-download -d Ubuntu-22.04

# Si el comando anterior no existe o falla, método clásico:
dism /online /enable-feature /featurename:Microsoft-Windows-Subsystem-Linux /all /norestart
dism /online /enable-feature /featurename:VirtualMachinePlatform /all /norestart
Restart-Computer   # reiniciar y continuar:
# Descargar e instalar el kernel: https://aka.ms/wsl2kernel  → luego:
wsl --set-default-version 2
wsl --install --web-download -d Ubuntu-22.04

# 2.2 Reiniciar el servidor
Restart-Computer
```

Tras el reinicio, abrir la distro (`wsl -d Ubuntu-22.04`), crear el usuario que pida
(usar p.ej. `biadmin`) y verificar:

```powershell
wsl -l -v          # Ubuntu-22.04  Running  VERSION 2
```

> ⚠️ **WSL es por-usuario de Windows.** Toda la instalación y las tareas programadas
> deben usar **la misma cuenta de Windows** (p.ej. `SERVIDOR\bi_admin`). Una tarea
> corriendo como `SYSTEM` u otro usuario NO ve esta distro.

## 3. Docker Engine dentro de Ubuntu

```powershell
wsl -d Ubuntu-22.04
```

```bash
# 3.1 Habilitar systemd (para que el servicio docker arranque con la distro)
sudo tee /etc/wsl.conf > /dev/null <<'EOF'
[boot]
systemd=true
EOF
exit
```

```powershell
wsl --shutdown      # aplicar wsl.conf
wsl -d Ubuntu-22.04
```

```bash
# 3.2 Instalar Docker Engine (repositorio oficial)
sudo apt-get update
sudo apt-get install -y ca-certificates curl gnupg
sudo install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
  https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo $VERSION_CODENAME) stable" | \
  sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
sudo apt-get update
sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin

# 3.3 Usar docker sin sudo + verificar
sudo usermod -aG docker $USER
exit
```

```powershell
wsl --shutdown
wsl -d Ubuntu-22.04
```

```bash
docker run --rm hello-world     # debe imprimir "Hello from Docker!"
docker compose version
```

## 4. Desplegar el proyecto

```bash
# 4.1 Clonar en el filesystem de WSL (NO en /mnt/c — rendimiento y permisos)
sudo mkdir -p /opt/proyect_bi && sudo chown $USER:$USER /opt/proyect_bi
git clone <URL_DEL_REPO> /opt/proyect_bi
# Alternativa sin git: copiar un zip a C:\ y descomprimir:
#   unzip /mnt/c/Temp/proyect_bi.zip -d /opt/proyect_bi

cd /opt/proyect_bi
```

## 5. `.env` de producción

```bash
cd /opt/proyect_bi
cp .env.example .env

# 5.1 Generar secretos (anotarlos en el gestor de contraseñas de la empresa)
openssl rand -hex 32    # → PII_SALT   (¡PERMANENTE! jamás cambiarlo tras la 1ª carga)
openssl rand -hex 32    # → JWT_SECRET (para cuando se despliegue el backend)
openssl rand -base64 24 # → PG_PASSWORD

nano .env
```

Valores obligatorios a editar en `.env`:

```ini
# SAP (origen, SOLO LECTURA)
DB_HOST=172.16.50.5
DB_PORT=4016
DB_SERVER=xp_plus
DB_DATABASE=db_microplus
DB_USER=<usuario_solo_lectura>
DB_PASSWORD=<password_real>

# EDW
PG_PASSWORD=<generado arriba>

# Seguridad
PII_SALT=<generado arriba — NO CAMBIAR NUNCA>
JWT_SECRET=<generado arriba>

# Admin inicial del backend (sembrado por la migración Alembic 0002_seed_roles la
# primera vez que arranca el contenedor `backend`, ver §6.1 más abajo) — obligatoria,
# las migraciones fallan sin ella. Generar una contraseña real, no reusar la de dev.
ADMIN_INITIAL_PASSWORD=<contraseña segura, distinta de la de desarrollo>

# Zona horaria (alineación de fechas del snapshot — plan §3.1)
TZ=America/Guayaquil

# Carga
FECHA_DESDE=2020-01-01
MODO_INCREMENTAL=true
```

```bash
chmod 600 .env          # solo el dueño puede leerlo
```

## 6. Levantar el EDW (los DDL corren solos en el primer arranque)

```bash
cd /opt/proyect_bi
docker compose up -d postgres_edw

# Esperar el healthcheck y verificar que los DDL 01..09 se ejecutaron:
docker compose ps
docker exec bi_postgres_edw psql -U etl_user -d edw -c "\dt edw.*"    # 11 dims + 11 hechos + etl_control
docker exec bi_postgres_edw psql -U etl_user -d edw -c "SELECT nombre FROM public.roles;"  # 4 roles seed
```

> Si los DDL no corrieron (tablas ausentes), el volumen ya existía de un intento
> anterior: `docker compose down -v` (⚠️ borra datos — solo válido AHORA que está
> vacío, nunca después) y repetir `up -d`.

## 6.1 Levantar el backend (aplica las migraciones del esquema `public` solo)

El esquema `edw.*`/`ml.*` (paso 6) lo crea el `initdb` de Postgres; el esquema
`public.*` (auth, metas, comisiones, notificaciones) lo gestiona **Alembic**
(`backend/alembic/`, docs/features/plan_migraciones_esquema_public.md) — se aplica
automáticamente al arrancar el contenedor `backend`, sin ningún paso manual de SQL:

```bash
cd /opt/proyect_bi
docker compose build backend
docker compose up -d backend

# Verificar que las migraciones corrieron (busca la traza de apply_migrations.py)
docker compose logs backend | grep -i "migracion\|alembic"

docker exec bi_postgres_edw psql -U etl_user -d edw -c \
  "SELECT version_num FROM public.alembic_version;"   # debe mostrar 0002_seed_roles
docker exec bi_postgres_edw psql -U etl_user -d edw -c \
  "SELECT email FROM public.usuarios WHERE email = 'admin@empresa.com';"

curl -s http://localhost:8000/health   # {"status":"ok", ...}
```

> Si el paso 6 ya inicializó `public.*` vía `edw/07`/`edw/08` (caso normal en un
> volumen nuevo), el backend detecta esa BD "pre-Alembic" (existe `public.usuarios`,
> no existe `public.alembic_version`) y la sella con `alembic stamp
> 0001_baseline_public` antes de aplicar lo pendiente — no re-ejecuta ningún DDL.
> Si las migraciones fallan, el contenedor **no arranca** (falla rápido, revisar
> `ADMIN_INITIAL_PASSWORD` en `.env` primero — es la causa más común).

## 7. Probar conexión a SAP desde el contenedor ETL

```bash
cd /opt/proyect_bi
docker compose build etl

# tsql (FreeTDS) directo al listener de SQL Anywhere; salir con "exit"
docker compose run --rm --entrypoint bash etl -c \
  'echo -e "SELECT 1\ngo\nexit" | tsql -H "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -P "$DB_PASSWORD"'
```

Debe devolver una fila con `1`. Si falla: revisar firewall saliente (paso 1.3),
credenciales, o que el listener TDS del ERP esté activo (auditoría 06).

## 8. Carga histórica inicial

```bash
cd /opt/proyect_bi
mkdir -p /var/log/bi && sudo chown $USER /var/log/bi

# Corrida completa (desde FECHA_DESDE). Puede tomar horas: dejar corriendo.
docker compose run --rm etl 2>&1 | tee /var/log/bi/etl_carga_inicial.log

# 8.1 Verificar control de cargas: todo en SUCCESS
docker exec bi_postgres_edw psql -U etl_user -d edw -c \
  "SELECT tabla_destino, estado, filas_cargadas, fecha_fin FROM edw.etl_control ORDER BY fecha_fin DESC LIMIT 30;"

# 8.2 Verificación post-carga del DW
docker exec -i bi_postgres_edw psql -U etl_user -d edw < edw/06_verificacion.sql

# 8.3 El snapshot de HOY debe existir (la razón de todo este despliegue)
docker exec bi_postgres_edw psql -U etl_user -d edw -c \
  "SELECT f.fecha_completa, COUNT(*) FROM edw.fact_inventario_snapshot s \
   JOIN edw.dim_fecha f ON s.fecha_sk = f.fecha_sk GROUP BY 1 ORDER BY 1 DESC LIMIT 7;"
```

## 9. Programar el ETL diario (06:00) — Task Scheduler

```powershell
# 9.1 Carpetas de operación
New-Item -ItemType Directory -Force C:\BI_Scripts, C:\BI_Logs, C:\BI_Backups

# 9.2 Script del ETL diario
Set-Content -Encoding utf8 C:\BI_Scripts\run_etl.ps1 @'
$fecha = Get-Date -Format "yyyyMMdd"
$log = "C:\BI_Logs\etl_$fecha.log"
wsl -d Ubuntu-22.04 -u root -- bash -lc "cd /opt/proyect_bi && docker compose run --rm etl" *>> $log
if ($LASTEXITCODE -ne 0) { Add-Content $log "ERROR: ETL termino con codigo $LASTEXITCODE" }
# Rotación: borrar logs de más de 60 días
Get-ChildItem C:\BI_Logs\etl_*.log | Where-Object LastWriteTime -lt (Get-Date).AddDays(-60) | Remove-Item -Force
'@

# 9.3 Tarea diaria 06:00 — ⚠️ /ru con LA MISMA cuenta que instaló WSL (pedirá su contraseña).
#     NUNCA usar SYSTEM: no vería la distro WSL.
schtasks /create /tn "BI_ETL_Diario" /sc DAILY /st 06:00 /rl HIGHEST `
  /ru "$env:COMPUTERNAME\bi_admin" /rp `
  /tr "powershell.exe -NoProfile -ExecutionPolicy Bypass -File C:\BI_Scripts\run_etl.ps1"

# 9.4 Prueba inmediata sin esperar a mañana
schtasks /run /tn "BI_ETL_Diario"
Get-Content C:\BI_Logs\etl_$(Get-Date -Format yyyyMMdd).log -Tail 20
```

## 10. Programar el backup diario (07:00)

```powershell
Set-Content -Encoding utf8 C:\BI_Scripts\backup_edw.ps1 @'
$fecha = Get-Date -Format "yyyyMMdd"
wsl -d Ubuntu-22.04 -u root -- bash -lc "docker exec bi_postgres_edw pg_dump -U etl_user -d edw -Fc -f /tmp/edw.dump && docker cp bi_postgres_edw:/tmp/edw.dump /mnt/c/BI_Backups/edw_$fecha.dump && docker exec bi_postgres_edw rm -f /tmp/edw.dump"
# Retención 30 días
Get-ChildItem C:\BI_Backups\edw_*.dump | Where-Object LastWriteTime -lt (Get-Date).AddDays(-30) | Remove-Item -Force
'@

schtasks /create /tn "BI_Backup_EDW" /sc DAILY /st 07:00 /rl HIGHEST `
  /ru "$env:COMPUTERNAME\bi_admin" /rp `
  /tr "powershell.exe -NoProfile -ExecutionPolicy Bypass -File C:\BI_Scripts\backup_edw.ps1"

schtasks /run /tn "BI_Backup_EDW"
Get-ChildItem C:\BI_Backups          # debe aparecer edw_YYYYMMDD.dump (> 0 bytes)
```

> Pedir a TI que incluya `C:\BI_Backups` en el respaldo corporativo — el histórico de
> snapshots NO es regenerable desde el ERP.

## 11. Acceso remoto al EDW (5433 por VPN, restringido)

WSL2 usa NAT: el puerto 5433 publicado por Docker vive en la IP interna de WSL, que
**cambia en cada arranque**. Se refresca con una tarea de inicio:

```powershell
Set-Content -Encoding utf8 C:\BI_Scripts\wsl_portproxy.ps1 @'
$ip = (wsl -d Ubuntu-22.04 hostname -I).Trim().Split(" ")[0]
netsh interface portproxy delete v4tov4 listenport=5433 listenaddress=0.0.0.0 2>$null
netsh interface portproxy add v4tov4 listenport=5433 listenaddress=0.0.0.0 connectport=5433 connectaddress=$ip
'@

schtasks /create /tn "BI_WSL_PortProxy" /sc ONSTART /rl HIGHEST `
  /ru "$env:COMPUTERNAME\bi_admin" /rp `
  /tr "powershell.exe -NoProfile -ExecutionPolicy Bypass -File C:\BI_Scripts\wsl_portproxy.ps1"
schtasks /run /tn "BI_WSL_PortProxy"

# Firewall: permitir 5433 SOLO desde las IPs de administración/VPN (editar la lista)
New-NetFirewallRule -DisplayName "BI EDW 5433 (VPN admin)" -Direction Inbound `
  -Protocol TCP -LocalPort 5433 -Action Allow -RemoteAddress 10.0.0.0/24
```

Prueba desde el laptop (conectado a la VPN):

```powershell
# En el laptop de desarrollo:
Test-NetConnection <IP_DEL_SERVIDOR> -Port 5433
# y en el .env local de desarrollo: PG_HOST=<IP_DEL_SERVIDOR>, PG_PORT=5433
```

## 12. Simulacro de resiliencia (no saltarse)

```powershell
# 12.1 Reiniciar el servidor y verificar que todo vuelve solo
Restart-Computer
# Tras el reinicio:
wsl -d Ubuntu-22.04 -- docker ps        # bi_postgres_edw debe estar Up (restart: unless-stopped)
netsh interface portproxy show all      # 5433 mapeado (tarea ONSTART)
schtasks /run /tn "BI_ETL_Diario"       # corrida manual OK

# 12.2 Prueba de restauración de backup (contenedor temporal, sin tocar el real)
wsl -d Ubuntu-22.04 -u root -- bash -lc "
  docker run -d --name pg_restore_test -e POSTGRES_PASSWORD=test postgres:16-alpine && sleep 10 &&
  docker cp /mnt/c/BI_Backups/edw_$(Get-Date -Format yyyyMMdd).dump pg_restore_test:/tmp/edw.dump &&
  docker exec pg_restore_test bash -c 'createdb -U postgres edw && pg_restore -U postgres -d edw /tmp/edw.dump' &&
  docker exec pg_restore_test psql -U postgres -d edw -c 'SELECT COUNT(*) FROM edw.fact_ventas_detalle;' ;
  docker rm -f pg_restore_test"
```

## 13. Chequeo de salud semanal (manual, 1 minuto)

```powershell
wsl -d Ubuntu-22.04 -u root -- bash -lc "docker exec bi_postgres_edw psql -U etl_user -d edw -c \"
SELECT f.fecha_completa AS dia, COUNT(*) AS filas_snapshot
FROM edw.fact_inventario_snapshot s JOIN edw.dim_fecha f ON s.fecha_sk = f.fecha_sk
WHERE f.fecha_completa >= CURRENT_DATE - 7 GROUP BY 1 ORDER BY 1;\""
```

Debe haber **una fila por cada día** de la última semana. Un día faltante = revisar
`C:\BI_Logs\etl_<fecha>.log` de ese día y re-ejecutar `schtasks /run /tn "BI_ETL_Diario"`
(la idempotencia del orquestador hace seguro re-correr — reemplaza solo la foto de hoy;
el día perdido en sí no es recuperable, por eso importa detectarlo pronto).

---

## Anexo A — Plan B: instalación nativa sin Docker (solo si WSL2 es inviable)

Resumen (el ETL ya soporta el driver nativo de Windows — ver `.env.example` y auditoría 06):

1. Instalar **PostgreSQL 16 para Windows** (instalador EDB), puerto 5433, usuario `etl_user`, BD `edw`.
2. Ejecutar los DDL **en orden** (aquí no hay auto-init):
   ```powershell
   $env:PGPASSWORD="<PG_PASSWORD>"
   Get-ChildItem C:\proyect_bi\edw\0*.sql | Sort-Object Name | ForEach-Object {
     & "C:\Program Files\PostgreSQL\16\bin\psql.exe" -h localhost -p 5433 -U etl_user -d edw -f $_.FullName
   }
   ```
3. Instalar el **cliente SQL Anywhere** (driver ODBC nativo) y verificar su nombre exacto en
   `Administrador de orígenes de datos ODBC (64 bits)` → pestaña Drivers.
4. Instalar **Python 3.11** + dependencias: `pip install -r C:\proyect_bi\etl\requirements.txt`.
5. `.env`: igual que §5 pero `DB_DRIVER=<nombre exacto del driver ODBC>` (p.ej. `SQL Anywhere 17`)
   y `PG_HOST=localhost`, `PG_PORT=5433`. `TZ` no es necesario (el proceso usa la hora local de Windows).
6. Tarea programada 06:00: `python C:\proyect_bi\etl\orchestrator.py` (mismo esquema de logs de §9).
7. Backup diario con `pg_dump.exe` nativo (mismo esquema de §10).

Desventajas ya aceptadas al elegir este plan: sin auto-init de DDL, sin aislamiento de
dependencias y sin paridad exacta con el entorno Docker validado.
