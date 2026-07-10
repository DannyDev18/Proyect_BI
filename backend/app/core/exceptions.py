# backend/app/core/exceptions.py
"""Excepciones de dominio. Los servicios lanzan estas, nunca `HTTPException` de FastAPI
(eso acopla la capa de negocio a HTTP). `main.py` las traduce a respuestas HTTP via
`@app.exception_handler`."""


class DomainError(Exception):
    """Excepción base de dominio. Cualquier subclase no manejada explícitamente
    responde 400 vía el handler catch-all de DomainError."""


class NotFoundError(DomainError):
    """El recurso solicitado no existe (usuario, rol, meta, etc.)."""


class ConflictError(DomainError):
    """La operación viola una restricción de unicidad/estado (ej. email duplicado)."""


class ValidationError(DomainError):
    """Regla de negocio ad-hoc violada (más allá de la validación de schema de Pydantic)."""


class PermissionDeniedError(DomainError):
    """El usuario autenticado no tiene privilegios para la acción solicitada."""


class ModelNotLoadedError(DomainError):
    """Se solicitó un modelo ML que no está cargado en el ModelLoader."""


class ExternalDataError(DomainError):
    """Fallo real de acceso a datos externos (EDW, filesystem de modelos, subprocess de
    entrenamiento) que no debe tragarse en silencio ni devolver un valor por defecto mudo."""


class ModelContractError(DomainError):
    """Una inferencia violó el contrato ML declarado (features faltantes o predicción
    fuera del rango plausible) para un contrato en estado 'active'. Ver
    app/ml/contract_validation.py -- responde 400 vía el handler catch-all de DomainError."""
