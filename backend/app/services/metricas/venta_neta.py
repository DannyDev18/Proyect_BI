# backend/app/services/metricas/venta_neta.py
"""Definición canónica de **Venta Neta** (G-02, docs/features/plan_madurez_bi_toma_decisiones.md).

> **Venta Neta** = `SUM(edw.fact_ventas_detalle.subtotal_neto)`
>                − `SUM(edw.fact_devoluciones.total_linea_devolucion)`
> sobre documentos con `dim_estado_documento.estado_factura = 'P'` (regla de negocio 1) y
> excluyendo la fila centinela `-1` (regla 12).

Notas de la definición, todas validadas (docs/auditoria/39_madurez_bi_toma_decisiones.md):

- `subtotal_neto` **ya viene post-descuento**: SAP lo calcula en `renglonesfacturas.totren`
  y el ETL lo copia tal cual (auditoría 10). No hay que volver a restar `valor_descuento`.
- **No** se filtra por `desinv`/`es_linea_servicio`: la regla 5 (`desinv='S'`) condiciona el
  **costo** de inventario, no el ingreso. Una línea de servicio es venta real.
- **No** se excluye ninguna clase de producto. La exclusión de `ANALYTICS_CLASES_EXCLUIDAS_MARGEN`
  (RN-BI1) aplica solo al universo de **margen/ROI**, nunca al de ingresos.
- Las devoluciones se restan **completas** y no son atribuibles a una clase de producto:
  `fact_devoluciones` no tiene el grano necesario.

**Divergencia histórica que este módulo cierra.** Antes existían dos tratamientos de las
líneas de importe negativo:

| Consumidor | Fragmento |
|---|---|
| Gerencia (`analytics_repository`) | `SUM(CASE WHEN subtotal_neto > 0 THEN subtotal_neto ELSE 0 END)` |
| Metas/Comisiones (`goal_repository`) | `SUM(subtotal_neto)` |

Medido sobre el EDW (auditoría 39): **0 líneas negativas en 522.477** del histórico, es decir
la divergencia era **latente, no activa** -- ambas definiciones dan hoy el mismo número. Se
conserva la variante defensiva (`> 0`) como canónica porque `fact_transformer` declara como
*"Pendiente de validar"* el supuesto de que una cantidad negativa signifique devolución
(auditoría 08, F13/F14): si algún día entran líneas negativas, se contarían dos veces --
una como venta negativa y otra vía `fact_devoluciones`.
"""
from typing import Final

# Alias de tabla que los repositorios deben usar al ensamblar estos fragmentos.
ALIAS_VENTAS: Final = "f"
ALIAS_DEVOLUCIONES: Final = "fd"
ALIAS_ESTADO: Final = "ed"

# Regla 1 (`estado='P'`) + regla 12 (centinela). El valor de `:estado_valido` lo aporta el
# repositorio desde `settings.ESTADO_DOCUMENTO_VALIDO` -- nunca un literal en el SQL.
FILTRO_ESTADO_VALIDO: Final = (
    f"{ALIAS_ESTADO}.estado_documento_sk <> -1 AND {ALIAS_ESTADO}.estado_factura = :estado_valido"
)

# Venta bruta: solo líneas de importe positivo (ver nota de divergencia en el docstring).
SQL_VENTA_BRUTA: Final = (
    f"SUM(CASE WHEN {ALIAS_VENTAS}.subtotal_neto > 0 THEN {ALIAS_VENTAS}.subtotal_neto ELSE 0 END)"
)

# Monto devuelto en el mismo recorte. Se resta completo de la venta bruta.
SQL_DEVOLUCIONES_MONTO: Final = (
    f"COALESCE(SUM({ALIAS_DEVOLUCIONES}.total_linea_devolucion), 0.0)"
)


def definicion_venta_neta() -> dict[str, str]:
    """Descripción legible de la métrica, para exponerla en `/system/provenance` y en el
    diccionario de indicadores sin duplicar el texto en otro archivo."""
    return {
        "nombre": "Venta Neta",
        "formula": "SUM(fact_ventas_detalle.subtotal_neto > 0) - SUM(fact_devoluciones.total_linea_devolucion)",
        "grano": "línea de factura, agregable a vendedor / sucursal / período",
        "filtros_obligatorios": "dim_estado_documento.estado_factura = 'P' (regla 1); excluye centinela -1 (regla 12)",
        "fuente": "edw.fact_ventas_detalle + edw.fact_devoluciones",
        "consumidores": "KPIs de Gerencia, Metas, Comisiones (plana y variable), Cumplimiento",
        "referencia": "docs/diccionario_indicadores.md; docs/auditoria/39_madurez_bi_toma_decisiones.md",
    }
