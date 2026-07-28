# backend/app/services/training_service.py
"""Orquesta el reentrenamiento de modelos ML disparando un contenedor efímero de la
imagen `ml` (ya construida por `docker compose build ml`) vía el socket de Docker
compartido -- Fase 3, docs/features/plan_mejora_pipeline_ml.md §5.2.1 opción 1. El
backend nunca importa ni ejecuta código de `ml/` directamente, preservando la frontera
backend↔entrenamiento que la arquitectura protege a propósito (CLAUDE.md).

Usa `docker run` (NO `docker compose run`), decisión validada empíricamente en este
entorno (Docker Desktop / Windows): `docker compose` necesita LEER localmente tanto el
YAML (`-f`) como el `.env` que auto-carga para interpolación (`${VAR}`) -- ambas lecturas
son 100% client-side, y este contenedor no tiene una ruta local que corresponda al
`--project-directory` real del host (`HOST_PROJECT_DIR`, con backslashes de Windows), así
que Compose fallaba con `env file ... not found` al intentar auto-cargar `.env` relativo
a esa ruta. `docker run -v "<HOST_PROJECT_DIR>\\ml:/app"` en cambio solo necesita que el
DAEMON (que sí corre en el host real) resuelva un string de bind-mount -- comprobado que
Docker Desktop acepta rutas estilo Windows en `-v` sin que el CLIENT (este contenedor,
Linux) necesite verlas localmente. `--network proyect_bi_default` conecta el contenedor
efímero a la misma red que `postgres_edw` (nombre de red = `<nombre_proyecto>_default`,
convención de Compose derivada del nombre del directorio del proyecto).

Reemplaza el enfoque previo (subprocess local sobre `ML_SOURCE_DIR`), que además estaba
roto en la práctica: ejecutaba `python <script>.py` sobre cada archivo de
`ml/src/training/`, pero esos módulos solo DEFINEN funciones -- ninguno tenía un bloque
`__main__`, así que "reentrenar" no entrenaba nada y siempre reportaba éxito. El nuevo
entrypoint (`ml/retrain_all.py`) sí entrena y aplica gating de campeón único
(`ml/src/training/promotion.py`) antes de devolver el control."""
import logging
import os
import subprocess
from datetime import datetime
from typing import Any

from app.core.config import settings
from app.core.exceptions import ExternalDataError

logger = logging.getLogger("Backend.TrainingService")

CLAVES_VALIDAS = ["sales_rf", "demand_rf", "churn_rf", "segmentation", "association", "anomaly"]

ML_IMAGE = "proyect_bi-ml"
COMPOSE_NETWORK = "proyect_bi_default"


def _forward_pg_env() -> list[str]:
    """`-e KEY=VALUE` para las variables de conexión a Postgres que `ml/` necesita
    dentro del contenedor efímero -- se reenvían los valores que este mismo contenedor
    YA tiene en su propio entorno (mismo Postgres compartido, mismo `.env` original).
    PG_HOST/PORT/USER/DB tienen default de código en `ml/` apuntando a `localhost`
    (pensado para ejecución fuera de Docker), por eso se fuerzan explícitamente a los
    valores de red reales (`postgres_edw:5432`)."""
    pg_password = os.environ.get("PG_PASSWORD")
    if not pg_password:
        raise ExternalDataError("Reentrenamiento no disponible: falta PG_PASSWORD en el entorno del backend.")
    valores = {
        "PG_HOST": os.environ.get("PG_HOST", "postgres_edw"),
        "PG_PORT": os.environ.get("PG_PORT", "5432"),
        "PG_USER": os.environ.get("PG_USER", "etl_user"),
        "PG_DB": os.environ.get("PG_DB", "edw"),
        "PG_PASSWORD": pg_password,
    }
    flags = []
    for k, v in valores.items():
        flags += ["-e", f"{k}={v}"]
    return flags


class TrainingService:
    def __init__(self, docker_socket_path: str | None = None, host_project_dir: str | None = None):
        self.docker_socket_path = docker_socket_path or settings.DOCKER_SOCKET_PATH
        self.host_project_dir = host_project_dir or settings.HOST_PROJECT_DIR
        self._status: dict[str, Any] = {
            "is_training": False,
            "last_run": None,
            "last_status": "Idle",  # Idle, Running, Success, Failed
            "logs": [],
        }

    def get_status(self) -> dict[str, Any]:
        return self._status

    def _log(self, msg: str) -> None:
        logger.info(msg)
        self._status["logs"].append(f"{datetime.now().isoformat()} - {msg}")
        if len(self._status["logs"]) > 50:
            self._status["logs"].pop(0)

    def verificar_disponible(self) -> None:
        """Validación síncrona antes de encolar (mismo patrón que la versión anterior,
        docs/auditoria/36_actualizacion_modulo_admin.md H9): el cliente debe recibir el
        error de inmediato, no enterrado en `GET /admin/modelos/status` tras un 200 falso."""
        if not os.path.exists(self.docker_socket_path):
            raise ExternalDataError(
                f"Reentrenamiento no disponible: no se encontró el socket de Docker "
                f"({self.docker_socket_path}) en este contenedor. Requiere que "
                f"docker-compose.yml monte '/var/run/docker.sock' en el backend "
                f"(Fase 3, docs/features/plan_mejora_pipeline_ml.md §5.2.1)."
            )
        if not self.host_project_dir:
            raise ExternalDataError(
                "Reentrenamiento no disponible: falta la variable de entorno "
                "HOST_PROJECT_DIR (ruta absoluta del proyecto en el HOST, no en este "
                "contenedor -- el daemon resuelve los bind-mounts de 'docker run -v' "
                "contra el filesystem del host)."
            )

    def _ml_volume_arg(self) -> str:
        separador = "\\" if "\\" in self.host_project_dir else "/"
        return f"{self.host_project_dir}{separador}ml:/app"

    def trigger_retraining_pipeline(self, clave: str = "all", disparado_por: str = "panel_admin") -> None:
        """Ejecuta `docker run --rm -v <host>/ml:/app ... proyect_bi-ml python
        retrain_all.py --model <clave>`. Pensado para correr en background
        (`BackgroundTasks`)."""
        if self._status["is_training"]:
            logger.warning("Intento de iniciar entrenamiento mientras ya hay uno en curso.")
            return
        if clave != "all" and clave not in CLAVES_VALIDAS:
            raise ValueError(f"Clave de modelo inválida: '{clave}'. Válidas: {CLAVES_VALIDAS} o 'all'.")

        self.verificar_disponible()

        self._status.update(is_training=True, last_status="Running", logs=[])
        self._log(f"Iniciando reentrenamiento con gating para '{clave}' (disparado por {disparado_por})")

        comando = [
            "docker", "run", "--rm",
            "-v", self._ml_volume_arg(),
            "--network", COMPOSE_NETWORK,
            *_forward_pg_env(),
            ML_IMAGE,
            "python", "retrain_all.py", "--model", clave, "--disparado-por", disparado_por,
        ]
        try:
            self._log(f"Ejecutando: {' '.join(comando)}")
            result = subprocess.run(comando, capture_output=True, text=True, timeout=1800)
            for linea in result.stdout.splitlines()[-30:]:
                self._log(linea)
            if result.returncode != 0:
                self._log(f"FALLO (exit={result.returncode}): {result.stderr[-500:]}")
                self._status["last_status"] = "Failed"
                raise ExternalDataError(f"El reentrenamiento de '{clave}' terminó con errores (exit={result.returncode}).")
            self._log(f"Reentrenamiento de '{clave}' completado.")
            self._status["last_status"] = "Success"
        except subprocess.TimeoutExpired:
            self._log("FALLO: el reentrenamiento excedió el tiempo máximo (30 min).")
            self._status["last_status"] = "Failed"
            raise
        except Exception as e:
            logger.error(f"Error en el pipeline de MLOps: {e}")
            self._status["last_status"] = "Failed"
            raise
        finally:
            self._status["is_training"] = False
            self._status["last_run"] = datetime.now().isoformat()

    def promote_model(self, clave: str, version: str, disparado_por: str) -> dict[str, Any]:
        """Promoción manual o rollback (§3.2/§5.3 del plan): apunta `registry.json` a una
        versión archivada específica sin reentrenar, vía
        `docker run ... proyect_bi-ml python promote.py --model <clave> --to <version>`."""
        if clave not in CLAVES_VALIDAS:
            raise ValueError(f"Clave de modelo inválida: '{clave}'. Válidas: {CLAVES_VALIDAS}.")
        self.verificar_disponible()

        comando = [
            "docker", "run", "--rm",
            "-v", self._ml_volume_arg(),
            "--network", COMPOSE_NETWORK,
            *_forward_pg_env(),
            ML_IMAGE,
            "python", "promote.py", "--model", clave, "--to", version, "--disparado-por", disparado_por,
        ]
        logger.info(f"Ejecutando: {' '.join(comando)}")
        result = subprocess.run(comando, capture_output=True, text=True, timeout=120)
        if result.returncode != 0:
            raise ExternalDataError(f"No se pudo promover '{clave}' a la versión '{version}': {result.stderr[-500:]}")
        return {"clave": clave, "version": version, "stdout": result.stdout.strip()}
