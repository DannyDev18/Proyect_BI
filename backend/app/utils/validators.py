# backend/app/utils/validators.py
"""Helpers de validación reutilizables. `sanitize_date_str` estaba duplicada (misma
lógica de `re.match`) en 2 métodos de `analytics_service.py` antes del refactor."""
import re

_DATE_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def sanitize_date_str(value: str | None) -> str | None:
    """Devuelve `value` si tiene forma YYYY-MM-DD, o None si no (evita pasar entradas
    parciales/inválidas a un filtro SQL de fecha)."""
    if value and not _DATE_PATTERN.match(value):
        return None
    return value
