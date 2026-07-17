# backend/app/schemas/system.py
from pydantic import BaseModel


class ProvenanceModelo(BaseModel):
    nombre: str
    algoritmo: str | None = None
    entrenado_en: str | None = None
    activo: bool


class ProvenanceResponse(BaseModel):
    ultima_carga_dw: str | None = None
    modelos: list[ProvenanceModelo]


class EtlControlEntry(BaseModel):
    tabla_destino: str
    estado: str | None = None
    ultimo_etl_ok: str | None = None
    registros_cargados: int | None = None
    duracion_seg: int | None = None
    mensaje_error: str | None = None
    fecha_ejecucion: str | None = None


class SystemHealthResponse(BaseModel):
    """Panel de salud del sistema (Fase 2 Admin, docs/features/
    plan_correcciones_pendientes.md §3) -- solo administrador."""
    etl_detalle: list[EtlControlEntry]
    logins_fallidos_ventana_horas: int
    logins_fallidos_conteo: int
