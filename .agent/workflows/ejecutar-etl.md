---
description: Ejecutar pipeline ETL (Extracción desde SAP a Data Warehouse PostgreSQL)
---

Sigue este procedimiento para ejecutar la carga de datos del ETL ya sea de manera aislada en desarrollo local o verificando la ejecución dockerizada:

### Opción A: Ejecución Local en Desarrollo (Paso a Paso)

Usa este método para depurar o regenerar los datos directamente en el Data Warehouse de desarrollo:

1. **Iniciar el Contenedor de la Base de Datos**
   Si no lo has hecho, levanta únicamente la instancia de la base de datos PostgreSQL:
   `docker compose up -d postgres_edw`
   _(Esto iniciará el contenedor y expondrá el puerto 5433 en localhost)_

2. **Preparar el Entorno Virtual Python**
   Asegúrate de estar en la raíz de la carpeta de trabajo (`c:\Tesis`):
   `python -m venv .venv`
   - Activación en Windows (PowerShell):
     `.venv\Scripts\Activate.ps1`
   - Activación en Linux/macOS:
     `source .venv/bin/activate`

3. **Instalar Dependencias**
   Instala las librerías necesarias especificadas en `etl/requirements.txt`:
   `pip install -r etl/requirements.txt`

4. **Ejecutar el Proceso ETL (Carga de Semilla)**
   Ejecuta el script de poblamiento de hechos y dimensiones que genera las ventas coherentes:
   `python etl/seed_data.py`
   _(Este script generará y cargará la dimensión de tiempo, productos locales, sucursales y la facturación histórica mostrando un resumen del total insertado)_

---

### Opción B: Ejecución/Verificación en Entorno Dockerizado

Si levantaste todo el stack con Docker Compose, el pipeline se ejecuta de manera automatizada:

1. **Iniciar el Contenedor del ETL**
   El contenedor `etl` se ejecuta automáticamente al iniciar. Si necesitas volver a correr la carga de datos sin destruir la base de datos, ejecuta:
   `docker compose start etl`

2. **Ver logs de la carga ETL**
   Monitorea la consola del ETL para comprobar que finalizó sin errores:
   `docker compose logs -f etl`

---

### Verificación de la Carga de Datos en el EDW

Para certificar que los datos analíticos se subieron correctamente, ejecuta la siguiente consulta SQL en el contenedor de base de datos:

- **Contar registros de hechos (Ventas Detalle):**
  `docker exec -it bi_postgres_edw psql -U etl_user -d edw -c "SELECT COUNT(*) AS total_facturas_lineas FROM edw.fact_ventas_detalle;"`
  _(Debería mostrar alrededor de ~5,000 registros insertados)_

- **Consistencia por sucursal:**
  `docker exec -it bi_postgres_edw psql -U etl_user -d edw -c "SELECT s.nombre_sucursal, COUNT(f.venta_sk) FROM edw.fact_ventas_detalle f JOIN edw.dim_sucursal s ON s.sucursal_sk = f.sucursal_sk GROUP BY s.nombre_sucursal ORDER BY 2 DESC;"`
