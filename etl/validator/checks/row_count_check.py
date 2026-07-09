# checks/row_count_check.py
import pandas as pd

from validator.checks.base_check import Check
from validator.models.result_types import CheckResult, Severity


class RowCountCheck(Check):
    name = "row_count_check"

    def run(self, prod_row: pd.Series, edw_row: pd.Series) -> CheckResult:
        filas_prod = int(prod_row["filas"] or 0)
        filas_edw = int(edw_row["filas"] or 0)
        delta = filas_edw - filas_prod
        pct = (abs(delta) / filas_prod * 100) if filas_prod else (100 if filas_edw else 0)

        if filas_prod == 0 and filas_edw == 0:
            severity = Severity.OK
        elif pct == 0:
            severity = Severity.OK
        elif pct <= 0.1:
            severity = Severity.WARNING
        else:
            severity = Severity.CRITICAL

        return CheckResult(
            check_name=self.name,
            severity=severity,
            descripcion=f"Producción={filas_prod} filas, EDW={filas_edw} filas (delta={delta}, {pct:.2f}%).",
            valor_produccion=filas_prod,
            valor_edw=filas_edw,
            delta=delta,
        )
