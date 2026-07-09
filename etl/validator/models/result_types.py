# models/result_types.py
from dataclasses import dataclass, field
from enum import Enum


class Severity(str, Enum):
    OK = "OK"
    WARNING = "WARNING"
    CRITICAL = "CRITICAL"


@dataclass
class CheckResult:
    """Resultado de un único check sobre una entidad."""
    check_name: str
    severity: Severity
    descripcion: str
    valor_produccion: object = None
    valor_edw: object = None
    delta: object = None
    detalle: str = ""


@dataclass
class ReconciliationResult:
    """Resultado consolidado de todos los checks de una entidad."""
    entidad: str
    tabla_edw: str
    evaluado: bool = True
    motivo_no_evaluado: str = ""
    checks: list[CheckResult] = field(default_factory=list)

    def severidad_maxima(self) -> Severity:
        if not self.checks:
            return Severity.OK
        orden = {Severity.OK: 0, Severity.WARNING: 1, Severity.CRITICAL: 2}
        return max((c.severity for c in self.checks), key=lambda s: orden[s])
