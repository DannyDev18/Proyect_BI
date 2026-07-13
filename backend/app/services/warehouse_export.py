# backend/app/services/warehouse_export.py
"""Export a Excel de los reportes del módulo Bodega (§2.1 del requerimiento: "Opción de
exportar a Excel para edición"). El PDF se resuelve en el frontend con vista imprimible
(decisión de la auditoría 23 §Decisiones-4). Generador genérico: cada lista de dicts del
reporte se vuelve una hoja con encabezados; los escalares van a la hoja "Resumen"."""
import io
from typing import Any

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

_HEADER_FILL = PatternFill(start_color="1E293B", end_color="1E293B", fill_type="solid")
_HEADER_FONT = Font(color="FFFFFF", bold=True)

# Nombre de hoja de Excel: máx 31 caracteres y sin []:*?/\
_INVALIDOS_HOJA = set('[]:*?/\\')


def _nombre_hoja(nombre: str) -> str:
    limpio = "".join(c for c in nombre if c not in _INVALIDOS_HOJA)
    return (limpio.replace("_", " ").strip().title() or "Hoja")[:31]


def _escribir_tabla(ws, filas: list[dict[str, Any]]) -> None:
    if not filas:
        ws.append(["(sin datos)"])
        return
    columnas: list[str] = []
    for fila in filas:
        for k in fila:
            if k not in columnas:
                columnas.append(k)
    ws.append([c.replace("_", " ").title() for c in columnas])
    for celda in ws[1]:
        celda.fill = _HEADER_FILL
        celda.font = _HEADER_FONT
        celda.alignment = Alignment(horizontal="center")
    for fila in filas:
        ws.append([
            ", ".join(f"{k}: {v}" for k, v in valor.items()) if isinstance(valor := fila.get(c), dict)
            else valor
            for c in columnas
        ])
    for idx, col in enumerate(columnas, start=1):
        ws.column_dimensions[get_column_letter(idx)].width = max(14, min(40, len(col) + 6))


def _aplanar(prefijo: str, valor: Any, escalares: list[tuple[str, Any]], tablas: dict[str, list[dict]]) -> None:
    if isinstance(valor, list) and valor and isinstance(valor[0], dict):
        tablas[prefijo] = valor
    elif isinstance(valor, dict):
        for k, v in valor.items():
            _aplanar(f"{prefijo} {k}" if prefijo else k, v, escalares, tablas)
    elif isinstance(valor, list):
        escalares.append((prefijo, ", ".join(str(v) for v in valor)))
    else:
        escalares.append((prefijo, valor))


def reporte_a_excel(titulo: str, reporte: dict[str, Any]) -> bytes:
    """Convierte el JSON de un reporte de bodega en un XLSX en memoria."""
    escalares: list[tuple[str, Any]] = []
    tablas: dict[str, list[dict]] = {}
    _aplanar("", reporte, escalares, tablas)

    wb = Workbook()
    ws = wb.active
    ws.title = "Resumen"
    ws.append([titulo])
    ws["A1"].font = Font(bold=True, size=14)
    ws.append([])
    for nombre, valor in escalares:
        ws.append([nombre.replace("_", " ").title(), valor])
    ws.column_dimensions["A"].width = 45
    ws.column_dimensions["B"].width = 30

    for nombre, filas in tablas.items():
        _escribir_tabla(wb.create_sheet(_nombre_hoja(nombre)), filas)

    buffer = io.BytesIO()
    wb.save(buffer)
    return buffer.getvalue()
