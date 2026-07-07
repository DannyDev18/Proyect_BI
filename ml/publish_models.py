# ml/publish_models.py
import subprocess
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("MLOps.Deployer")

def publish_models_to_backend():
    """
    Dado que la arquitectura utiliza Docker Compose, los directorios físicos
    de ./ml/models están montados directamente en el contenedor del backend 
    (/app/ml_models). No es necesario copiar archivos de forma interactiva 
    o usar paths del host base. Solamente reiniciamos el contenedor. 
    """
    logger.info("Verificando orquestación con Docker Compose (Volumes)...")
    logger.info("Los archivos generados ya están mapeados en 'bi_backend' mediante el volumen: ./ml/models:/app/ml_models:ro")
    
    logger.info("Reiniciando el contenedor backend para cargar los nuevos binarios a la memoria de la API...")
    try:
        subprocess.run(
            ["docker", "compose", "restart", "backend"],
            check=True
        )
        logger.info("=== El backend Dockerizado ha recargado los modelos con éxito ===")
    except Exception as e:
        logger.error(f"Error reiniciando el servicio de backend con Docker: {e}")

if __name__ == "__main__":
    publish_models_to_backend()
