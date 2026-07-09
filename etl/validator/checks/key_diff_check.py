# checks/key_diff_check.py
import pandas as pd

from validator.checks.base_check import Check
from validator.models.result_types import CheckResult, Severity


class KeyDiffCheck(Check):
    """Mide el % de filas del EDW cuyas FKs resolvieron al registro centinela -1 ("Desconocido"),
    por columna. Reutiliza la convención de la regla de negocio §12 (prohibido el fallback a
    filas arbitrarias; toda llave no resuelta cae en -1 y debe medirse, no ignorarse)."""

    name = "key_diff_check"

    def __init__(self, umbral_warning_pct: float = 1.0, umbral_critical_pct: float = 5.0):
        self.umbral_warning_pct = umbral_warning_pct
        self.umbral_critical_pct = umbral_critical_pct

    def run(self, orphan_row: pd.Series) -> CheckResult:
        total = int(orphan_row.get("filas_total") or 0)
        columnas_huerfanas = {
            c: int(v or 0) for c, v in orphan_row.items() if c != "filas_total"
        }

        if total == 0:
            return CheckResult(
                check_name=self.name, severity=Severity.OK,
                descripcion="Sin filas en el rango evaluado.",
            )

        peor_pct = 0.0
        detalle_partes = []
        for col, cnt in columnas_huerfanas.items():
            pct = cnt / total * 100
            if cnt:
                detalle_partes.append(f"{col}={cnt} ({pct:.2f}%)")
            peor_pct = max(peor_pct, pct)

        if peor_pct == 0:
            severity = Severity.OK
        elif peor_pct <= self.umbral_warning_pct:
            severity = Severity.WARNING
        else:
            severity = Severity.CRITICAL

        return CheckResult(
            check_name=self.name,
            severity=severity,
            descripcion=(
                "Llaves huérfanas (centinela -1): " + (", ".join(detalle_partes) or "ninguna")
            ),
            valor_edw=peor_pct,
        )
