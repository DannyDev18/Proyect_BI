# checks/sum_check.py
import pandas as pd

from validator.checks.base_check import Check
from validator.models.result_types import CheckResult, Severity


class SumCheck(Check):
    """Reconcilia una columna de sumatoria (cantidad, valor, costo...) entre Producción y EDW.
    `columna` debe existir con el mismo alias en ambas queries de agregación."""

    name = "sum_check"

    def __init__(self, columna: str, tolerancia_pct: float = 0.5):
        self.columna = columna
        self.tolerancia_pct = tolerancia_pct

    def run(self, prod_row: pd.Series, edw_row: pd.Series) -> CheckResult:
        valor_prod = float(prod_row.get(self.columna) or 0)
        valor_edw = float(edw_row.get(self.columna) or 0)
        delta = valor_edw - valor_prod
        pct = (abs(delta) / abs(valor_prod) * 100) if valor_prod else (100 if valor_edw else 0)

        if pct <= self.tolerancia_pct:
            severity = Severity.OK
        elif pct <= self.tolerancia_pct * 5:
            severity = Severity.WARNING
        else:
            severity = Severity.CRITICAL

        return CheckResult(
            check_name=f"{self.name}:{self.columna}",
            severity=severity,
            descripcion=(
                f"Columna '{self.columna}': Producción={valor_prod:,.2f}, EDW={valor_edw:,.2f} "
                f"(delta={delta:,.2f}, {pct:.2f}%)."
            ),
            valor_produccion=valor_prod,
            valor_edw=valor_edw,
            delta=delta,
        )
