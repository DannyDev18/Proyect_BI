# config/validation_rules.py
"""Catálogo declarativo de entidades reconciliables entre Producción (SAP) y el EDW.

Igual que PIPELINE_CONFIG en etl/orchestrator.py, una entidad no listada aquí no se valida:
esto es intencional, evita "código muerto" silencioso. El validator NO importa
PIPELINE_CONFIG ni ningún módulo del ETL (extractors/transformers/loaders/orchestrator) para
mantenerse desacoplado; solo reutiliza connectors/ y config/settings.py.

Cada entrada declara:
  - nombre:        identificador de la entidad (usado en el reporte y en --entidad)
  - tabla_edw:      tabla destino en edw.* (para el check de completitud en edw.etl_control)
  - query_prod:     archivo .sql (SELECT-only) contra Producción, tokenizado {CODEMP}/{ESTADO}/{FECHA_DESDE}
  - query_edw:      archivo .sql equivalente contra el EDW, tokenizado {FECHA_DESDE}
  - query_edw_dup:  archivo .sql opcional que cuenta grupos duplicados en el EDW
  - query_edw_keys: archivo .sql opcional que cuenta llaves huérfanas (centinela -1) en el EDW
  - tolerancia_pct: % de diferencia tolerado en sumatorias antes de marcar WARNING/CRITICAL
"""

from dataclasses import dataclass, field


@dataclass
class EntityRule:
    nombre: str
    tabla_edw: str
    query_prod: str
    query_edw: str
    query_edw_dup: str = ""
    query_edw_keys: str = ""
    tolerancia_pct: float = 0.5  # diferencias por debajo de esto se consideran redondeo, no hallazgo


ENTITIES: list[EntityRule] = [
    EntityRule(
        nombre="ventas",
        tabla_edw="fact_ventas_detalle",
        query_prod="ventas_check.sql",
        query_edw="ventas_check.sql",
        query_edw_dup="ventas_duplicates.sql",
        query_edw_keys="ventas_orphan_keys.sql",
    ),
    EntityRule(
        nombre="movimientos_inventario",
        tabla_edw="fact_movimientos_inventario",
        query_prod="movimientos_inventario_check.sql",
        query_edw="movimientos_inventario_check.sql",
        query_edw_dup="movimientos_inventario_duplicates.sql",
        query_edw_keys="movimientos_inventario_orphan_keys.sql",
    ),
    # Agregar aquí nuevas entidades a medida que se necesiten (compras, cobros_cxc, pagos_cxp,
    # nomina, movimientos_caja, devoluciones...), replicando el patrón de archivos .sql en
    # queries/produccion/ y queries/edw/. No se listan todas de entrada para no validar
    # agregados que nadie ha revisado todavía (mismo criterio que PIPELINE_CONFIG).
]


def get_entity(nombre: str) -> EntityRule:
    for e in ENTITIES:
        if e.nombre == nombre:
            return e
    raise ValueError(f"Entidad '{nombre}' no está registrada en ENTITIES (validation_rules.py).")
