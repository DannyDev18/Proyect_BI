# ml/src/training/backtest_recommendation.py
"""Arnés de backtest temporal para el módulo de venta cruzada (Fase 3,
docs/features/plan_modulo_cross_selling.md §2.3.d).

Split SIEMPRE temporal (nunca aleatorio, evita fuga de datos): las canastas hasta la
fecha de corte T entrenan; las canastas del período (T, T+h] se usan para evaluar
"completado de canasta" -- se parte cada canasta de test en un contexto (lo que el
vendedor ya lleva) y un conjunto oculto (lo que realmente se llevó después), y se mide
si el motor de recomendación hubiera sugerido esos productos ocultos a partir del
contexto.

Reutilizable para reentrenamientos futuros: cualquier estrategia candidata solo debe
exponer una función `recomendar(contexto: list[str], top_n: int) -> list[str]` (lista
de codart ordenada por score descendente) para poder evaluarse con `evaluar_estrategia`.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Callable

import pandas as pd

logger = logging.getLogger("ML.BacktestRecommendation")

RecomendadorFn = Callable[[list[str], int], list[str]]


@dataclass
class MetricasBacktest:
    """Métricas de decisión de §2.3.d del plan, agregadas sobre todas las canastas de test."""

    n_canastas_test: int
    cobertura: float  # % de canastas con >=1 sugerencia no vacía
    precision_at: dict[int, float] = field(default_factory=dict)
    recall_at: dict[int, float] = field(default_factory=dict)
    hit_rate_5: float = 0.0
    impacto_ticket_medio: float = 0.0  # valor medio (precio) de los productos ocultos acertados

    def to_dict(self) -> dict:
        d = {
            "n_canastas_test": self.n_canastas_test,
            "cobertura": round(self.cobertura, 4),
            "hit_rate_5": round(self.hit_rate_5, 4),
            "impacto_ticket_medio": round(self.impacto_ticket_medio, 2),
        }
        for k, v in self.precision_at.items():
            d[f"precision_at_{k}"] = round(v, 4)
        for k, v in self.recall_at.items():
            d[f"recall_at_{k}"] = round(v, 4)
        return d


def split_temporal(df_basket: pd.DataFrame, horizonte_dias: int, fecha_col: str = "fecha") -> tuple[pd.DataFrame, pd.DataFrame]:
    """Split cronológico: entrena con canastas hasta T = max(fecha) - horizonte_dias;
    evalúa con canastas de (T, max(fecha)]. Nunca aleatorio (evita fuga temporal)."""
    fechas = pd.to_datetime(df_basket[fecha_col])
    fecha_corte = fechas.max() - pd.Timedelta(days=horizonte_dias)
    train = df_basket.loc[fechas <= fecha_corte]
    test = df_basket.loc[fechas > fecha_corte]
    logger.info(
        f"Split temporal: corte={fecha_corte.date()}, train={len(train)} líneas "
        f"({fechas.loc[fechas <= fecha_corte].min().date() if len(train) else '-'}..{fecha_corte.date()}), "
        f"test={len(test)} líneas ({fecha_corte.date()}..{fechas.max().date()})"
    )
    return train, test


def construir_canastas(df: pd.DataFrame, transaction_col: str = "transaction_id", product_col: str = "product_code") -> pd.Series:
    """Agrupa líneas de venta por transacción -> lista ordenada (determinista) de codart
    únicos. Solo canastas con 2+ productos son útiles para basket-completion."""
    canastas = df.groupby(transaction_col)[product_col].apply(lambda s: sorted(set(s)))
    return canastas[canastas.map(len) >= 2]


def construir_canastas_con_contexto(
    df: pd.DataFrame, transaction_col: str = "transaction_id", product_col: str = "product_code",
) -> pd.DataFrame:
    """Igual que `construir_canastas`, pero conserva `cliente_sk`/`fecha` por
    transacción -- necesario para el backtest de `cross_sell_ranker` (Fase 2,
    docs/features/plan_refactor_venta_cruzada_ia.md §2.4): el ranker necesita saber
    QUIÉN es el cliente y CUÁNDO (para calcular sus features al corte T=fecha de esa
    transacción) además de qué llevaba en la canasta."""
    agg = df.groupby(transaction_col).agg(
        items=(product_col, lambda s: sorted(set(s))),
        cliente_sk=("cliente_sk", "first"),
        fecha=("fecha", "first"),
    )
    return agg[agg["items"].map(len) >= 2]


def _contexto_y_oculto(items: list[str]) -> tuple[list[str], set[str]]:
    """Parte una canasta en contexto (primera mitad, redondeando arriba) y conjunto
    oculto (el resto) -- determinista (orden alfabético de codart, ya viene de
    `construir_canastas`), no aleatorio, para que el backtest sea reproducible."""
    corte = max(1, -(-len(items) // 2))  # ceil(len/2)
    return items[:corte], set(items[corte:])


def evaluar_estrategia(
    recomendar: RecomendadorFn,
    canastas_test: pd.Series,
    precios: dict[str, float] | None = None,
    k_values: tuple[int, ...] = (3, 5),
) -> MetricasBacktest:
    """Evalúa una estrategia de recomendación contra las canastas de test.

    Para cada canasta: contexto = primera mitad (lo que el vendedor ya lleva),
    oculto = el resto (lo que realmente se llevó). Se piden top-max(k_values)
    sugerencias a partir del contexto (excluyendo lo que ya está en el contexto,
    responsabilidad de `recomendar`) y se comparan contra `oculto`.
    """
    k_max = max(k_values)
    precios = precios or {}

    n = len(canastas_test)
    con_sugerencia = 0
    aciertos_por_k = {k: 0 for k in k_values}  # suma de |topk ∩ oculto|
    recall_por_k = {k: [] for k in k_values}
    hits_5 = 0
    valores_acierto: list[float] = []

    for items in canastas_test:
        contexto, oculto = _contexto_y_oculto(items)
        sugerencias = recomendar(contexto, k_max) or []
        if sugerencias:
            con_sugerencia += 1
        for k in k_values:
            topk = sugerencias[:k]
            interseccion = set(topk) & oculto
            aciertos_por_k[k] += len(interseccion)
            recall_por_k[k].append(len(interseccion) / len(oculto) if oculto else 0.0)
        top5 = set(sugerencias[:5])
        inter5 = top5 & oculto
        if inter5:
            hits_5 += 1
            valores_acierto.extend(precios.get(cod, 0.0) for cod in inter5)

    precision_at = {k: (aciertos_por_k[k] / (n * k) if n else 0.0) for k in k_values}
    recall_at = {k: (sum(recall_por_k[k]) / n if n else 0.0) for k in k_values}

    return MetricasBacktest(
        n_canastas_test=n,
        cobertura=(con_sugerencia / n) if n else 0.0,
        precision_at=precision_at,
        recall_at=recall_at,
        hit_rate_5=(hits_5 / n) if n else 0.0,
        impacto_ticket_medio=(sum(valores_acierto) / len(valores_acierto)) if valores_acierto else 0.0,
    )


def evaluar_estrategia_reranked(
    generar_candidatos: RecomendadorFn,
    reranker: Callable[[list[str], int, "pd.Timestamp"], list[str]],
    canastas_ctx: pd.DataFrame,
    precios: dict[str, float] | None = None,
    k_values: tuple[int, ...] = (3, 5),
    pool_candidatos: int = 50,
) -> MetricasBacktest:
    """Mismo protocolo y las mismas métricas que `evaluar_estrategia` (Precision@K,
    Recall@K, Hit-Rate@5, cobertura -- auditoría 25), pero en dos etapas (Fase 2,
    docs/features/plan_refactor_venta_cruzada_ia.md §2.4, arquitectura de dos etapas del
    plan §3): `generar_candidatos` propone un pool amplio (item-item, igual que
    producción) y `reranker` lo reordena usando el modelo `cross_sell_ranker` --
    necesita `cliente_sk`/`fecha` de la canasta (que `evaluar_estrategia` no requiere)
    para calcular las features del cliente al corte T=fecha de esa transacción, así que
    usa `canastas_ctx` (`construir_canastas_con_contexto`), no `canastas` planas."""
    k_max = max(k_values)
    precios = precios or {}

    n = len(canastas_ctx)
    con_sugerencia = 0
    aciertos_por_k = {k: 0 for k in k_values}
    recall_por_k = {k: [] for k in k_values}
    hits_5 = 0
    valores_acierto: list[float] = []

    for _, fila in canastas_ctx.iterrows():
        items, cliente_sk, fecha = fila["items"], fila["cliente_sk"], fila["fecha"]
        contexto, oculto = _contexto_y_oculto(items)
        candidatos = generar_candidatos(contexto, pool_candidatos) or []
        sugerencias = (reranker(candidatos, cliente_sk, fecha) if candidatos else [])[:k_max]
        if sugerencias:
            con_sugerencia += 1
        for k in k_values:
            topk = sugerencias[:k]
            interseccion = set(topk) & oculto
            aciertos_por_k[k] += len(interseccion)
            recall_por_k[k].append(len(interseccion) / len(oculto) if oculto else 0.0)
        top5 = set(sugerencias[:5])
        inter5 = top5 & oculto
        if inter5:
            hits_5 += 1
            valores_acierto.extend(precios.get(cod, 0.0) for cod in inter5)

    precision_at = {k: (aciertos_por_k[k] / (n * k) if n else 0.0) for k in k_values}
    recall_at = {k: (sum(recall_por_k[k]) / n if n else 0.0) for k in k_values}

    return MetricasBacktest(
        n_canastas_test=n,
        cobertura=(con_sugerencia / n) if n else 0.0,
        precision_at=precision_at,
        recall_at=recall_at,
        hit_rate_5=(hits_5 / n) if n else 0.0,
        impacto_ticket_medio=(sum(valores_acierto) / len(valores_acierto)) if valores_acierto else 0.0,
    )
