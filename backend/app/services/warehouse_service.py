# backend/app/services/warehouse_service.py
"""Lógica de negocio del módulo Bodega (docs/features/modulo_bodega.md, auditoría 23).

Reglas RN-B1..B6 (docs/auditoria/23_modulo_bodega.md):
- RN-B1 punto de reorden efectivo (configurado > 0, si no fórmula §6.3)
- RN-B2 estados Crítico/Cerca/Seguro/Exceso
- RN-B3 transferencia antes de compra (excedente >60d origen, déficit <15d destino)
- RN-B4 cantidad a comprar (horizonte 30/45 días)
- RN-B5 rotación = costo de ventas / inventario promedio (semáforo 2/4)

El forecast de salidas por producto reutiliza el modelo `demand_rf` existente vía
`walk_forward_forecast` (mismo patrón que ventas); los listados masivos usan proyección
estadística (promedio de 30 días) declarada en el payload — H23-6."""
import datetime
import logging
import time
from typing import Any

import pandas as pd

from app.core.config import settings
from app.core.exceptions import ValidationError
from app.ml import inference
from app.ml.forecasting import walk_forward_forecast
from app.ml.model_loader import ModelLoader
from app.repositories.dataset_repository import DatasetRepository
from app.repositories.warehouse_repository import TIPOS_MOVIMIENTO, WarehouseRepository
from app.schemas.pagination import Page, PaginationParams, paginar

logger = logging.getLogger("Backend.WarehouseService")

ESTADO_CRITICO = "Crítico"
ESTADO_CERCA = "Cerca"
ESTADO_SEGURO = "Seguro"
ESTADO_EXCESO = "Exceso"


class WarehouseService:
    def __init__(
        self,
        warehouse_repo: WarehouseRepository,
        dataset_repo: DatasetRepository,
        model_loader: ModelLoader,
    ):
        self.repo = warehouse_repo
        self.dataset_repo = dataset_repo
        self.model_loader = model_loader

    # ── Fórmulas (RN-B1/B2, §6.3) ────────────────────────────────────────────
    @staticmethod
    def _salida_diaria(salidas_periodo: float, dias: int = 30) -> float:
        return (salidas_periodo / dias) if dias > 0 else 0.0

    @staticmethod
    def _punto_reorden_efectivo(configurado: float, salida_diaria: float) -> float:
        if configurado and configurado > 0:
            return round(float(configurado), 2)
        return round(
            salida_diaria * (settings.BODEGA_LEAD_TIME_DIAS + settings.BODEGA_STOCK_SEGURIDAD_DIAS), 2,
        )

    @staticmethod
    def _dias_inventario(stock: float, salida_diaria: float) -> float | None:
        """None = sin salidas en el período (inventario "infinito", no divisible)."""
        if salida_diaria <= 0:
            return None
        return round(stock / salida_diaria, 1)

    @classmethod
    def _estado_stock(cls, stock: float, reorden: float, dias_inv: float | None) -> str:
        if dias_inv is not None and dias_inv > settings.BODEGA_DIAS_EXCESO:
            return ESTADO_EXCESO
        if reorden <= 0:
            return ESTADO_SEGURO
        if stock < reorden:
            return ESTADO_CRITICO
        if stock <= reorden * 1.5:
            return ESTADO_CERCA
        return ESTADO_SEGURO

    @staticmethod
    def _tendencia_pct(actual: float, previo: float) -> float | None:
        if previo <= 0:
            return None
        return round((actual - previo) / previo * 100, 1)

    @staticmethod
    def _defaults_rango(fecha_desde: str | None, fecha_hasta: str | None) -> tuple[str, str, str, str]:
        """Rango por defecto = últimos 30 días; período previo = los 30 anteriores.
        Devuelve (desde, hasta, desde_prev, hasta_prev) como ISO."""
        hoy = datetime.date.today()
        hasta = datetime.date.fromisoformat(fecha_hasta) if fecha_hasta else hoy
        desde = datetime.date.fromisoformat(fecha_desde) if fecha_desde else hasta - datetime.timedelta(days=30)
        if desde > hasta:
            raise ValidationError("El rango de fechas es inválido: fecha_desde > fecha_hasta.")
        delta = hasta - desde
        hasta_prev = desde - datetime.timedelta(days=1)
        desde_prev = hasta_prev - delta
        return desde.isoformat(), hasta.isoformat(), desde_prev.isoformat(), hasta_prev.isoformat()

    def _enriquecer_producto(self, row: dict[str, Any], dias_periodo: int = 30) -> dict[str, Any]:
        """Deriva las métricas por producto usadas en varios endpoints."""
        salida_diaria = self._salida_diaria(row["salidas_periodo"], dias_periodo)
        reorden = self._punto_reorden_efectivo(row.get("punto_reorden_config", 0), salida_diaria)
        dias_inv = self._dias_inventario(row["stock_actual"], salida_diaria)
        estado = self._estado_stock(row["stock_actual"], reorden, dias_inv)
        dias_hasta_reorden = None
        if salida_diaria > 0 and row["stock_actual"] > reorden:
            dias_hasta_reorden = round((row["stock_actual"] - reorden) / salida_diaria, 1)
        elif salida_diaria > 0:
            dias_hasta_reorden = 0.0
        return {
            **row,
            "salida_diaria": round(salida_diaria, 2),
            "punto_reorden": reorden,
            "dias_inventario": dias_inv,
            "estado": estado,
            "dias_hasta_reorden": dias_hasta_reorden,
        }

    # ── Filtros globales (§1.1) ──────────────────────────────────────────────
    def get_filtros(self, analytics_repo_catalogos: dict[str, list[str]]) -> dict[str, Any]:
        return {
            **analytics_repo_catalogos,
            "proveedores": self.repo.get_proveedores(),
            "tipos_movimiento": TIPOS_MOVIMIENTO,
        }

    # ── KPIs (§1.2) ──────────────────────────────────────────────────────────
    def get_kpis(
        self, sucursal: str | None = None, almacen: str | None = None,
        categoria: str | None = None, proveedor: str | None = None,
        tipo_movimiento: str | None = None, fecha_desde: str | None = None,
        fecha_hasta: str | None = None,
    ) -> dict[str, Any]:
        desde, hasta, _, _ = self._defaults_rango(fecha_desde, fecha_hasta)
        filtros = dict(sucursal=sucursal, almacen=almacen, categoria=categoria,
                       proveedor=proveedor, tipo_movimiento=tipo_movimiento)

        productos = [self._enriquecer_producto(r) for r in self.repo.get_inventario_productos(**filtros)]
        periodo = self.repo.get_kpis_periodo(desde, hasta, **filtros)
        actual = self.repo.get_snapshot_total_a_fecha(None, **filtros)

        # Tendencia vs mes anterior (H23-2: puede no existir snapshot previo → None).
        primer_dia_mes = datetime.date.today().replace(day=1)
        fin_mes_anterior = (primer_dia_mes - datetime.timedelta(days=1)).isoformat()
        previo = self.repo.get_snapshot_total_a_fecha(
            fin_mes_anterior, sucursal=sucursal, almacen=almacen, categoria=categoria,
            proveedor=proveedor, tipo_movimiento=tipo_movimiento,
        )

        # H24-x: `actual["total_skus"]` es el tamaño del catálogo completo (SAP expone TODO
        # artículo por almacén, con existencia 0 donde nunca hubo stock -- ver
        # WarehouseRepository.get_skus_surtido) y por eso NO varía al filtrar por almacén.
        # Se reemplaza por el surtido real (codart con movimiento histórico en el almacén).
        total_skus = self.repo.get_skus_surtido(**filtros)
        valor_total = actual["valor_total"] if actual else sum(p["valor_inventario"] for p in productos)
        skus_activos = actual["skus_activos"] if actual else sum(1 for p in productos if p["stock_actual"] > 0)
        total_skus = max(total_skus, skus_activos)  # salvaguarda: nunca por debajo de lo activo
        # Cantidad física total (unidades) del almacén filtrado -- mismo valor que devuelve
        # dbo.fn_exiact_alm en SAP (SUM(existe)), congelado a la fecha del último snapshot.
        cantidad_total = actual["cantidad_total"] if actual else sum(p["stock_actual"] for p in productos)

        # Rotación (RN-B5): mensual sobre el rango, anualizada para el semáforo.
        inv_promedio = periodo["inventario_promedio"] or (valor_total if valor_total > 0 else None)
        dias_rango = max((datetime.date.fromisoformat(hasta) - datetime.date.fromisoformat(desde)).days, 1)
        rotacion_periodo = (periodo["costo_ventas"] / inv_promedio) if inv_promedio else None
        rotacion_anualizada = (rotacion_periodo * 365 / dias_rango) if rotacion_periodo is not None else None
        if rotacion_anualizada is None:
            semaforo = "sin_datos"
        elif rotacion_anualizada > settings.BODEGA_ROTACION_BUENA:
            semaforo = "verde"
        elif rotacion_anualizada >= settings.BODEGA_ROTACION_REGULAR:
            semaforo = "amarillo"
        else:
            semaforo = "rojo"

        # Días de inventario global: stock valorizado / costo de venta diario del rango.
        costo_diario = periodo["costo_ventas"] / dias_rango if dias_rango else 0
        dias_disponibles = round(valor_total / costo_diario, 1) if costo_diario > 0 else None

        criticos = [p for p in productos if p["estado"] == ESTADO_CRITICO]
        pct_criticos = round(len(criticos) / len(productos) * 100, 1) if productos else 0.0
        if pct_criticos > 10:
            color_stock_bajo = "rojo"
        elif pct_criticos >= 5:
            color_stock_bajo = "amarillo"
        else:
            color_stock_bajo = "verde"

        tasa_stockout = periodo["tasa_stockout_pct"]

        return {
            "total_articulos": {
                # H24-x: `total_skus` es el tamaño del catálogo completo (vi_mv_existencias en
                # SAP expone TODO artículo para TODO almacén, con existencia 0 donde nunca se
                # ha stockeado) -- por diseño NO varía al filtrar por almacén/sucursal. El valor
                # que sí refleja "artículos en inventario" en el almacén filtrado es
                # `skus_activos` (stock_actual > 0); es el que debe mostrarse como titular.
                "total_skus": total_skus,
                "skus_activos": skus_activos,
                "skus_stock_cero": total_skus - skus_activos,
                "cantidad_total": round(cantidad_total, 2),
                "tendencia_pct": self._tendencia_pct(skus_activos, previo["skus_activos"]) if previo else None,
            },
            "rotacion": {
                "rotacion_periodo": round(rotacion_periodo, 2) if rotacion_periodo is not None else None,
                "rotacion_anualizada": round(rotacion_anualizada, 2) if rotacion_anualizada is not None else None,
                "semaforo": semaforo,
            },
            "dias_inventario": {
                "dias": dias_disponibles,
                "alerta_desabastecimiento": bool(
                    dias_disponibles is not None and dias_disponibles < settings.BODEGA_DIAS_DEFICIT
                ),
            },
            "stock_bajo": {
                "productos_bajo_reorden": len(criticos),
                "pct_del_total": pct_criticos,
                "color": color_stock_bajo,
            },
            "valor_inventario": {
                "valor_total": round(valor_total, 2),
                "tendencia_pct": self._tendencia_pct(valor_total, previo["valor_total"]) if previo else None,
                "top_categorias": self.repo.get_valor_por_categoria(
                    sucursal=sucursal, almacen=almacen, proveedor=proveedor, tipo_movimiento=tipo_movimiento,
                ),
            },
            "tasa_stockout": {
                "pct": tasa_stockout,
                "meta_pct": 3.0,
                "alerta": bool(tasa_stockout is not None and tasa_stockout > 5.0),
            },
        }

    # ── Gráfico 1 (§1.3): histórico + predicción de salidas ─────────────────
    def get_salidas_forecast(
        self, producto_cod: str | None = None, dias_horizonte: int = 30,
        sucursal: str | None = None, almacen: str | None = None,
        categoria: str | None = None, proveedor: str | None = None,
        fecha_desde: str | None = None, fecha_hasta: str | None = None,
        top_n: int = 10,
    ) -> dict[str, Any]:
        desde, hasta, _, _ = self._defaults_rango(fecha_desde, fecha_hasta)
        historial = self.repo.get_salidas_serie_diaria(
            producto_cod, desde, hasta, sucursal=sucursal, almacen=almacen,
            categoria=categoria, proveedor=proveedor,
            top_n=None if producto_cod else top_n,
        )

        stock_actual = None
        punto_reorden = None
        metodo = "estadistico"
        prediccion: list[dict[str, Any]] = []

        serie_hist = pd.Series(
            {pd.Timestamp(h["fecha"]): h["unidades"] for h in historial}, dtype=float,
        ).sort_index()

        if producto_cod:
            fila = next(
                (r for r in self.repo.get_inventario_productos(
                    sucursal=sucursal, almacen=almacen, categoria=categoria,
                    proveedor=proveedor, tipo_movimiento=None,
                ) if r["codart"] == producto_cod),
                None,
            )
            if fila:
                enriquecido = self._enriquecer_producto(fila)
                stock_actual = enriquecido["stock_actual"]
                punto_reorden = enriquecido["punto_reorden"]
            prediccion, metodo = self._forecast_ml_producto(producto_cod, dias_horizonte, serie_hist)
        if not prediccion:
            prediccion = self._forecast_estadistico(serie_hist, dias_horizonte)
            metodo = "estadistico"

        return {
            "producto_cod": producto_cod,
            "metodo": metodo,
            "stock_actual": stock_actual,
            "punto_reorden": punto_reorden,
            "historial": historial,
            "prediccion": prediccion,
        }

    def _forecast_ml_producto(
        self, producto_cod: str, dias: int, serie_salidas: pd.Series,
    ) -> tuple[list[dict[str, Any]], str]:
        """Walk-forward con el modelo `demand_rf` existente sobre la serie de ventas del
        producto (mismo insumo que get_demand_forecast). Banda de confianza con el MAE
        real del sidecar demand.meta.json. Degrada con gracia a [] (el caller usa el
        método estadístico) — patrón obligatorio de prediction_service."""
        try:
            df_hist = self.dataset_repo.get_product_sales_history(producto_cod)
            if df_hist.empty:
                return [], "estadistico"
            df_hist["ds"] = pd.to_datetime(df_hist["ds"])
            df_hist = df_hist.sort_values("ds").set_index("ds").resample("D").sum().fillna(0)

            preds = walk_forward_forecast(
                self.model_loader, df_hist, "y_quantity", dias, inference.predict_demand,
            )
            meta = self.model_loader.get_meta("demand_rf")
            mae = meta.get("metrics", {}).get("MAE")
            resultado = []
            for fecha, valor in preds:
                # La banda del requerimiento es "80%"; sin distribución del error se usa
                # el MAE diario real (misma convención declarada del módulo de ventas).
                margen = mae if mae is not None else valor * 0.2
                resultado.append({
                    "fecha": fecha.strftime("%Y-%m-%d"),
                    "unidades": round(valor, 2),
                    "banda_superior": round(valor + margen, 2),
                    "banda_inferior": round(max(0.0, valor - margen), 2),
                })
            return resultado, "ml_demand_rf"
        except Exception as e:
            logger.error(f"Fallo forecast ML de salidas para producto_cod={producto_cod}: {e}")
            return [], "estadistico"

    @staticmethod
    def _forecast_estadistico(serie: pd.Series, dias: int) -> list[dict[str, Any]]:
        """Proyección declarada como estadística (H23-6): promedio móvil de 7 días con
        desviación estándar como banda."""
        if serie.empty:
            return []
        serie = serie.resample("D").sum().fillna(0) if isinstance(serie.index, pd.DatetimeIndex) else serie
        prom = float(serie.tail(7).mean())
        desv = float(serie.tail(30).std() or 0.0)
        ultimo = serie.index[-1]
        out = []
        for i in range(1, dias + 1):
            fecha = ultimo + pd.Timedelta(days=i)
            out.append({
                "fecha": fecha.strftime("%Y-%m-%d"),
                "unidades": round(prom, 2),
                "banda_superior": round(prom + desv, 2),
                "banda_inferior": round(max(0.0, prom - desv), 2),
            })
        return out

    # ── Predicción de compras del próximo mes por categoría (docs/auditoria/24) ──
    # Cache en memoria por proceso (clase, no instancia -- WarehouseService se
    # reconstruye en cada request vía DI): evita 20 walk-forward por request mientras
    # el EDW no cambie (carga por lotes, no intra-hora). Si el despliegue usa varios
    # workers el cache no se comparte entre procesos (limitación declarada, auditoría 24).
    _prediccion_cache: dict[tuple, tuple[float, dict[str, Any]]] = {}

    def _prediccion_cache_get(self, key: tuple) -> dict[str, Any] | None:
        entrada = self._prediccion_cache.get(key)
        if not entrada:
            return None
        expira, valor = entrada
        if time.monotonic() > expira:
            del self._prediccion_cache[key]
            return None
        return valor

    def _prediccion_cache_set(self, key: tuple, valor: dict[str, Any]) -> None:
        ttl_seg = settings.BODEGA_FORECAST_CACHE_TTL_MIN * 60
        self._prediccion_cache[key] = (time.monotonic() + ttl_seg, valor)

    @staticmethod
    def _rango_mes_siguiente() -> tuple[datetime.date, datetime.date, int]:
        """Primer y último día del mes calendario siguiente + días de walk-forward
        necesarios desde mañana hasta ese último día (RN-B7)."""
        hoy = datetime.date.today()
        primer_dia = (hoy.replace(day=1) + datetime.timedelta(days=32)).replace(day=1)
        ultimo_dia = (primer_dia.replace(day=28) + datetime.timedelta(days=4)).replace(day=1) - datetime.timedelta(days=1)
        dias_horizonte = (ultimo_dia - hoy).days
        return primer_dia, ultimo_dia, dias_horizonte

    def _prediccion_articulo(
        self, codart: str, dias_horizonte: int, primer_dia: datetime.date, ultimo_dia: datetime.date,
        desde_hist: str, hasta_hist: str, sucursal: str | None, almacen: str | None, proveedor: str | None,
    ) -> tuple[list[dict[str, Any]], str]:
        """Predicción diaria de un artículo recortada al mes objetivo. Reutiliza
        `_forecast_ml_producto` (demand_rf); si degrada, cae al mismo camino
        estadístico que `get_salidas_forecast` (H23-6). El fallback también se
        protege con try/except: un artículo cuyo repositorio falle (p.ej. conexión
        agotada tras N walk-forwards seguidos en el mismo request) no debe tumbar
        toda la predicción de la categoría -- degrada a "sin datos" para ese
        artículo únicamente (mismo principio que `_forecast_ml_producto`)."""
        resultado, metodo = self._forecast_ml_producto(codart, dias_horizonte, pd.Series(dtype=float))
        if not resultado:
            try:
                historial = self.repo.get_salidas_serie_diaria(
                    codart, desde_hist, hasta_hist, sucursal=sucursal, almacen=almacen, proveedor=proveedor,
                )
                serie_hist = pd.Series(
                    {pd.Timestamp(h["fecha"]): h["unidades"] for h in historial}, dtype=float,
                ).sort_index()
                resultado = self._forecast_estadistico(serie_hist, dias_horizonte)
            except Exception as e:
                logger.error(f"Fallo fallback estadístico de predicción mensual para codart={codart}: {e}")
                resultado = []
            metodo = "estadistico"
        return [p for p in resultado if primer_dia.isoformat() <= p["fecha"] <= ultimo_dia.isoformat()], metodo

    def get_prediccion_compras_mes(
        self, categoria: str | None = None, producto_cod: str | None = None,
        sucursal: str | None = None, almacen: str | None = None, proveedor: str | None = None,
    ) -> dict[str, Any]:
        """Predicción de compras del mes calendario siguiente (RN-B7): agrega el
        forecast `demand_rf` de los `BODEGA_TOP_ARTICULOS_PREDICCION` artículos con
        más ventas de la categoría (o la predicción individual si `producto_cod`)."""
        cache_key = (categoria, producto_cod, sucursal, almacen, proveedor)
        cacheado = self._prediccion_cache_get(cache_key)
        if cacheado is not None:
            return cacheado

        primer_dia, ultimo_dia, dias_horizonte = self._rango_mes_siguiente()
        desde_hist, hasta_hist, _, _ = self._defaults_rango(None, None)

        if producto_cod:
            resultado = self._prediccion_compras_mes_articulo(
                producto_cod, categoria, dias_horizonte, primer_dia, ultimo_dia,
                desde_hist, hasta_hist, sucursal, almacen, proveedor,
            )
            self._prediccion_cache_set(cache_key, resultado)
            return resultado

        resultado = self._prediccion_compras_mes_categoria(
            categoria, dias_horizonte, primer_dia, ultimo_dia, desde_hist, hasta_hist,
            sucursal, almacen, proveedor,
        )
        self._prediccion_cache_set(cache_key, resultado)
        return resultado

    def _prediccion_compras_mes_articulo(
        self, producto_cod: str, categoria: str | None, dias_horizonte: int,
        primer_dia: datetime.date, ultimo_dia: datetime.date, desde_hist: str, hasta_hist: str,
        sucursal: str | None, almacen: str | None, proveedor: str | None,
    ) -> dict[str, Any]:
        filtrado, metodo = self._prediccion_articulo(
            producto_cod, dias_horizonte, primer_dia, ultimo_dia, desde_hist, hasta_hist,
            sucursal, almacen, proveedor,
        )
        inv = next(
            (r for r in self.repo.get_inventario_productos(
                sucursal=sucursal, almacen=almacen, categoria=categoria, proveedor=proveedor, tipo_movimiento=None,
            ) if r["codart"] == producto_cod),
            None,
        )
        stock_actual = inv["stock_actual"] if inv else 0.0
        costo_unitario = inv["costo_unitario"] if inv else 0.0
        prediccion_mes = round(sum(p["unidades"] for p in filtrado), 2)
        compra_sugerida = round(max(0.0, prediccion_mes - stock_actual), 2)
        return {
            "mes_objetivo": primer_dia.strftime("%Y-%m"),
            "categoria": categoria,
            "producto_cod": producto_cod,
            "metodo": metodo,
            "serie": filtrado,
            "resumen": {
                "unidades_previstas_mes": prediccion_mes,
                "costo_estimado_compra": round(compra_sugerida * costo_unitario, 2),
                "productos_incluidos": 1,
            },
            "top_articulos": [],
        }

    def _prediccion_compras_mes_categoria(
        self, categoria: str | None, dias_horizonte: int, primer_dia: datetime.date, ultimo_dia: datetime.date,
        desde_hist: str, hasta_hist: str, sucursal: str | None, almacen: str | None, proveedor: str | None,
    ) -> dict[str, Any]:
        # Ranking por ventas reales (fact_ventas_detalle vía get_rotacion_productos) --
        # no por kardex (get_salidas_por_producto usa fact_movimientos_inventario, no
        # es lo que pide el requerimiento "artículos con más ventas", auditoría 24 H24-1).
        candidatos = self.repo.get_rotacion_productos(
            desde_hist, hasta_hist, sucursal=sucursal, almacen=almacen, categoria=categoria,
            proveedor=proveedor, tipo_movimiento=None, limit=500,
        )
        top_n = sorted(candidatos, key=lambda c: -c["unidades_vendidas"])[:settings.BODEGA_TOP_ARTICULOS_PREDICCION]
        inventario_por_codart = {
            r["codart"]: r for r in self.repo.get_inventario_productos(
                sucursal=sucursal, almacen=almacen, categoria=categoria, proveedor=proveedor, tipo_movimiento=None,
            )
        }

        serie_categoria: dict[str, dict[str, float]] = {}
        top_articulos: list[dict[str, Any]] = []
        metodos: set[str] = set()
        unidades_totales = 0.0
        costo_total = 0.0

        for c in top_n:
            codart = c["codart"]
            filtrado, metodo = self._prediccion_articulo(
                codart, dias_horizonte, primer_dia, ultimo_dia, desde_hist, hasta_hist,
                sucursal, almacen, proveedor,
            )
            metodos.add(metodo)
            prediccion_mes = round(sum(p["unidades"] for p in filtrado), 2)
            inv = inventario_por_codart.get(codart)
            stock_actual = inv["stock_actual"] if inv else c["stock_actual"]
            punto_reorden = (
                self._punto_reorden_efectivo(inv["punto_reorden_config"], self._salida_diaria(inv["salidas_periodo"]))
                if inv else 0.0
            )
            costo_unitario = inv["costo_unitario"] if inv else 0.0
            compra_sugerida = round(max(0.0, prediccion_mes - stock_actual), 2)

            top_articulos.append({
                "codart": codart, "nombre": c["nombre"], "categoria": c["categoria"],
                "unidades_vendidas_periodo": c["unidades_vendidas"],
                "stock_actual": stock_actual, "punto_reorden": punto_reorden,
                "prediccion_mes": prediccion_mes, "compra_sugerida": compra_sugerida,
                "metodo": metodo,
            })
            unidades_totales += prediccion_mes
            costo_total += compra_sugerida * costo_unitario

            for p in filtrado:
                acc = serie_categoria.setdefault(
                    p["fecha"], {"unidades": 0.0, "banda_superior": 0.0, "banda_inferior": 0.0},
                )
                acc["unidades"] += p["unidades"]
                acc["banda_superior"] += p["banda_superior"]
                acc["banda_inferior"] += p["banda_inferior"]

        # Suma directa de bandas de N series = aproximación conservadora, no una banda
        # estadísticamente rigurosa (se declara en docs, auditoría 24 H24-4).
        metodo_global = "estadistico" if metodos <= {"estadistico"} else "ml_demand_rf"
        serie = [
            {
                "fecha": f, "unidades": round(v["unidades"], 2),
                "banda_superior": round(v["banda_superior"], 2),
                "banda_inferior": round(max(0.0, v["banda_inferior"]), 2),
            }
            for f, v in sorted(serie_categoria.items())
        ]
        return {
            "mes_objetivo": primer_dia.strftime("%Y-%m"),
            "categoria": categoria,
            "producto_cod": None,
            "metodo": metodo_global,
            "serie": serie,
            "resumen": {
                "unidades_previstas_mes": round(unidades_totales, 2),
                "costo_estimado_compra": round(costo_total, 2),
                "productos_incluidos": len(top_articulos),
            },
            "top_articulos": top_articulos,
        }

    # ── Gráfico 2 (§1.3): matriz rotación × margen ──────────────────────────
    def get_rotacion_matriz(
        self, sucursal: str | None = None, almacen: str | None = None,
        categoria: str | None = None, proveedor: str | None = None,
        tipo_movimiento: str | None = None, fecha_desde: str | None = None,
        fecha_hasta: str | None = None,
    ) -> dict[str, Any]:
        desde, hasta, _, _ = self._defaults_rango(fecha_desde, fecha_hasta)
        filas = self.repo.get_rotacion_productos(
            desde, hasta, sucursal=sucursal, almacen=almacen, categoria=categoria,
            proveedor=proveedor, tipo_movimiento=tipo_movimiento,
        )
        dias_rango = max(
            (datetime.date.fromisoformat(hasta) - datetime.date.fromisoformat(desde)).days, 1,
        )
        puntos = []
        for f in filas:
            # Rotación mensual del producto: veces que rota el stock según el costo
            # vendido del período normalizado a 30 días (RN-B5 a grano producto).
            costo_mensual = f["costo_ventas"] * 30 / dias_rango
            rotacion_mensual = (costo_mensual / f["valor_inventario"]) if f["valor_inventario"] > 0 else None
            margen_unitario = (f["margen_total"] / f["unidades_vendidas"]) if f["unidades_vendidas"] > 0 else 0.0
            salida_diaria = f["unidades_vendidas"] / dias_rango
            puntos.append({
                "codart": f["codart"],
                "nombre": f["nombre"],
                "categoria": f["categoria"],
                "rotacion_mensual": round(rotacion_mensual, 2) if rotacion_mensual is not None else None,
                "margen_unitario": round(margen_unitario, 2),
                "stock_actual": f["stock_actual"],
                "valor_inventario": round(f["valor_inventario"], 2),
                "dias_inventario": self._dias_inventario(f["stock_actual"], salida_diaria),
            })
        con_rotacion = [p["rotacion_mensual"] for p in puntos if p["rotacion_mensual"] is not None]
        margenes = [p["margen_unitario"] for p in puntos]
        return {
            "productos": puntos,
            # Medianas para trazar los ejes de los cuadrantes en el frontend.
            "mediana_rotacion": round(float(pd.Series(con_rotacion).median()), 2) if con_rotacion else 0.0,
            "mediana_margen": round(float(pd.Series(margenes).median()), 2) if margenes else 0.0,
        }

    # ── Gráficos 3 y 4 (§1.3) ────────────────────────────────────────────────
    def get_top_productos(
        self, sucursal: str | None = None, almacen: str | None = None,
        categoria: str | None = None, proveedor: str | None = None,
        tipo_movimiento: str | None = None, fecha_desde: str | None = None,
        fecha_hasta: str | None = None, limit: int = 20,
    ) -> list[dict[str, Any]]:
        desde, hasta, desde_prev, hasta_prev = self._defaults_rango(fecha_desde, fecha_hasta)
        dias_rango = max((datetime.date.fromisoformat(hasta) - datetime.date.fromisoformat(desde)).days, 1)
        filas = self.repo.get_salidas_por_producto(
            desde, hasta, desde_prev, hasta_prev, sucursal=sucursal, almacen=almacen,
            categoria=categoria, proveedor=proveedor, tipo_movimiento=tipo_movimiento, limit=limit,
        )
        out = []
        for f in filas:
            salida_diaria = self._salida_diaria(f["unidades"], dias_rango)
            out.append({
                "codart": f["codart"],
                "nombre": f["nombre"],
                "categoria": f["categoria"],
                "unidades": f["unidades"],
                "stock_actual": f["stock_actual"],
                "dias_inventario": self._dias_inventario(f["stock_actual"], salida_diaria),
                "tendencia_pct": self._tendencia_pct(f["unidades"], f["unidades_previo"]),
            })
        return out

    def get_salidas_categoria(
        self, sucursal: str | None = None, almacen: str | None = None,
        proveedor: str | None = None, tipo_movimiento: str | None = None,
        fecha_desde: str | None = None, fecha_hasta: str | None = None,
    ) -> list[dict[str, Any]]:
        desde, hasta, desde_prev, hasta_prev = self._defaults_rango(fecha_desde, fecha_hasta)
        filas = self.repo.get_salidas_por_categoria(
            desde, hasta, desde_prev, hasta_prev, sucursal=sucursal, almacen=almacen,
            proveedor=proveedor, tipo_movimiento=tipo_movimiento,
        )
        total = sum(f["unidades"] for f in filas) or 1.0
        return [
            {
                **f,
                "pct_participacion": round(f["unidades"] / total * 100, 1),
                "tendencia_pct": self._tendencia_pct(f["unidades"], f["unidades_previo"]),
            }
            for f in filas
        ]

    # ── Gráfico 5 (§1.3): estado vs punto de reorden ────────────────────────
    def _stock_reorden_filas(
        self, sucursal: str | None = None, almacen: str | None = None,
        categoria: str | None = None, proveedor: str | None = None,
        tipo_movimiento: str | None = None, solo_criticos: bool = False,
    ) -> list[dict[str, Any]]:
        """Lista completa ordenada (sin paginar) -- consumida por el endpoint paginado
        y por los reportes internos (§2), que necesitan el dataset completo."""
        productos = [
            self._enriquecer_producto(r)
            for r in self.repo.get_inventario_productos(
                sucursal=sucursal, almacen=almacen, categoria=categoria,
                proveedor=proveedor, tipo_movimiento=tipo_movimiento,
            )
        ]
        orden_estado = {ESTADO_CRITICO: 0, ESTADO_CERCA: 1, ESTADO_SEGURO: 2, ESTADO_EXCESO: 3}
        productos.sort(key=lambda p: (orden_estado.get(p["estado"], 9), p["dias_hasta_reorden"] or 1e9))
        if solo_criticos:
            productos = [p for p in productos if p["estado"] == ESTADO_CRITICO]
        return [
            {
                "codart": p["codart"], "nombre": p["nombre"], "categoria": p["categoria"],
                "stock_actual": p["stock_actual"], "punto_reorden": p["punto_reorden"],
                "salida_diaria": p["salida_diaria"], "dias_inventario": p["dias_inventario"],
                "dias_hasta_reorden": p["dias_hasta_reorden"], "estado": p["estado"],
            }
            for p in productos
        ]

    def get_stock_reorden(
        self, pagination: PaginationParams, sucursal: str | None = None, almacen: str | None = None,
        categoria: str | None = None, proveedor: str | None = None,
        tipo_movimiento: str | None = None, solo_criticos: bool = False,
    ) -> Page[dict[str, Any]]:
        filas = self._stock_reorden_filas(
            sucursal=sucursal, almacen=almacen, categoria=categoria,
            proveedor=proveedor, tipo_movimiento=tipo_movimiento, solo_criticos=solo_criticos,
        )
        return paginar(filas, pagination)

    # ── Gráfico 6 + §3.3 (RN-B4): necesidad/plan de compra ──────────────────
    NO_COMPRAR_RESUMEN_MAX = 50  # `no_comprar` es un resumen informativo, no se pagina (plan §4.2)

    def _necesidad_compra_completo(
        self, sucursal: str | None = None, almacen: str | None = None,
        categoria: str | None = None, proveedor: str | None = None,
        tipo_movimiento: str | None = None, horizonte_dias: int | None = None,
    ) -> dict[str, Any]:
        """`recomendados`/`no_comprar` completos (sin paginar) -- consumido por el
        endpoint paginado y por los reportes internos (§2), que necesitan el total."""
        horizonte = horizonte_dias or settings.BODEGA_HORIZONTE_COMPRA_DIAS
        productos = [
            self._enriquecer_producto(r)
            for r in self.repo.get_inventario_productos(
                sucursal=sucursal, almacen=almacen, categoria=categoria,
                proveedor=proveedor, tipo_movimiento=tipo_movimiento,
            )
        ]
        hoy = datetime.date.today()
        recomendados = []
        no_comprar = []
        for p in productos:
            dias_inv = p["dias_inventario"]
            rotacion_anual = (p["salidas_periodo"] * 12 * p["costo_unitario"] / p["valor_inventario"]) \
                if p["valor_inventario"] > 0 else None
            # Productos que NO deben comprarse (§3.3-S2): exceso o baja rotación.
            if dias_inv is not None and dias_inv > settings.BODEGA_DIAS_EXCESO:
                no_comprar.append({
                    **self._fila_compra(p, 0.0, hoy),
                    "motivo": f"Stock para más de {settings.BODEGA_DIAS_EXCESO} días",
                })
                continue
            if rotacion_anual is not None and rotacion_anual < settings.BODEGA_ROTACION_REGULAR and p["stock_actual"] > 0:
                no_comprar.append({
                    **self._fila_compra(p, 0.0, hoy),
                    "motivo": "Baja rotación (< 2 veces/año)",
                })
                continue
            # Comprar (RN-B4): días de inventario bajo el umbral (o sin stock con demanda).
            debe_comprar = (
                (dias_inv is not None and dias_inv < settings.BODEGA_DIAS_COMPRA)
                or (p["stock_actual"] <= 0 and p["salida_diaria"] > 0)
            )
            if not debe_comprar:
                continue
            cantidad = max(0.0, round(p["salida_diaria"] * horizonte - p["stock_actual"], 0))
            if cantidad <= 0:
                continue
            if p["estado"] == ESTADO_CRITICO:
                prioridad, justificacion = "Alta", "Stock crítico"
            elif dias_inv is not None and dias_inv < settings.BODEGA_DIAS_DEFICIT:
                prioridad, justificacion = "Alta", "Riesgo de desabastecimiento"
            elif rotacion_anual is not None and rotacion_anual > settings.BODEGA_ROTACION_MIN_COMPRA:
                prioridad, justificacion = "Media", "Alta rotación"
            else:
                prioridad, justificacion = "Baja", "Reposición preventiva"
            recomendados.append({
                **self._fila_compra(p, cantidad, hoy),
                "prioridad": prioridad,
                "justificacion": justificacion,
            })

        orden_prioridad = {"Alta": 0, "Media": 1, "Baja": 2}
        recomendados.sort(key=lambda r: (orden_prioridad[r["prioridad"]], r["dias_hasta_reorden"] or 1e9))
        return {
            "horizonte_dias": horizonte,
            "recomendados": recomendados,
            "no_comprar": no_comprar,
            "total_productos_a_comprar": len(recomendados),
            "valor_total_compra": round(sum(r["costo_total"] for r in recomendados), 2),
            "ahorro_por_no_comprar": round(
                sum(n["stock_actual"] * n["costo_unitario"] for n in no_comprar), 2,
            ),
        }

    def get_necesidad_compra(
        self, pagination: PaginationParams, sucursal: str | None = None, almacen: str | None = None,
        categoria: str | None = None, proveedor: str | None = None,
        tipo_movimiento: str | None = None, horizonte_dias: int | None = None,
    ) -> dict[str, Any]:
        completo = self._necesidad_compra_completo(
            sucursal=sucursal, almacen=almacen, categoria=categoria,
            proveedor=proveedor, tipo_movimiento=tipo_movimiento, horizonte_dias=horizonte_dias,
        )
        return {
            **completo,
            "recomendados": paginar(completo["recomendados"], pagination),
            "no_comprar": completo["no_comprar"][: self.NO_COMPRAR_RESUMEN_MAX],
        }

    def _fila_compra(self, p: dict[str, Any], cantidad: float, hoy: datetime.date) -> dict[str, Any]:
        fecha_reorden = None
        if p["dias_hasta_reorden"] is not None:
            fecha_reorden = (hoy + datetime.timedelta(days=int(p["dias_hasta_reorden"]))).isoformat()
        return {
            "codart": p["codart"], "nombre": p["nombre"], "categoria": p["categoria"],
            "stock_actual": p["stock_actual"], "salida_diaria": p["salida_diaria"],
            "dias_inventario": p["dias_inventario"], "dias_hasta_reorden": p["dias_hasta_reorden"],
            "fecha_estimada_reorden": fecha_reorden,
            "cantidad_sugerida": cantidad,
            "costo_unitario": p["costo_unitario"],
            "costo_total": round(cantidad * p["costo_unitario"], 2),
        }

    # ── Panel §3.1: matriz de inventario por almacén ─────────────────────────
    def _inventario_matriz_completo(
        self, sucursal: str | None = None, almacen: str | None = None, categoria: str | None = None,
        proveedor: str | None = None, tipo_movimiento: str | None = None,
        estado: str | None = None,
    ) -> dict[str, Any]:
        # `almacen`: si el usuario lo filtra, la matriz se restringe a esa sola bodega
        # (una columna) en vez de mostrar todas -- stock_total/punto_reorden/estado se
        # recalculan solo sobre las filas devueltas, así que quedan consistentes.
        filas = self.repo.get_stock_por_almacen(
            sucursal=sucursal, almacen=almacen, categoria=categoria,
            proveedor=proveedor, tipo_movimiento=tipo_movimiento,
        )
        almacenes = sorted({f["almacen"] for f in filas})
        por_producto: dict[str, dict[str, Any]] = {}
        for f in filas:
            item = por_producto.setdefault(f["codart"], {
                "codart": f["codart"], "nombre": f["nombre"], "categoria": f["categoria"],
                "stock_por_almacen": {}, "stock_total": 0.0,
                "salidas_periodo": 0.0, "punto_reorden_config": 0.0,
            })
            item["stock_por_almacen"][f["almacen"]] = f["stock_actual"]
            item["stock_total"] += f["stock_actual"]
            item["salidas_periodo"] += f["salidas_periodo"]
            item["punto_reorden_config"] += f["punto_reorden_config"]

        productos = []
        for item in por_producto.values():
            salida_diaria = self._salida_diaria(item["salidas_periodo"])
            reorden = self._punto_reorden_efectivo(item["punto_reorden_config"], salida_diaria)
            dias_inv = self._dias_inventario(item["stock_total"], salida_diaria)
            item_estado = self._estado_stock(item["stock_total"], reorden, dias_inv)
            productos.append({
                "codart": item["codart"], "nombre": item["nombre"], "categoria": item["categoria"],
                "stock_por_almacen": item["stock_por_almacen"],
                "stock_total": round(item["stock_total"], 2),
                "punto_reorden": reorden,
                "dias_inventario": dias_inv,
                "estado": item_estado,
            })
        if estado:
            productos = [p for p in productos if p["estado"] == estado]
        productos.sort(key=lambda p: ({ESTADO_CRITICO: 0, ESTADO_CERCA: 1, ESTADO_EXCESO: 2, ESTADO_SEGURO: 3}
                                      .get(p["estado"], 9), -p["stock_total"]))
        return {"almacenes": almacenes, "productos": productos}

    def get_inventario_matriz(
        self, pagination: PaginationParams, sucursal: str | None = None, almacen: str | None = None,
        categoria: str | None = None, proveedor: str | None = None, tipo_movimiento: str | None = None,
        estado: str | None = None,
    ) -> dict[str, Any]:
        completo = self._inventario_matriz_completo(
            sucursal=sucursal, almacen=almacen, categoria=categoria, proveedor=proveedor,
            tipo_movimiento=tipo_movimiento, estado=estado,
        )
        return {
            "almacenes": completo["almacenes"],
            "productos": paginar(completo["productos"], pagination),
        }

    # ── Panel §3.2 (RN-B3): transferencias inteligentes ──────────────────────
    def _transferencias_completo(
        self, sucursal: str | None = None, categoria: str | None = None,
        proveedor: str | None = None, tipo_movimiento: str | None = None,
    ) -> dict[str, Any]:
        filas = self.repo.get_stock_por_almacen(
            sucursal=sucursal, categoria=categoria, proveedor=proveedor, tipo_movimiento=tipo_movimiento,
        )
        por_producto: dict[str, list[dict[str, Any]]] = {}
        for f in filas:
            por_producto.setdefault(f["codart"], []).append(f)

        sugerencias = []
        for codart, bodegas in por_producto.items():
            if len(bodegas) < 2:
                continue
            enriquecidas = []
            for b in bodegas:
                salida_diaria = self._salida_diaria(b["salidas_periodo"])
                dias_inv = self._dias_inventario(b["stock_actual"], salida_diaria)
                reorden = self._punto_reorden_efectivo(b["punto_reorden_config"], salida_diaria)
                enriquecidas.append({**b, "salida_diaria": salida_diaria, "dias_inv": dias_inv,
                                     "reorden": reorden})
            # Origen: excedente (>60 días de inventario, o stock sin salidas). Destino:
            # déficit (<15 días con demanda).
            origenes = [
                b for b in enriquecidas
                if (b["dias_inv"] is not None and b["dias_inv"] > settings.BODEGA_DIAS_EXCEDENTE)
                or (b["dias_inv"] is None and b["stock_actual"] > 0)
            ]
            destinos = [
                b for b in enriquecidas
                if b["salida_diaria"] > 0 and (b["dias_inv"] or 0) < settings.BODEGA_DIAS_DEFICIT
            ]
            for destino in destinos:
                for origen in origenes:
                    if origen["almacen"] == destino["almacen"]:
                        continue
                    objetivo = destino["salida_diaria"] * settings.BODEGA_DIAS_OBJETIVO_TRANSFERENCIA
                    necesidad = max(0.0, objetivo - destino["stock_actual"])
                    # Sin exceder el excedente del origen (dejarlo en 60 días como piso).
                    piso_origen = (origen["salida_diaria"] * settings.BODEGA_DIAS_EXCEDENTE
                                   if origen["salida_diaria"] > 0 else 0.0)
                    disponible = max(0.0, origen["stock_actual"] - piso_origen)
                    cantidad = round(min(necesidad, disponible), 0)
                    if cantidad <= 0:
                        continue
                    if destino["stock_actual"] < destino["reorden"]:
                        prioridad = "Alta"
                    elif (destino["dias_inv"] or 0) < settings.BODEGA_DIAS_DEFICIT:
                        prioridad = "Media"
                    else:
                        prioridad = "Baja"
                    dias_dest_post = self._dias_inventario(
                        destino["stock_actual"] + cantidad, destino["salida_diaria"],
                    )
                    dias_origen_txt = (
                        f"{origen['dias_inv']:.0f} días de stock" if origen["dias_inv"] is not None
                        else "stock sin salidas registradas"
                    )
                    sugerencias.append({
                        "codart": codart,
                        "nombre": destino["nombre"],
                        "categoria": destino["categoria"],
                        "almacen_origen": origen["almacen"],
                        "stock_origen": origen["stock_actual"],
                        "dias_inv_origen": origen["dias_inv"],
                        "almacen_destino": destino["almacen"],
                        "stock_destino": destino["stock_actual"],
                        "dias_inv_destino": destino["dias_inv"],
                        "cantidad_transferir": cantidad,
                        "dias_inv_destino_post": dias_dest_post,
                        "prioridad": prioridad,
                        "ahorro_estimado": round(cantidad * destino["costo_unitario"], 2),
                        "motivo": (
                            f"En {origen['almacen']} tiene {dias_origen_txt} "
                            f"(salidas {origen['salida_diaria']:.1f} uds/día); en {destino['almacen']} "
                            f"tiene {(destino['dias_inv'] or 0):.0f} días de stock "
                            f"(salidas {destino['salida_diaria']:.1f} uds/día)."
                        ),
                    })
                    break  # un origen por destino: la mejor fuente disponible

        orden = {"Alta": 0, "Media": 1, "Baja": 2}
        sugerencias.sort(key=lambda s: (orden[s["prioridad"]], -s["ahorro_estimado"]))
        return {
            "sugerencias": sugerencias,
            "total_sugerencias": len(sugerencias),
            "ahorro_total_estimado": round(sum(s["ahorro_estimado"] for s in sugerencias), 2),
        }

    def get_transferencias_sugeridas(
        self, pagination: PaginationParams, sucursal: str | None = None, categoria: str | None = None,
        proveedor: str | None = None, tipo_movimiento: str | None = None,
    ) -> dict[str, Any]:
        completo = self._transferencias_completo(
            sucursal=sucursal, categoria=categoria, proveedor=proveedor, tipo_movimiento=tipo_movimiento,
        )
        return {
            **completo,
            "sugerencias": paginar(completo["sugerencias"], pagination),
        }

    # ── §4: notificaciones calculadas al vuelo ───────────────────────────────
    def get_notificaciones(
        self, sucursal: str | None = None, almacen: str | None = None,
    ) -> list[dict[str, Any]]:
        notificaciones: list[dict[str, Any]] = []
        hoy = datetime.date.today()

        productos = [
            self._enriquecer_producto(r)
            for r in self.repo.get_inventario_productos(sucursal=sucursal, almacen=almacen)
        ]

        # Stock crítico (§4.2 fila 1) — límite para no inundar la campana.
        criticos = [p for p in productos if p["estado"] == ESTADO_CRITICO]
        for p in criticos[:10]:
            notificaciones.append({
                "tipo": "stock_critico", "prioridad": "alta",
                "mensaje": (
                    f"⚠️ {p['nombre']} ({p['codart']}) tiene stock crítico. "
                    f"Nivel actual: {p['stock_actual']:.0f}, Punto reorden: {p['punto_reorden']:.0f}"
                ),
                "codart": p["codart"],
            })
        if len(criticos) > 10:
            notificaciones.append({
                "tipo": "stock_critico_resumen", "prioridad": "alta",
                "mensaje": f"🔴 Hay {len(criticos)} productos con stock crítico en total.",
                "codart": None,
            })

        # Predicción de agotamiento <7 días (§4.2 fila 2) — derivada estadística.
        por_agotarse = [
            p for p in productos
            if p["estado"] != ESTADO_CRITICO
            and p["dias_hasta_reorden"] is not None and p["dias_hasta_reorden"] < 7
        ]
        for p in por_agotarse[:10]:
            notificaciones.append({
                "tipo": "prediccion_agotamiento", "prioridad": "alta",
                "mensaje": (
                    f"🔮 {p['nombre']} ({p['codart']}) llegará al punto de reorden en "
                    f"{p['dias_hasta_reorden']:.0f} días según proyección. Considerar compra."
                ),
                "codart": p["codart"],
            })

        # Transferencias sugeridas (§4.2 fila 3).
        transferencias = self._transferencias_completo(sucursal=sucursal)
        for t in transferencias["sugerencias"][:5]:
            notificaciones.append({
                "tipo": "transferencia_sugerida", "prioridad": "media",
                "mensaje": (
                    f"🔄 {t['nombre']} ({t['codart']}) tiene excedente en {t['almacen_origen']} y "
                    f"déficit en {t['almacen_destino']}. Transferir {t['cantidad_transferir']:.0f} unidades."
                ),
                "codart": t["codart"],
            })

        # Informe semanal listo: 5 días antes del fin de mes (§4.2 fila 4).
        ultimo_dia = (hoy.replace(day=28) + datetime.timedelta(days=4)).replace(day=1) - datetime.timedelta(days=1)
        if (ultimo_dia - hoy).days <= 5:
            notificaciones.append({
                "tipo": "reporte_semanal", "prioridad": "alta",
                "mensaje": "📋 Reporte de compras sugeridas para el próximo mes disponible.",
                "codart": None,
            })

        return notificaciones

    # ── §2: reportes para gerencia ───────────────────────────────────────────
    def get_reporte_justificacion(
        self, sucursal: str | None = None, almacen: str | None = None,
        categoria: str | None = None, proveedor: str | None = None,
    ) -> dict[str, Any]:
        """§2.1 — Reporte de Justificación de Abastecimiento."""
        filtros = dict(sucursal=sucursal, almacen=almacen, categoria=categoria, proveedor=proveedor)
        compra = self._necesidad_compra_completo(**filtros, horizonte_dias=settings.BODEGA_HORIZONTE_PLAN_DIAS)
        rotacion = self.get_rotacion_matriz(**filtros)
        transferencias = self._transferencias_completo(
            sucursal=sucursal, categoria=categoria, proveedor=proveedor,
        )
        kpis = self.get_kpis(**filtros)

        productos_rot = [p for p in rotacion["productos"] if p["rotacion_mensual"] is not None]
        top_rotacion = sorted(productos_rot, key=lambda p: -p["rotacion_mensual"])[:20]
        bottom_rotacion = sorted(productos_rot, key=lambda p: p["rotacion_mensual"])[:10]

        resumen_categoria: dict[str, dict[str, float]] = {}
        for r in compra["recomendados"]:
            acc = resumen_categoria.setdefault(r["categoria"], {"productos": 0, "valor": 0.0})
            acc["productos"] += 1
            acc["valor"] = round(acc["valor"] + r["costo_total"], 2)

        return {
            "generado_en": datetime.datetime.now().isoformat(timespec="seconds"),
            "filtros": {k: v for k, v in filtros.items() if v},
            "resumen_ejecutivo": {
                "total_productos_a_comprar": compra["total_productos_a_comprar"],
                "valor_total_compra": compra["valor_total_compra"],
                "resumen_por_categoria": [
                    {"categoria": c, **v} for c, v in sorted(
                        resumen_categoria.items(), key=lambda kv: -kv[1]["valor"],
                    )
                ],
                "tendencia_valor_inventario_pct": kpis["valor_inventario"]["tendencia_pct"],
            },
            "productos_recomendados": compra["recomendados"],
            "analisis_rotacion": {"top_rotacion": top_rotacion, "bottom_rotacion": bottom_rotacion},
            "proyeccion": {
                "horizonte_dias": compra["horizonte_dias"],
                "posibles_desabastecimientos": [
                    r for r in compra["recomendados"] if r["prioridad"] == "Alta"
                ],
            },
            "transferencias": transferencias,
            "ahorro_por_no_comprar": compra["ahorro_por_no_comprar"],
        }

    def get_reporte_transferencias(
        self, sucursal: str | None = None, categoria: str | None = None,
    ) -> dict[str, Any]:
        """§2.2 — Reporte de Productos Candidatos a Transferencia."""
        data = self._transferencias_completo(sucursal=sucursal, categoria=categoria)
        sugerencias = data["sugerencias"]
        return {
            "generado_en": datetime.datetime.now().isoformat(timespec="seconds"),
            "resumen": {
                "productos_con_excedente": len({s["codart"] for s in sugerencias}),
                "productos_con_deficit": len({(s["codart"], s["almacen_destino"]) for s in sugerencias}),
                "valor_transferible": data["ahorro_total_estimado"],
            },
            "transferencias_sugeridas": sugerencias,
            "ahorro": {
                "monto_ahorrado_por_no_comprar": data["ahorro_total_estimado"],
            },
            "por_prioridad": {
                nivel: [s for s in sugerencias if s["prioridad"] == nivel]
                for nivel in ("Alta", "Media", "Baja")
            },
        }

    def get_reporte_analisis_mensual(
        self, sucursal: str | None = None, almacen: str | None = None,
    ) -> dict[str, Any]:
        """§2.3 — Reporte mensual consolidado de Stock y Abastecimiento."""
        filtros = dict(sucursal=sucursal, almacen=almacen)
        kpis = self.get_kpis(**filtros)
        stock = self._stock_reorden_filas(**filtros)[:50]
        compra = self._necesidad_compra_completo(**filtros)
        return {
            "generado_en": datetime.datetime.now().isoformat(timespec="seconds"),
            "resumen_general": {
                # H24-x: usar skus_activos (con stock real), no total_skus (catálogo completo,
                # idéntico para cualquier almacén -- ver comentario en get_kpis).
                "total_articulos": kpis["total_articulos"]["skus_activos"],
                "valor_inventario": kpis["valor_inventario"]["valor_total"],
                "rotacion_anualizada": kpis["rotacion"]["rotacion_anualizada"],
                "dias_inventario": kpis["dias_inventario"]["dias"],
            },
            "productos_criticos": [p for p in stock if p["estado"] == ESTADO_CRITICO],
            "productos_exceso": [p for p in stock if p["estado"] == ESTADO_EXCESO],
            "comparativa_mes_anterior": {
                "variacion_valor_pct": kpis["valor_inventario"]["tendencia_pct"],
                "variacion_articulos_pct": kpis["total_articulos"]["tendencia_pct"],
            },
            "plan_compras": {
                "recomendados": compra["recomendados"],
                "valor_total": compra["valor_total_compra"],
            },
        }
