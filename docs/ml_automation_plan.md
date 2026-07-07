# Plan de Automatización Diaria del Pipeline de Machine Learning

Dado que el ecosistema del proyecto utiliza **Docker Compose** y está diseñado bajo una arquitectura de microservicios con volúmenes compartidos (`./ml/models:/app/ml_models`), la automatización diaria no requiere arquitecturas MLOps hiper-complejas (como Airflow puro) al menos inicialmente.

La estrategia más resiliente se basa en **Cron Jobs montados a nivel Sistema Operativo en el Servidor Host** que orquesten los binarios de Docker.

## 1. Diseño del Script Orquestador (Bash / PowerShell)

Deberías crear un archivo en tu máquina anfitriona (ej. `retrain_ml_cron.ps1` o `retrain_ml_cron.sh`):

### Si es Linux (Bash):

```bash
#!/bin/bash
# Ruta de tu repositorio
cd /ruta/hacia/Proyect_BI

echo "Iniciando reentrenamiento diario MLOps..."
# Ejecutamos el pipeline (asume que docker-compose tiene un contenedor especializado, o usando el python nativo/venv del host si el ML no está dockerizado)
source .venv/bin/activate
python ml/main.py

echo "Publicando (reiniciando backend para cargar modelos)..."
python ml/publish_models.py
echo "Proceso finalizado."
```

### Si es Windows (PowerShell):

```powershell
Set-Location -Path "C:\ruta\hacia\Proyect_BI"
# Activar entorno virtual
& ".\.venv\Scripts\Activate.ps1"

# Entrenar
python ml\main.py

# Publicar (docker compose restart backend)
python ml\publish_models.py
```

## 2. Configuración de Tareas Automáticas

### En Windows Server / Local (Task Scheduler)

1. Abrir **Programador de Tareas (Task Scheduler)**.
2. Hacer clic en **Crear tarea básica...**
3. Nombrarla `Retrain_ML_Pipeline_BI`.
4. Seleccionar el disparador: **Diariamente**, a las `03:00 AM` (recomendado para que la base de datos no sufra carga de concurrencia).
5. Acción: **Iniciar un programa**.
   - **Programa o script:** `powershell.exe`
   - **Argumentos:** `-ExecutionPolicy Bypass -File C:\ruta\hacia\retrain_ml_cron.ps1`
6. Finalizar la configuración asegurándose que tiene los permisos necesarios de Docker (ejecutar con los máximos privilegios).

### En Linux Server (Cron Tab)

Ejecutar `crontab -e` y añadir la siguiente línea para ejecutarlo todos los días a las 03:00 de la madrugada y guardar los logs externamente para depuración:

```cron
0 3 * * * /ruta/hacia/Proyect_BI/retrain_ml_cron.sh >> /var/log/ml_daily_retrain.log 2>&1
```

## 3. Beneficios de este diseño:

- **Zero Downtime:** El backend actualiza modelos reiniciándose en segundos (menos de 5 segundos de downtime local gracias al volumen compartido).
- **Competitividad Constante:** El `model_selector.py` (que elige entre CatBoost, LightGBM, XGBoost, etc.) se ejecutará de cero frente a la nueva data diaria del almacén, asegurando que si la temporalidad cambia drásticamente un mes, el mejor _tipo de algoritmo_ también podría rotar de manera automática.
- **Trazabilidad:** Puedes expandir el script para enviar la salida del `python ml/main.py` a Slack o Email en caso de un `exit 1` originado por colapso de datos.
