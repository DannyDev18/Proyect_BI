# backend/app/services/system_service.py
"""Procedencia de datos del sistema: última carga del DW + estado real de los 6
modelos ML. Reemplaza el mock `PROVENANCE_FACTS` del frontend (docs/auditoria/
33_actualizacion_modulo_gerencia.md, H4) -- sin modelos ML nuevos, reutiliza
`ModelLoader` (mismo patrón de `admin_ml.py::get_models_status`)."""
from typing import Any

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
