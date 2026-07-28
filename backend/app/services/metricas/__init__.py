# backend/app/services/metricas/__init__.py
"""Capa semántica: punto único de definición de las métricas de negocio.

Motivación (G-02 de `docs/features/plan_madurez_bi_toma_decisiones.md`): "venta neta" es
*la* métrica del negocio -- base de metas, comisiones, cumplimiento y KPIs de Gerencia -- y
su cálculo aparecía disperso en repositorios y servicios sin nada que garantizara que todos
aplicaran el mismo tratamiento de devoluciones, estado de documento y líneas negativas. En
BI eso tiene nombre propio: *múltiples versiones de la verdad*, y el síntoma aparece tarde
(un vendedor reclama que su comisión no cuadra con el tablero, y no hay forma de decir cuál
de los dos está bien).

Este paquete NO reemplaza los repositorios: expone los fragmentos SQL canónicos y las
constantes que los repositorios ensamblan, de modo que la *definición* viva en un solo
archivo aunque las consultas sigan teniendo formas distintas (analytics filtra por 6
dimensiones; metas/comisiones agrupa por vendedor y período).

El diccionario de negocio correspondiente está en `docs/diccionario_indicadores.md`.
"""
from app.services.metricas.venta_neta import (
    FILTRO_ESTADO_VALIDO,
    SQL_DEVOLUCIONES_MONTO,
    SQL_VENTA_BRUTA,
    definicion_venta_neta,
)

__all__ = [
    "FILTRO_ESTADO_VALIDO",
    "SQL_DEVOLUCIONES_MONTO",
    "SQL_VENTA_BRUTA",
    "definicion_venta_neta",
]
