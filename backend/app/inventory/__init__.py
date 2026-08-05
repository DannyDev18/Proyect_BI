# backend/app/inventory/__init__.py
"""Módulo de Gestión de Inventario y Reabastecimiento (MGIR), docs/features/plan_modulo_
inventario_reabastecimiento.md. Dueño único de las fórmulas de inventario de Bodega
(estadística de demanda, stock de seguridad, punto de reorden, riesgo de quiebre, ABC/XYZ,
simulación what-if, propuestas de compra).

API pública del paquete -- el resto del sistema importa de aquí, no de los submódulos:
- `engine`: motor puro (sin I/O, sin `settings`) con las fórmulas de inventario. Se expone
  el submódulo completo (no funciones sueltas) porque `WarehouseService` (Fase 2 del plan)
  y los tests del motor lo consumen función por función -- reexportar cada símbolo
  individualmente aquí solo agregaría un nivel de indirección sin beneficio.
- `ReplenishmentService`: orquestación (lista priorizada, resumen, alertas, simulación,
  propuestas de compra).
- `ReplenishmentConfigService`/`ReplenishmentConfigRepository`/`ReplenishmentProposalRepository`:
  necesarios en `app/api/dependencies.py` para el wiring de inyección de dependencias de
  FastAPI (que construye instancias concretas), no una violación de frontera."""
from app.inventory import engine
from app.inventory.config_service import ReplenishmentConfigService
from app.inventory.proposals import ReplenishmentProposalRepository
from app.inventory.repository import ReplenishmentConfigRepository
from app.inventory.service import ReplenishmentService

__all__ = [
    "engine",
    "ReplenishmentService",
    "ReplenishmentConfigService",
    "ReplenishmentConfigRepository",
    "ReplenishmentProposalRepository",
]
