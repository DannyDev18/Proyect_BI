# ml/notebooks/eda_cross_selling.py
"""EDA del re-análisis del modelo de venta cruzada (Fase 2, plan
docs/features/plan_modulo_cross_selling.md §2.3.a).

No hay Jupyter disponible en este entorno de ejecución (agente headless sin kernel
interactivo), así que el EDA se implementa como script plano: cada sección imprime sus
hallazgos con un encabezado, pensado para correr una sola vez y pegar la salida en la
auditoría/reporte (no es un artefacto que se reejecute en producción). Ejecutar dentro
del contenedor `ml` (mismas versiones pineadas que el entrenamiento real, H-20):

    docker compose run --rm ml python notebooks/eda_cross_selling.py

Todo el SQL respeta los filtros de negocio obligatorios (CLAUDE.md regla 1 y 12):
estado_documento_sk <> -1, NOT es_devolucion, producto_sk <> -1, llave de negocio codart.
"""
import sys

import pandas as pd

sys.path.insert(0, ".")
from src.data.make_dataset import SalesTimeSerieExtractor  # noqa: E402

pd.set_option("display.width", 120)
pd.set_option("display.max_columns", 20)


def linea(titulo: str) -> None:
    print("\n" + "=" * 100)
    print(titulo)
    print("=" * 100)


def main() -> None:
    ext = SalesTimeSerieExtractor()
    engine = ext.engine

    # ------------------------------------------------------------------
    # 1) Dataset base: líneas de venta válidas con fecha, sucursal y categoría
    #    (clase de dim_producto), para poder cortar por año/ventana más adelante
    #    sin repetir el JOIN en cada sub-análisis.
    # ------------------------------------------------------------------
    sql_base = """
        SELECT
            fvd.num_factura AS transaction_id,
            p.codart AS product_code,
            p.clase AS categoria,
            df.fecha_completa AS fecha,
            fvd.sucursal_sk AS sucursal_sk,
            fvd.cliente_sk AS cliente_sk
        FROM edw.fact_ventas_detalle fvd
        JOIN edw.dim_producto p ON fvd.producto_sk = p.producto_sk
        JOIN edw.dim_fecha df ON fvd.fecha_sk = df.fecha_sk
        JOIN edw.dim_estado_documento ed ON fvd.estado_documento_sk = ed.estado_documento_sk
        WHERE ed.estado_documento_sk <> -1 AND NOT ed.es_devolucion AND fvd.producto_sk <> -1
    """
    df = pd.read_sql(sql_base, engine)
    df["fecha"] = pd.to_datetime(df["fecha"])
    df["anio"] = df["fecha"].dt.year
    linea("0) Volumen base")
    print(f"Líneas de venta válidas: {len(df):,}")
    print(f"Facturas únicas: {df['transaction_id'].nunique():,}")
    print(f"Productos (codart) únicos: {df['product_code'].nunique():,}")
    print(f"Rango de fechas: {df['fecha'].min().date()} .. {df['fecha'].max().date()}")

    # ------------------------------------------------------------------
    # 2) Distribución del tamaño de canasta (nº de productos distintos por factura)
    # ------------------------------------------------------------------
    linea("1) Distribución de tamaño de canasta (productos distintos por factura)")
    tam_canasta = df.groupby("transaction_id")["product_code"].nunique()
    print(tam_canasta.describe())
    bins = [0, 1, 2, 3, 5, 10, tam_canasta.max()]
    labels = ["1", "2", "3", "4-5", "6-10", "11+"]
    dist = pd.cut(tam_canasta, bins=bins, labels=labels, right=True).value_counts().sort_index()
    print("\nDistribución por bucket:")
    print(dist)
    print(f"\n% facturas con 2+ productos (universo útil para reglas): "
          f"{(tam_canasta >= 2).mean() * 100:.1f}%")

    # ------------------------------------------------------------------
    # 3) Concentración de ventas (Pareto) por producto y por categoría
    # ------------------------------------------------------------------
    linea("2) Concentración Pareto por producto (codart)")
    ventas_por_producto = df["product_code"].value_counts()
    total = ventas_por_producto.sum()
    acumulado = ventas_por_producto.cumsum() / total
    for pct in (0.05, 0.10, 0.20, 0.50):
        n = int(len(ventas_por_producto) * pct)
        cobertura = ventas_por_producto.iloc[:n].sum() / total
        print(f"Top {pct*100:.0f}% de productos ({n}) concentra {cobertura*100:.1f}% de las líneas de venta")

    linea("2b) Concentración Pareto por categoría (clase)")
    ventas_por_cat = df["categoria"].value_counts()
    print(f"Categorías (clase) distintas: {df['categoria'].nunique()}")
    print((ventas_por_cat / ventas_por_cat.sum() * 100).round(1).head(10))

    # ------------------------------------------------------------------
    # 4) Estabilidad temporal de co-ocurrencias: ¿los pares frecuentes de 2024
    #    siguen siéndolo en 2026?
    # ------------------------------------------------------------------
    linea("3) Estabilidad temporal de co-ocurrencias (2024 vs 2026)")

    def top_pares(sub_df: pd.DataFrame, min_support_count: int = 5, top_n: int = 30) -> set:
        basket = sub_df.groupby("transaction_id")["product_code"].apply(lambda s: sorted(set(s)))
        basket = basket[basket.map(len) > 1]
        cooc: dict[tuple, int] = {}
        for items in basket:
            for i in range(len(items)):
                for j in range(i + 1, len(items)):
                    par = (items[i], items[j])
                    cooc[par] = cooc.get(par, 0) + 1
        pares = {p: c for p, c in cooc.items() if c >= min_support_count}
        top = sorted(pares.items(), key=lambda kv: kv[1], reverse=True)[:top_n]
        return {p for p, _ in top}

    pares_2024 = top_pares(df[df["anio"] == 2024])
    pares_2026 = top_pares(df[df["anio"] == 2026])
    interseccion = pares_2024 & pares_2026
    print(f"Top-30 pares 2024: {len(pares_2024)} | Top-30 pares 2026: {len(pares_2026)}")
    print(f"Intersección: {len(interseccion)} pares ({len(interseccion) / max(len(pares_2024), 1) * 100:.0f}% "
          f"de los de 2024 siguen en el top de 2026) -> estabilidad temporal razonable, "
          f"justifica una ventana de entrenamiento de varios años en vez de solo el último trimestre.")

    # ------------------------------------------------------------------
    # 5) Cobertura de la línea base v0.1.0 (recalculada aquí para verificar
    #    contra la ya documentada en la auditoría 25: 87.9% en el último trimestre)
    # ------------------------------------------------------------------
    linea("4) Cobertura línea base (verificación contra auditoría 25)")
    ultimo_trimestre = df[df["fecha"] >= (df["fecha"].max() - pd.Timedelta(days=90))]
    canastas_trim = ultimo_trimestre.groupby("transaction_id")["product_code"].apply(lambda s: sorted(set(s)))
    canastas_trim = canastas_trim[canastas_trim.map(len) >= 2]
    print(f"Facturas del último trimestre con 2+ productos: {len(canastas_trim):,} "
          f"(auditoría 25 reportó 4.264)")

    # ------------------------------------------------------------------
    # 6) Afinidad por sucursal y por segmento (aproximación rápida): ¿el top-10
    #    de pares es el mismo en las 2 sucursales de mayor volumen?
    # ------------------------------------------------------------------
    linea("5) Afinidad por sucursal (top-2 sucursales por volumen)")
    top_sucursales = df["sucursal_sk"].value_counts().head(2).index.tolist()
    pares_por_suc = {s: top_pares(df[df["sucursal_sk"] == s], min_support_count=3, top_n=20) for s in top_sucursales}
    if len(top_sucursales) == 2:
        inter_suc = pares_por_suc[top_sucursales[0]] & pares_por_suc[top_sucursales[1]]
        print(f"Sucursales comparadas: {top_sucursales}")
        print(f"Intersección de sus top-20 pares: {len(inter_suc)} de 20 "
              f"-> {'afinidad mayormente GLOBAL' if len(inter_suc) >= 10 else 'afinidad con componente LOCAL relevante'}")

    print("\nEDA completo.")


if __name__ == "__main__":
    main()
