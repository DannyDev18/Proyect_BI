# report/report_builder.py
"""Ensambla el reporte Markdown final a partir de los ReconciliationResult, en el mismo
formato que los reportes existentes en docs/auditoria/ (fecha, alcance, método, hallazgos)."""
from datetime import datetime

from validator.models.result_types import ReconciliationResult, Severity

ICONOS = {Severity.OK: "OK", Severity.WARNING: "WARNING", Severity.CRITICAL: "CRITICAL"}


def build_report(resultados: list[ReconciliationResult], fecha_desde: str, siguiente_numero: int) -> str:
    fecha = datetime.now().strftime("%Y-%m-%d %H:%M")
    lineas = [
        f"# Auditoría {siguiente_numero:02d} — Validación automática Producción vs EDW",
        "",
        f"- **Fecha:** {fecha}",
        f"- **Alcance:** entidades {[r.entidad for r in resultados]}, rango fecha >= {fecha_desde}",
        "- **Método:** `etl/validator` — SELECT-only contra SAP y contra el EDW (PostgreSQL). "
        "No hubo escrituras a Producción ni al EDW; comparación por agregados (conteos, "
        "sumatorias, rangos de fecha, duplicados, llaves huérfanas).",
        "",
        "## Resumen ejecutivo",
        "",
        "| Entidad | Evaluado | OK | WARNING | CRITICAL |",
        "|---|---|---|---|---|",
    ]

    for r in resultados:
        if not r.evaluado:
            lineas.append(f"| {r.entidad} | NO ({r.motivo_no_evaluado}) | - | - | - |")
            continue
        n_ok = sum(1 for c in r.checks if c.severity == Severity.OK)
        n_warn = sum(1 for c in r.checks if c.severity == Severity.WARNING)
        n_crit = sum(1 for c in r.checks if c.severity == Severity.CRITICAL)
        lineas.append(f"| {r.entidad} | SI | {n_ok} | {n_warn} | {n_crit} |")

    lineas += ["", "## Hallazgos por entidad", ""]

    for r in resultados:
        lineas.append(f"### {r.entidad} (`{r.tabla_edw}`)")
        lineas.append("")
        if not r.evaluado:
            lineas.append(f"**No evaluado.** {r.motivo_no_evaluado}")
            lineas.append("")
            continue
        for c in r.checks:
            lineas.append(f"- **[{ICONOS[c.severity]}] {c.check_name}** — {c.descripcion}")
            if c.detalle:
                lineas.append(f"  - Detalle: {c.detalle}")
        lineas.append("")

    lineas += ["## Resumen de recomendaciones por prioridad", ""]
    hallazgos_criticos = [
        (r.entidad, c) for r in resultados if r.evaluado for c in r.checks if c.severity == Severity.CRITICAL
    ]
    hallazgos_warning = [
        (r.entidad, c) for r in resultados if r.evaluado for c in r.checks if c.severity == Severity.WARNING
    ]
    no_evaluados = [r.entidad for r in resultados if not r.evaluado]

    if no_evaluados:
        lineas.append(f"- **Alta** — Completar/reintentar el ETL para: {', '.join(no_evaluados)}.")
    for entidad, c in hallazgos_criticos:
        lineas.append(f"- **Alta** — [{entidad}] {c.check_name}: {c.descripcion}")
    for entidad, c in hallazgos_warning:
        lineas.append(f"- **Media** — [{entidad}] {c.check_name}: {c.descripcion}")
    if not hallazgos_criticos and not hallazgos_warning and not no_evaluados:
        lineas.append("- Ninguna. Todas las entidades evaluadas están reconciliadas dentro de tolerancia.")

    return "\n".join(lineas) + "\n"
