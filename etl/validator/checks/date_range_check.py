# checks/date_range_check.py
import pandas as pd

from validator.checks.base_check import Check
from validator.models.result_types import CheckResult, Severity


class DateRangeCheck(Check):
    """Compara la cobertura de fechas (mínima/máxima) entre Producción y EDW. Un desfase indica
    que el ETL no cargó el rango completo o cargó fechas fuera de lo esperado."""

    name = "date_range_check"

    def run(self, prod_row: pd.Series, edw_row: pd.Series) -> CheckResult:
        min_p, max_p = prod_row.get("fecha_min"), prod_row.get("fecha_max")
        min_e, max_e = edw_row.get("fecha_min"), edw_row.get("fecha_max")

        if pd.isna(min_p) and pd.isna(min_e):
            return CheckResult(
                check_name=self.name, severity=Severity.OK,
                descripcion="Sin filas en el rango evaluado en ninguno de los dos lados.",
            )

        desfase_min = (pd.isna(min_e)) or (pd.notna(min_p) and pd.Timestamp(min_e) > pd.Timestamp(min_p))
        desfase_max = (pd.isna(max_e)) or (pd.notna(max_p) and pd.Timestamp(max_e) < pd.Timestamp(max_p))

        if desfase_min or desfase_max:
            severity = Severity.CRITICAL
        else:
            severity = Severity.OK

        return CheckResult(
            check_name=self.name,
            severity=severity,
            descripcion=(
                f"Producción: [{min_p} .. {max_p}] | EDW: [{min_e} .. {max_e}]."
            ),
            valor_produccion=f"{min_p}..{max_p}",
            valor_edw=f"{min_e}..{max_e}",
        )
