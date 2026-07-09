# backend/app/repositories/base.py
"""Marcador común de la capa repository.

No se define un `Protocol` genérico de CRUD (`get`, `create`, `update`, `delete`) porque
cada repositorio de este proyecto tiene una forma de acceso a datos distinta (ORM para
`public.*`, SQL crudo de solo lectura para `edw.*`) -- forzar una interfaz común
prematuramente sería abstracción sin valor real (KISS). Lo que sí es un contrato real y
compartido: todo repositorio recibe una `Session` de SQLAlchemy por constructor/parámetro
(nunca crea su propia conexión), lo que los hace 100% mockeables en tests de servicio
reemplazando el repositorio completo por un `unittest.mock.MagicMock`.
"""
from sqlalchemy.orm import Session


class BaseRepository:
    """Repositorios ORM (schema `public.*`) heredan de esto para compartir la sesión."""

    def __init__(self, db: Session):
        self.db = db
