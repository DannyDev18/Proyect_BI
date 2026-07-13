# backend/tests/unit/test_pagination.py
"""Paginación genérica (docs/auditoria/24_prediccion_categoria_paginacion.md) --
función pura, sin dependencias de BD."""
import pytest
from pydantic import ValidationError

from app.schemas.pagination import PaginationParams, paginar


def test_paginar_primera_pagina():
    items = list(range(1, 26))  # 25 elementos
    pagina = paginar(items, PaginationParams(page=1, page_size=10))
    assert pagina.items == list(range(1, 11))
    assert pagina.total == 25
    assert pagina.total_pages == 3


def test_paginar_ultima_pagina_incompleta():
    items = list(range(1, 26))
    pagina = paginar(items, PaginationParams(page=3, page_size=10))
    assert pagina.items == [21, 22, 23, 24, 25]
    assert pagina.total_pages == 3


def test_paginar_pagina_fuera_de_rango_no_lanza_error():
    items = list(range(1, 11))
    pagina = paginar(items, PaginationParams(page=99, page_size=10))
    assert pagina.items == []
    assert pagina.total == 10
    assert pagina.total_pages == 1


def test_paginar_lista_vacia():
    pagina = paginar([], PaginationParams(page=1, page_size=10))
    assert pagina.items == []
    assert pagina.total == 0
    assert pagina.total_pages == 0


def test_page_size_excede_tope_falla_validacion():
    with pytest.raises(ValidationError):
        PaginationParams(page=1, page_size=1000)


def test_page_menor_a_uno_falla_validacion():
    with pytest.raises(ValidationError):
        PaginationParams(page=0, page_size=10)
