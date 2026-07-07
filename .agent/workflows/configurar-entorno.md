---
description: Configurar el entorno de desarrollo y levantar contenedores base (Docker Compose)
---

Sigue este procedimiento para inicializar el entorno de desarrollo Dockerizado para este proyecto, de acuerdo con el `docs/manual_ejecucion.md` y `docker-compose.yml`:

1. **Configurar el Archivo de Variables de Entorno**
   Crea y edita el archivo `.env` en la raíz del proyecto (`c:\Tesis\.env`) con la configuración base descrita en el manual:

   ```env
   # ── PostgreSQL Data Warehouse (EDW) ───────────────────────────
   POSTGRES_DB=edw
   POSTGRES_USER=etl_user
   POSTGRES_PASSWORD=mi_super_password_secreto
   DATABASE_URL=postgresql+psycopg2://etl_user:mi_super_password_secreto@localhost:5433/edw
   SECRET_KEY=mvp_d3v_s3cr3t_k3y_ch4ng3_1n_pr0d
   ALGORITHM=HS256
   ACCESS_TOKEN_EXPIRE_MINUTES=480
   BACKEND_CORS_ORIGINS=["http://localhost:5173", "http://localhost:3000"]
   ```

2. **Levantar todos los Servicios**
   Construye las imágenes base e inicia todos los contenedores en segundo plano (`postgres_edw`, `etl`, `backend`, `frontend`) utilizando:
   `docker compose up -d --build`

3. **Verificar el Estado de los Contenedores**
   Comprueba que todos los servicios estén en ejecución y en estado saludable:
   `docker compose ps`
   _El contenedor `bi_etl` se ejecutará una sola vez para poblar el Data Warehouse con la semilla de datos y luego quedará con estado exitoso (Exit 0)._

4. **Verificar la Base de Datos Analítica (EDW)**
   Verifica que la base de datos se haya inicializado con el esquema `edw` y sus tablas correspondientes (`dim_tiempo`, `dim_producto`, `dim_sucursal`, `fact_ventas_detalle`) ejecutando el DDL de `database/init.sql`:
   `docker exec -it bi_postgres_edw psql -U etl_user -d edw -c "\dt edw.*"`

5. **Monitorear el Estado del Backend y Frontend**
   - Logs del backend (FastAPI):
     `docker compose logs -f backend`
   - Comprobar endpoint de salud de la API:
     `curl http://localhost:8000/api/v1/health`
     _(Debería retornar: {"status": "ok", "service": "...", "version": "..."})_
   - Dashboard BI Frontend:
     Accede desde el navegador a `http://localhost:5173`
