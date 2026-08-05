# backend/app/services/replenishment_config_service.py
"""Validación de la configuración editable del motor de Reabastecimiento (docs/features/
plan_reabastecimiento_inteligente.md §6.3)."""
from app.core.exceptions import ValidationError
from app.inventory.repository import ReplenishmentConfigRepository

CLASES_ABC_VALIDAS = {"A", "B", "C"}
NIVELES_SERVICIO_VALIDOS = {0.90, 0.95, 0.975, 0.99}


class ReplenishmentConfigService:
    def __init__(self, repo: ReplenishmentConfigRepository):
        self.repo = repo

    def get_politica(self):
        return self.repo.get_politica()

    def update_politica(self, clase_abc: str, nivel_servicio: float, usuario_id: int | None):
        if clase_abc not in CLASES_ABC_VALIDAS:
            raise ValidationError(f"Clase ABC inválida: '{clase_abc}'. Valores permitidos: A, B, C.")
        if not (0.0 < nivel_servicio < 1.0):
            raise ValidationError("El nivel de servicio debe estar entre 0 y 1 (ej. 0.95 = 95%).")
        try:
            return self.repo.update_politica(clase_abc, nivel_servicio, usuario_id)
        except ValueError as e:
            raise ValidationError(str(e)) from e

    def get_lead_times(self):
        return self.repo.get_lead_times()

    def upsert_lead_time(
        self, dias: float, usuario_id: int | None,
        producto: str | None = None, categoria: str | None = None, proveedor: str | None = None,
    ):
        niveles = [v for v in (producto, categoria, proveedor) if v]
        if len(niveles) != 1:
            raise ValidationError("Debe especificarse exactamente uno de producto, categoria o proveedor.")
        if dias <= 0:
            raise ValidationError("El lead time debe ser un número de días mayor a 0.")
        return self.repo.upsert_lead_time(dias, usuario_id, producto=producto, categoria=categoria, proveedor=proveedor)

    def delete_lead_time(self, lead_time_id: int) -> None:
        try:
            self.repo.delete_lead_time(lead_time_id)
        except ValueError as e:
            raise ValidationError(str(e)) from e
