# backend/app/schemas/pagination.py
"""Paginación genérica reutilizable por cualquier endpoint que devuelva listas
(docs/auditoria/24_prediccion_categoria_paginacion.md). `paginar()` opera en memoria
sobre una lista ya calculada/ordenada por el servicio -- reduce el payload de red al
cliente, no el cómputo/IO previo (limitación declarada, ver auditoría 24 H24-2).

Para endpoints cuyo orden se resuelve en SQL, el mismo contrato `Page[T]` puede
poblarse desde un repositorio con LIMIT/OFFSET + COUNT(*); no hay ningún caso así
en el módulo Bodega todavía, por eso solo se implementa el nivel en memoria aquí."""
import math
from typing import Annotated, Generic, Sequence, TypeVar

from fastapi import Query
from pydantic import BaseModel, Field

T = TypeVar("T")

PAGE_SIZE_MAXIMO = 200


class PaginationParams(BaseModel):
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=25, ge=1, le=PAGE_SIZE_MAXIMO)


def pagination_params(
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=PAGE_SIZE_MAXIMO)] = 25,
) -> PaginationParams:
    """Dependencia FastAPI: `Depends(pagination_params)` en cualquier router.
    Los límites (ge/le) los valida FastAPI vía `Query(...)` -- así un `page_size`
    fuera de rango responde 422 (`RequestValidationError`) en vez de un 500 sin
    manejar (construir `PaginationParams(...)` directamente con un valor inválido
    lanza `pydantic.ValidationError`, que no es lo que traducen los handlers
    globales de `main.py`)."""
    return PaginationParams(page=page, page_size=page_size)


class Page(BaseModel, Generic[T]):
    items: list[T]
    total: int
    page: int
    page_size: int
    total_pages: int


def paginar(items: Sequence[T], params: PaginationParams) -> Page[T]:
    """Recorta `items` (ya ordenados por el servicio) a la página pedida.
    `page` fuera de rango devuelve una página vacía con `total` correcto, sin error --
    el paginador del frontend puede mostrar el total sin que el usuario reciba un 4xx
    por navegar más allá del final."""
    total = len(items)
    total_pages = math.ceil(total / params.page_size) if total else 0
    inicio = (params.page - 1) * params.page_size
    fin = inicio + params.page_size
    return Page(
        items=list(items[inicio:fin]),
        total=total,
        page=params.page,
        page_size=params.page_size,
        total_pages=total_pages,
    )
