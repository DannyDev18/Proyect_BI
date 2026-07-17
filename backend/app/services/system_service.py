# backend/app/services/system_service.py
"""Procedencia de datos del sistema: última carga del DW + estado real de los 6
modelos ML. Reemplaza el mock `PROVENANCE_FACTS` del frontend (docs/auditoria/
33_actualizacion_modulo_gerencia.md, H4) -- sin modelos ML nuevos, reutiliza
`ModelLoader` (mismo patrón de `admin_ml.py::get_models_status`)."""
from typing import Any

from app.core.config import settings
from app.ml.model_loader import MODEL_DISPLAY_NAMES, ModelLoader
from app.repositories.system_repository import SystemRepository


class SystemService:
    def __init__(self, system_repo: SystemRepository, model_loader: ModelLoader):
        self.system_repo = system_repo
        self.model_loader = model_loader

    def get_provenance(self) -> dict[str, Any]:
        ultima_carga = self.system_repo.get_ultima_carga_dw()
        modelos = []
        for key in self.model_loader.keys():
            activo = self.model_loader.is_loaded(key)
            meta = self.model_loader.get_meta(key) if activo else {}
            modelos.append({
                "nombre": MODEL_DISPLAY_NAMES.get(key, key),
                "algoritmo": meta.get("algorithm"),
                "entrenado_en": meta.get("trained_at"),
                "activo": activo,
            })
        return {
            "ultima_carga_dw": ultima_carga.isoformat() if ultima_carga else None,
            "modelos": modelos,
        }

    def get_system_health(self) -> dict[str, Any]:
        """Panel de salud del sistema (Fase 2 Admin, docs/features/
        plan_correcciones_pendientes.md §3): detalle por tabla de `edw.etl_control`
        (antes solo se exponía el máximo global en /system/provenance) + conteo de
        logins fallidos recientes (antes no se registraban en absoluto). Solo
        administrador -- a diferencia de /system/provenance, este detalle operativo no
        se muestra a los otros 3 roles."""
        etl_detalle = self.system_repo.get_etl_control_detalle()
        return {
            "etl_detalle": [
                {
                    "tabla_destino": e["tabla_destino"],
                    "estado": e["estado"],
                    "ultimo_etl_ok": e["ultimo_etl_ok"].isoformat() if e["ultimo_etl_ok"] else None,
                    "registros_cargados": e["registros_cargados"],
                    "duracion_seg": e["duracion_seg"],
                    "mensaje_error": e["mensaje_error"],
                    "fecha_ejecucion": e["fecha_ejecucion"].isoformat() if e["fecha_ejecucion"] else None,
                }
                for e in etl_detalle
            ],
            "logins_fallidos_ventana_horas": settings.ADMIN_LOGINS_FALLIDOS_VENTANA_HORAS,
            "logins_fallidos_conteo": self.system_repo.get_conteo_logins_fallidos(
                settings.ADMIN_LOGINS_FALLIDOS_VENTANA_HORAS
            ),
        }
