# backend/app/services/cross_sell_engine_service.py
"""Motor compuesto de Venta Cruzada (docs/features/plan_refactor_venta_cruzada_ia.md,
decisión de arquitectura §3.1): servicio nuevo, NO se agrega a `PredictionService`
(ya tiene 6 casos de uso genéricos y 590+ líneas). Este servicio ORQUESTA -- consume
`PredictionService` por inyección (mismo patrón que `Cartera360Service`), nunca
reimplementa inferencia. Fase 1 solo cubre el perfil de cliente 360; la Fase 2 (ranker
de recomendaciones) se agrega aquí, no en un servicio nuevo distinto."""
import logging
from typing import Any

from app.core.exceptions import NotFoundError, PermissionDeniedError
from app.repositories.cartera360_repository import Cartera360Repository
from app.repositories.catalog_repository import CatalogRepository
from app.services.prediction_service import PredictionService

logger = logging.getLogger("Backend.CrossSellEngineService")


class CrossSellEngineService:
    def __init__(
        self,
        cartera360_repo: Cartera360Repository,
        catalog_repo: CatalogRepository,
        prediction_service: PredictionService,
    ):
        self.cartera360_repo = cartera360_repo
        self.catalog_repo = catalog_repo
        self.prediction_service = prediction_service

    def _verificar_pertenencia_cartera(self, cliente_id: str, codven_restriccion: str | None) -> None:
        """Mismo criterio de RLS que `PredictionService._verificar_pertenencia_cartera`
        (docs/auditoria/34_actualizacion_modulo_ventas.md, H-V2) -- decisión §3 punto 6
        del plan: todo endpoint nuevo con `cliente_id` debe aplicarlo, sin excepción."""
        if codven_restriccion is None:
            return
        if not self.catalog_repo.cliente_pertenece_a_vendedor(cliente_id, codven_restriccion):
            raise PermissionDeniedError(
                f"El cliente '{cliente_id}' no pertenece a la cartera del vendedor autenticado."
            )

    def get_perfil_cliente(self, cliente_id: str, codven_restriccion: str | None = None) -> dict[str, Any]:
        """Compone estadística pura del EDW (`Cartera360Repository`, CLV histórico y
        agregados por cliente) con los dos modelos que ya se sirven por cliente
        (`churn_rf` vía `PredictionService.get_churn_risk`, `kmeans_rfm` vía
        `get_customer_segment`) -- sin entrenar ni servir nada nuevo. Nombre real
        (`search_clientes`) resuelto aparte por el router, este método asume que ya
        se conoce el nombre a mostrar."""
        self._verificar_pertenencia_cartera(cliente_id, codven_restriccion)

        datos = self.catalog_repo.get_cliente_datos(cliente_id)
        if datos is None:
            raise NotFoundError(f"Cliente '{cliente_id}' no encontrado.")

        perfil = self.cartera360_repo.get_perfil_cliente(cliente_id)
        tiene_historial = perfil is not None

        resultado: dict[str, Any] = {
            "cliente_id": cliente_id,
            "nombre": datos["nombre"],
            "ciudad": datos["ciudad"],
            "tiene_historial": tiene_historial,
            "num_compras": None, "ultima_compra": None, "antiguedad_dias": None,
            "valor_historico": None, "ticket_promedio": None, "frecuencia_12m": None,
            "categoria_favorita": None, "productos_favoritos": [],
        }
        if tiene_historial:
            assert perfil is not None
            resultado.update(perfil)
            resultado["productos_favoritos"] = self.cartera360_repo.get_productos_favoritos_cliente(cliente_id)

        # churn_rf/kmeans_rfm ya manejan "sin historial" devolviendo su propio estado
        # neutro (ver PredictionService.get_churn_risk/get_customer_segment) -- no se
        # duplica esa lógica aquí, solo se propaga sin la doble verificación de RLS
        # (codven_restriccion ya se validó arriba en esta misma llamada).
        churn = self.prediction_service.get_churn_risk(cliente_id, codven_restriccion=None)
        segmento = self.prediction_service.get_customer_segment(cliente_id, codven_restriccion=None)

        resultado["probabilidad_recompra"] = round(100 - churn["probabilidad_abandono"], 2)
        resultado["riesgo_alto_abandono"] = churn["riesgo_alto"]
        resultado["segmento"] = segmento["segmento"] if segmento["segmento"] != -1 else None
        resultado["nombre_segmento"] = segmento["nombre_segmento"]
        return resultado

    def simular_venta(self, items: list[str], cliente_id: str | None, codven_restriccion: str | None = None) -> dict[str, Any]:
        """Fase 3 (CAMBIO 4/12 del plan): cifras REALES sobre la canasta que el
        vendedor está armando -- ningún número aquí es una predicción inventada.
        `ticket_estimado`/`margen_estimado` salen de `dim_producto` vigente
        (`CatalogRepository.get_products_info`, ya usado por el asistente de
        sugerencias); `incremento_vs_ticket_promedio_cliente`/`probabilidad_recompra`
        reutilizan el perfil de cliente de la Fase 1 (CLV histórico + churn_rf), sin
        cálculo nuevo. No incluye "probabilidad de cierre" ni "probabilidad de compra
        por producto" -- el ranker de la Fase 2 no fue promovido (docs/auditoria/
        40_refactor_venta_cruzada.md) y el EDW no tiene ventas perdidas (§2.2 del plan).
        `items` vacío ya lo rechaza `SimulacionVentaRequest` (`Field(min_length=1)`,
        422) antes de llegar aquí -- no se revalida."""
        if cliente_id:
            self._verificar_pertenencia_cartera(cliente_id, codven_restriccion)

        info_productos = self.catalog_repo.get_products_info(items)
        encontrados = [info_productos[cod] for cod in items if cod in info_productos]
        no_encontrados = [cod for cod in items if cod not in info_productos]

        ticket_estimado = round(sum(p["precio"] for p in encontrados), 2)
        margenes = [p["margen_unitario"] for p in encontrados]
        margen_estimado = round(sum(margenes), 2) if encontrados and all(m is not None for m in margenes) else None

        incremento = None
        probabilidad_recompra = None
        frases_cliente: list[str] = []
        if cliente_id:
            perfil = self.cartera360_repo.get_perfil_cliente(cliente_id)
            if perfil and perfil.get("ticket_promedio"):
                incremento = round(ticket_estimado - perfil["ticket_promedio"], 2)
                if incremento >= 0:
                    frases_cliente.append(f"${incremento:.2f} por encima de su ticket promedio histórico")
                else:
                    frases_cliente.append(f"${abs(incremento):.2f} por debajo de su ticket promedio histórico")
            churn = self.prediction_service.get_churn_risk(cliente_id, codven_restriccion=None)
            probabilidad_recompra = round(100 - churn["probabilidad_abandono"], 2)
            frases_cliente.append(f"{probabilidad_recompra:.0f}% de probabilidad de recompra (churn_rf)")

        frases = [f"Esta canasta de {len(items)} producto(s) suma ${ticket_estimado:.2f}"]
        if margen_estimado is not None:
            frases.append(f"con ${margen_estimado:.2f} de margen bruto estimado")
        else:
            frases.append("margen no disponible para uno o más productos de la canasta")
        explicacion = ", ".join(frases[:1]) + " " + frases[1] + "."
        if frases_cliente:
            explicacion += " Para este cliente: " + " y ".join(frases_cliente) + "."
        if no_encontrados:
            explicacion += f" {len(no_encontrados)} código(s) no se encontraron en el catálogo vigente."

        return {
            "ticket_estimado": ticket_estimado,
            "productos_no_encontrados": no_encontrados,
            "margen_estimado": margen_estimado,
            "incremento_vs_ticket_promedio_cliente": incremento,
            "probabilidad_recompra": probabilidad_recompra,
            "explicacion": explicacion,
        }

    @staticmethod
    def _margen_agregado(productos: list[dict[str, Any]]) -> float | None:
        margenes = [p["margen_unitario"] for p in productos]
        return round(sum(margenes), 2) if productos and all(m is not None for m in margenes) else None

    def get_combos(self, cliente_id: str | None, codven_restriccion: str | None = None) -> list[dict[str, Any]]:
        """Fase 4 (CAMBIO 5/6 del plan): 4 estrategias declaradas, cada una sobre datos
        reales del EDW -- "Ideal para Flotas" queda fuera (decisión de negocio §8.4 del
        plan: sin definición de "cliente de flota/corporativo" derivable del EDW hoy).
        Un combo sin datos suficientes para su estrategia no se emite."""
        if cliente_id:
            self._verificar_pertenencia_cartera(cliente_id, codven_restriccion)

        combos: list[dict[str, Any]] = []

        # 1. Oferta Estrella: mayor afinidad histórica REAL (coocurrencia en facturas,
        # ya calculada por get_top_combinaciones -- RN de Fase 3 del cross-selling
        # original, sin telemetría). `afinidad` = facturas conjuntas reales (no un
        # score normalizado inventado).
        top_pares = self.catalog_repo.get_top_combinaciones(limit=1)
        if top_pares:
            par = top_pares[0]
            info = self.catalog_repo.get_products_info([par["codart_a"], par["codart_b"]])
            productos = [info[c] for c in (par["codart_a"], par["codart_b"]) if c in info]
            if len(productos) == 2:
                combos.append({
                    "nombre": "Oferta Estrella", "estrategia": "mayor_afinidad_historica",
                    "productos": productos, "margen_esperado": self._margen_agregado(productos),
                    "afinidad": float(par["facturas"]), "popularidad": None,
                    "porque": (
                        f"{par['nombre_a']} y {par['nombre_b']} se compraron juntos en "
                        f"{par['facturas']} facturas de los últimos 2 años -- la combinación "
                        f"más frecuente del catálogo."
                    ),
                })

        # 2. Mayor Rentabilidad: mayor margen relativo real, diversificado por categoría.
        top_margen = self.catalog_repo.get_top_margen_relativo(limit=4)
        if top_margen:
            combos.append({
                "nombre": "Mayor Rentabilidad", "estrategia": "mayor_margen_relativo",
                "productos": top_margen, "margen_esperado": self._margen_agregado(top_margen),
                "afinidad": None, "popularidad": None,
                "porque": "Los productos con mejor margen relativo del catálogo vigente, uno por categoría distinta.",
            })

        # 3. Cliente Frecuente: reincidencia histórica REAL del propio cliente (solo si
        # hay cliente y tiene historial -- sin cliente no hay "frecuente" que ofrecer).
        if cliente_id:
            favoritos = self.cartera360_repo.get_productos_favoritos_cliente(cliente_id, limit=4)
            if favoritos:
                info = self.catalog_repo.get_products_info([f["codart"] for f in favoritos])
                productos = [info[f["codart"]] for f in favoritos if f["codart"] in info]
                if productos:
                    perfil = self.cartera360_repo.get_perfil_cliente(cliente_id)
                    venta_favoritos = sum(f["venta_acumulada"] for f in favoritos)
                    # popularidad = % real del gasto histórico del cliente que representan
                    # estos productos -- "share of wallet", no un score inventado.
                    popularidad = (
                        round(100 * venta_favoritos / perfil["valor_historico"], 1)
                        if perfil and perfil.get("valor_historico") else None
                    )
                    combos.append({
                        "nombre": "Cliente Frecuente", "estrategia": "reincidencia_cliente",
                        "productos": productos, "margen_esperado": self._margen_agregado(productos),
                        "afinidad": None, "popularidad": popularidad,
                        "porque": "Los productos que este cliente ya compra con más frecuencia, según su propio historial.",
                    })

        # 4. Protección Total: complementarios de categoría DISTINTA -- diversidad real
        # (mismo motor que RN-CS3), sin contexto de canasta específico (no hay canasta
        # aquí, solo top-1 por categoría de mayor venta general).
        diversos = self.catalog_repo.get_top_productos_diversos(categorias_excluir=[], excluir_codarts=[], limit=4)
        if diversos:
            info = self.catalog_repo.get_products_info([d["codart"] for d in diversos])
            productos = [info[d["codart"]] for d in diversos if d["codart"] in info]
            if productos:
                combos.append({
                    "nombre": "Protección Total", "estrategia": "diversidad_categorias",
                    "productos": productos, "margen_esperado": self._margen_agregado(productos),
                    "afinidad": None, "popularidad": None,
                    "porque": "Productos de categorías distintas y de alta venta, para cubrir necesidades complementarias del cliente.",
                })

        return combos
