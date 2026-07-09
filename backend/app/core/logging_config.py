# backend/app/core/logging_config.py
"""Configuración de logging centralizada. Antes cada módulo confiaba en el logging
default de Python/Uvicorn sin ningún `basicConfig`/`dictConfig` explícito."""
import logging
import sys


def configure_logging(level: str = "INFO") -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)],
        force=True,
    )
