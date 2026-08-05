# backend/tests/unit/test_inventory_module_boundary.py
"""Guarda de frontera del módulo de Inventario/Reabastecimiento (`app/inventory/`,
Fase 7 de docs/features/plan_modulo_inventario_reabastecimiento.md, auditoría 52).

Invariante real que este test protege: `engine.py` es el motor puro del módulo (mismo
patrón que `commission_variable_engine.py`/`goal_pipeline_stages.py`) -- sin I/O, sin
`settings`, testeable sin base de datos. Si alguien agrega un `from app.repositories...`
o un `from app.core.config import settings` dentro de `engine.py`, este test falla en vez
de que la regresión se descubra en producción (una fórmula "pura" que de repente necesita
una sesión de BD para poder testearse)."""
import ast
from pathlib import Path

# Módulos que `engine.py` NUNCA debe importar -- cualquiera de estos es I/O o acceso a
# configuración/estado de aplicación, ambos prohibidos en el motor puro.
_PREFIJOS_PROHIBIDOS = (
    "app.repositories",
    "app.models",
    "app.database",
    "app.core.config",
    "app.ml",
    "sqlalchemy",
)

_INVENTORY_DIR = Path(__file__).resolve().parents[2] / "app" / "inventory"


def _imports_de(archivo: Path) -> list[str]:
    tree = ast.parse(archivo.read_text(encoding="utf-8"))
    modulos: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modulos.extend(n.name for n in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modulos.append(node.module)
    return modulos


def test_engine_no_importa_io_ni_settings():
    archivo = _INVENTORY_DIR / "engine.py"
    modulos = _imports_de(archivo)
    violaciones = [
        m for m in modulos
        if any(m == prefijo or m.startswith(prefijo + ".") for prefijo in _PREFIJOS_PROHIBIDOS)
    ]
    assert not violaciones, (
        f"app/inventory/engine.py debe ser un motor puro sin I/O -- imports prohibidos "
        f"encontrados: {violaciones}"
    )


def test_engine_no_define_clases_con_sesion_de_base_de_datos():
    """Segunda señal de la misma invariante: ninguna función/clase de `engine.py` recibe
    un parámetro llamado `db`/`session` -- si aparece uno, el motor dejó de ser puro."""
    archivo = _INVENTORY_DIR / "engine.py"
    tree = ast.parse(archivo.read_text(encoding="utf-8"))
    nombres_prohibidos = {"db", "session"}
    ofensores: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            argumentos = {a.arg for a in node.args.args}
            if argumentos & nombres_prohibidos:
                ofensores.append(node.name)
    assert not ofensores, f"Funciones de engine.py con un parámetro de sesión de BD: {ofensores}"


def test_paquete_inventory_expone_su_api_publica():
    """`app.inventory.__init__` debe seguir reexportando lo que el resto del sistema
    necesita para el wiring de FastAPI (`dependencies.py`) sin que cada consumidor tenga
    que conocer la estructura interna del paquete."""
    import app.inventory as inventory

    for nombre in ("engine", "ReplenishmentService", "ReplenishmentConfigService",
                   "ReplenishmentConfigRepository", "ReplenishmentProposalRepository"):
        assert hasattr(inventory, nombre), f"app.inventory no expone '{nombre}' en su API pública"
