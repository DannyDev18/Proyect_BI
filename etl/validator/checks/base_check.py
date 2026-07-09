# checks/base_check.py
from abc import ABC, abstractmethod
import pandas as pd

from validator.models.result_types import CheckResult


class Check(ABC):
    """Contrato común: recibe los resultados agregados ya obtenidos de Producción y del EDW
    (DataFrames de una sola fila, producto de las queries de agregación) y devuelve un
    CheckResult. Ningún Check ejecuta SQL por su cuenta ni abre conexiones."""

    name: str = "check"

    @abstractmethod
    def run(self, prod_row: pd.Series, edw_row: pd.Series) -> CheckResult:
        raise NotImplementedError
