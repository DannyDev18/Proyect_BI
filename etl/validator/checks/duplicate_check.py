# checks/duplicate_check.py
import pandas as pd

from validator.checks.base_check import Check
from validator.models.result_types import CheckResult, Severity


class DuplicateCheck(Check):
    """Cuenta grupos de filas exactamente duplicadas en el EDW (misma llave de negocio +
    mismos valores). No compara contra Producción: un duplicado en el EDW es, por definición,
    un artefacto de carga (reproceso), no algo que pueda existir "también" en el origen."""

    name = "duplicate_check"

    def run(self, dup_row: pd.Series) -> CheckResult:
        grupos = int(dup_row.get("grupos_duplicados") or 0)
        severity = Severity.OK if grupos == 0 else Severity.CRITICAL
        return CheckResult(
            check_name=self.name,
            severity=severity,
            descripcion=f"{grupos} grupo(s) de filas duplicadas detectados en el EDW.",
            valor_edw=grupos,
        )
