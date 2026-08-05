# backend/app/inventory/service.py
"""Servicio de Reabastecimiento Inteligente (docs/features/plan_reabastecimiento_
inteligente.md §6.4, auditoría docs/auditoria/50_reabastecimiento_inteligente.md).

Conecta datos crudos del EDW (`WarehouseRepository.get_metricas_reabastecimiento`) +
configuración editable (`ReplenishmentConfigRepository`) con el motor puro
(`replenishment_engine`). No reemplaza `WarehouseService` (que sigue sirviendo
`/necesidad-compra` con la fórmula determinista, Fase 3 del plan: ambos motores
conviven -- A-0.7 de la auditoría 50 confirmó que el cambio de fórmula altera el
estado de más de la mitad del catálogo evaluado, una decisión de política de negocio
que gerencia debe ver antes de que sea la predeterminada).

Conversión mensual -> diaria: el repositorio agrega salidas por MES (mismo grano que
`meses_con_venta`, alineado con `MESES_MINIMOS_ESTOCASTICO` del motor puro, que decide
la degradación de método según cuántos MESES de historia hay, no cuántos días). El
motor puro trabaja en unidades diarias (la fórmula clásica `SS = z·σ·√LT` asume σ de
demanda diaria y LT en días) -- se convierte con un promedio de 30.44 días/mes (365.25/12,
constante calendario real, no una aproximación arbitraria de "30")."""
from __future__ import annotations

import statistics
from dataclasses import asdict
from typing import Any

from app.core.config import settings
from app.core.exceptions import NotFoundError, ValidationError
from app.inventory import engine
from app.inventory.proposals import ReplenishmentProposalRepository
from app.inventory.repository import ReplenishmentConfigRepository
from app.repositories.warehouse_repository import WarehouseRepository

DIAS_POR_MES = 365.25 / 12  # 30.4375 -- constante calendario real, no un redondeo a 30.

# F9 (§8 del plan): máquina de estados de una propuesta -- solo estas 2 transiciones
# reales, cualquier otra (incluida re-decidir una ya decidida) se rechaza explícitamente.
_TRANSICIONES_PROPUESTA = {"aprobar": "aprobada", "rechazar": "rechazada"}


class ReplenishmentService:
    def __init__(
        self, warehouse_repo: WarehouseRepository, config_repo: ReplenishmentConfigRepository,
        proposal_repo: ReplenishmentProposalRepository,
    ):
        self.warehouse_repo = warehouse_repo
        self.config_repo = config_repo
        self.proposal_repo = proposal_repo
        # D-6 (auditoría 52, Fase 4 de docs/features/plan_modulo_inventario_
        # reabastecimiento.md): memoización de la evaluación completa del catálogo
        # (~8.153 artículos) por request -- `resumen`+`alertas`+`simular` la llamaban
        # hasta 4 veces por request real (medido: 1,64s). Segura sin incluir la RLS por
        # almacén (RN-B10) en la clave porque el propio `warehouse_repo` ya la trae
        # inyectada (`almacenes_permitidos`) y `ReplenishmentService` se construye una
        # instancia nueva por request vía `Depends` -- el caché nunca sobrevive entre
        # usuarios ni entre requests.
        self._cache_catalogo: dict[tuple, list[dict[str, Any]]] = {}

    def _resolver_lead_time_por_codart(
        self, codart: str, categoria: str, resolucion: dict[str, dict[str, float]], lead_time_default: float,
    ) -> engine.ResultadoLeadTime:
        return engine.resolver_lead_time(
            lead_time_producto=resolucion["producto"].get(codart),
            lead_time_categoria=resolucion["categoria"].get(categoria),
            lead_time_proveedor=None,  # el catálogo actual no trae "el" proveedor de un producto (N:M vía compras)
            lead_time_default=lead_time_default,
        )

    def get_lista_reabastecimiento(
        self, sucursal: str | None = None, almacen: str | None = None,
        categoria: str | None = None, proveedor: str | None = None,
        tipo_movimiento: str | None = None, horizonte_dias: float | None = None,
        solo_criticos: bool = False, riesgo: str | None = None,
        clase_abc: str | None = None, clase_xyz: str | None = None,
        niveles_servicio_override: dict[str, float] | None = None,
        lead_time_default_override: float | None = None,
    ) -> list[dict[str, Any]]:
        """Lista priorizada completa (sin paginar -- el llamador pagina). La evaluación
        cara del catálogo (~8.153 artículos) vive en `_evaluar_catalogo` (memoizada);
        aquí solo se aplican los post-filtros (`solo_criticos`/`riesgo`/`clase_abc`/
        `clase_xyz`, baratos, no cambian el resultado de la evaluación) y el orden."""
        filas_catalogo = self._evaluar_catalogo(
            sucursal=sucursal, almacen=almacen, categoria=categoria,
            proveedor=proveedor, tipo_movimiento=tipo_movimiento,
            horizonte_dias=horizonte_dias,
            niveles_servicio_override=niveles_servicio_override,
            lead_time_default_override=lead_time_default_override,
        )
        # Copia antes de filtrar/ordenar -- `_evaluar_catalogo` puede devolver la MISMA
        # lista cacheada a otro llamador con filtros distintos; nunca se muta en sitio.
        filas = list(filas_catalogo)

        if solo_criticos:
            filas = [f for f in filas if f["riesgo"] == "critico"]
        if riesgo:
            filas = [f for f in filas if f["riesgo"] == riesgo]
        if clase_abc:
            filas = [f for f in filas if f["clase_abc"] == clase_abc]
        if clase_xyz:
            filas = [f for f in filas if f["clase_xyz"] == clase_xyz]

        filas.sort(key=lambda f: f["prioridad_score"])
        return filas

    def _evaluar_catalogo(
        self, sucursal: str | None, almacen: str | None,
        categoria: str | None, proveedor: str | None, tipo_movimiento: str | None,
        horizonte_dias: float | None,
        niveles_servicio_override: dict[str, float] | None,
        lead_time_default_override: float | None,
    ) -> list[dict[str, Any]]:
        """Evalúa el catálogo completo (sin post-filtros de riesgo/ABC/XYZ, sin orden) --
        el cálculo caro que `get_resumen`/`get_alertas`/`get_explicacion`/`simular`
        terminaban repitiendo hasta 4 veces por request real (D-6, auditoría 52).
        Memoizado por la combinación de filtros de alcance + overrides del simulador
        (F8) -- exactamente los parámetros que cambian el resultado. Cada fila es el
        `DesgloseRecomendacion` del motor, aplanado a dict, más el nombre/categoría para
        la tabla. Ningún campo se calcula fuera del motor puro salvo la clasificación
        ABC (que necesita el catálogo completo en memoria para la curva de Pareto -- el
        motor la recibe ya resuelta)."""
        clave_cache = (
            sucursal, almacen, categoria, proveedor, tipo_movimiento, horizonte_dias,
            tuple(sorted((niveles_servicio_override or {}).items())),
            lead_time_default_override,
        )
        if clave_cache in self._cache_catalogo:
            return self._cache_catalogo[clave_cache]

        horizonte = horizonte_dias or settings.BODEGA_HORIZONTE_COMPRA_DIAS
        lead_time_default = (
            lead_time_default_override if lead_time_default_override is not None else settings.BODEGA_LEAD_TIME_DIAS
        )
        productos = self.warehouse_repo.get_metricas_reabastecimiento(
            sucursal=sucursal, almacen=almacen, categoria=categoria,
            proveedor=proveedor, tipo_movimiento=tipo_movimiento,
        )
        if not productos:
            self._cache_catalogo[clave_cache] = []
            return []

        # ── ABC: curva de Pareto real sobre TODO el catálogo filtrado (auditoría 50
        # A-0.3: cortes 80/95 sobre valor de consumo, no sobre unidades). ────────────
        ordenados = sorted(productos, key=lambda p: p["valor_consumo"], reverse=True)
        valor_total = sum(p["valor_consumo"] for p in ordenados)
        acumulado = 0.0
        clase_abc_por_codart: dict[str, engine.ClaseABC] = {}
        for p in ordenados:
            acumulado += p["valor_consumo"]
            clase_abc_por_codart[p["codart"]] = engine.clasificar_abc(p["valor_consumo"], acumulado, valor_total)

        niveles_servicio = niveles_servicio_override or self.config_repo.get_niveles_servicio()
        resolucion_lt = self.config_repo.get_lead_times_resolucion()

        filas: list[dict[str, Any]] = []
        for p in productos:
            clase_a = clase_abc_por_codart.get(p["codart"], "C")

            # ── Demanda mensual -> estadística -> conversión a diaria ──────────────
            stat_mensual = engine.estadistica_demanda(p["unidades_mensuales"], p["meses_con_venta"])
            cv = engine.coeficiente_variacion(stat_mensual.media_diaria, stat_mensual.sigma_diaria, stat_mensual.meses_con_venta)
            clase_x = engine.clasificar_xyz(cv)
            stat_diaria = engine.EstadisticaDemanda(
                media_diaria=round(stat_mensual.media_diaria / DIAS_POR_MES, 4),
                sigma_diaria=round(stat_mensual.sigma_diaria / (DIAS_POR_MES ** 0.5), 4),
                meses_con_venta=stat_mensual.meses_con_venta,
                metodo=stat_mensual.metodo,
            )
            metodo_demanda: engine.MetodoDemanda = (
                "sin_historia" if stat_diaria.metodo == "sin_historia" else "estadistico"
            )  # F6 del plan conecta demand_rf aquí; por ahora, siempre estadístico (honesto).

            lt = self._resolver_lead_time_por_codart(p["codart"], p["categoria"], resolucion_lt, lead_time_default)
            nivel_servicio = niveles_servicio.get(clase_a, engine.NIVEL_SERVICIO_DEFAULT_POR_ABC[clase_a])
            ss = engine.stock_seguridad(stat_diaria, lt.dias, nivel_servicio, settings.BODEGA_STOCK_SEGURIDAD_DIAS)
            rop = engine.punto_reorden(stat_diaria, lt.dias, ss)
            cantidad = engine.cantidad_sugerida(p["stock_actual"], stat_diaria.media_diaria, rop, horizonte)

            desglose = engine.construir_desglose(
                codart=p["codart"], clase_abc=clase_a, clase_xyz=clase_x,
                stat=stat_diaria, cv=cv, metodo_demanda=metodo_demanda,
                lt=lt, nivel_servicio=nivel_servicio, ss=ss, rop=rop,
                stock_actual=p["stock_actual"], cantidad=cantidad,
            )
            prioridad = engine.calcular_prioridad(
                desglose.riesgo, clase_a,
                dias_hasta_quiebre=(desglose.cobertura_dias if desglose.cobertura_dias is not None else None),
            )
            fila = asdict(desglose)
            fila.update({
                "nombre": p["nombre"],
                "costo_unitario": p["costo_unitario"],
                "costo_total_sugerido": round(cantidad * p["costo_unitario"], 2),
                "prioridad_score": prioridad,
                # Campos internos (prefijo `_`, ignorados por `ItemReabastecimiento` --
                # Pydantic v2 descarta claves extra por defecto): insumo de `get_alertas`
                # para no repetir la consulta ni el cálculo de estadística mensual.
                "_unidades_mensuales": p["unidades_mensuales"],
                "_media_mensual": stat_mensual.media_diaria,
                "_sigma_mensual": stat_mensual.sigma_diaria,
            })
            filas.append(fila)

        self._cache_catalogo[clave_cache] = filas
        return filas

    def get_explicacion(self, codart: str, **filtros: Any) -> dict[str, Any]:
        """Bloque 3 (Explicabilidad, §6.4): `GET /lista/{codart}/explicacion`. Reutiliza
        `get_lista_reabastecimiento` sin post-filtros de riesgo/ABC/XYZ (`solo_criticos`/
        `riesgo`/`clase_abc`/`clase_xyz` no se propagan aquí a propósito) porque la
        clasificación ABC de un artículo depende de la curva de Pareto de TODO el
        catálogo filtrado por almacén/categoría/proveedor -- calcularla en aislamiento
        para un solo `codart` daría una clase distinta a la que ese mismo artículo tiene
        en la lista, rompiendo la invariante de que la lista y el detalle cuentan la
        misma historia. Filtros de alcance (almacén/categoría/proveedor/tipo_movimiento/
        horizonte_dias) sí se respetan -- son los mismos que la RLS y la vista actual
        del usuario."""
        filtros_alcance = {
            k: v for k, v in filtros.items()
            if k in {"sucursal", "almacen", "categoria", "proveedor", "tipo_movimiento", "horizonte_dias"}
        }
        filas = self.get_lista_reabastecimiento(**filtros_alcance)
        for fila in filas:
            if fila["codart"] == codart:
                return fila
        raise NotFoundError(f"No se encontró el artículo '{codart}' en el alcance de filtros actual.")

    def get_resumen(self, **filtros: Any) -> dict[str, Any]:
        """Centro de Decisiones (bloque 1 del plan): KPIs de decisión, no de censo."""
        filas = self.get_lista_reabastecimiento(**filtros)
        criticos = [f for f in filas if f["riesgo"] == "critico"]
        altos = [f for f in filas if f["riesgo"] == "alto"]
        con_recomendacion = [f for f in filas if f["cantidad_sugerida"] > 0]
        costo_total = round(sum(f["costo_total_sugerido"] for f in con_recomendacion), 2)
        coberturas = [f["cobertura_dias"] for f in filas if f["cobertura_dias"] is not None]
        return {
            "total_articulos_evaluados": len(filas),
            "productos_riesgo_critico": len(criticos),
            "productos_riesgo_alto": len(altos),
            "productos_con_recomendacion_compra": len(con_recomendacion),
            "costo_total_compra_sugerida": costo_total,
            "cobertura_mediana_dias": round(statistics.median(coberturas), 1) if coberturas else None,
            "cobertura_promedio_dias": round(statistics.mean(coberturas), 1) if coberturas else None,
        }

    def get_alertas(self, limite_por_tipo: int = 20, **filtros: Any) -> list[dict[str, Any]]:
        """F7 (§7.4 del plan): alertas tipadas con acción sugerida y deep-link,
        **extendiendo** el generador ya existente de Bodega (`WarehouseService.
        get_notificaciones`), no duplicándolo -- solo cubre las 2 señales que ese
        generador nunca calculó (cambio brusco de demanda, tendencia sostenida a la
        baja). La alerta de "riesgo de quiebre" (🔴 del plan) NO se repite aquí: es el
        mismo evento real que `stock_critico`/`prediccion_agotamiento` de Bodega, solo
        calculado con una fórmula más precisa (stock de seguridad vs. umbral fijo) --
        mostrar ambas en la misma campana por el mismo artículo confundiría al usuario
        sin agregar información nueva; ese riesgo ya es visible en el Centro de
        Decisiones y la Lista Inteligente de este mismo módulo. El sobrestock (🟠)
        tampoco se repite -- ya lo cubren las alertas de "Inmovilizado"/"Exceso" del
        estado de stock existente (auditoría 42, Fase 6.1)."""
        filas = self.get_lista_reabastecimiento(**filtros)

        cambios_bruscos: list[dict[str, Any]] = []
        tendencias: list[dict[str, Any]] = []
        for f in filas:
            unidades = f.get("_unidades_mensuales") or []
            if not unidades:
                continue
            ultimo_mes = unidades[-1]
            if engine.detectar_cambio_brusco(
                ultimo_mes, f["_media_mensual"], f["_sigma_mensual"], meses_con_venta=len(unidades),
            ):
                direccion = "por encima" if ultimo_mes > f["_media_mensual"] else "por debajo"
                cambios_bruscos.append({
                    "tipo": "cambio_brusco_demanda", "severidad": "media",
                    "codart": f["codart"], "nombre": f["nombre"],
                    "mensaje": (
                        f"Demanda del último mes ({ultimo_mes:.1f} uds) {direccion} de lo habitual "
                        f"(media {f['_media_mensual']:.1f} uds/mes) -- fuera de ±2 desviaciones estándar."
                    ),
                    "accion_url": f"/bodega/reabastecimiento?codart={f['codart']}",
                })
            if engine.detectar_tendencia_decreciente(unidades):
                tendencias.append({
                    "tipo": "tendencia_decreciente", "severidad": "baja",
                    "codart": f["codart"], "nombre": f["nombre"],
                    "mensaje": f"Demanda en caída sostenida los últimos 3 meses -- revisar política antes de comprar.",
                    "accion_url": f"/bodega/reabastecimiento?codart={f['codart']}",
                })

        return cambios_bruscos[:limite_por_tipo] + tendencias[:limite_por_tipo]

    def simular(
        self, niveles_servicio: dict[str, float] | None = None,
        lead_time_default_dias: float | None = None, **filtros: Any,
    ) -> dict[str, Any]:
        """F8 (§6.4/§7.1 del plan, bloque 4 Simulación): recalcula el resumen bajo
        parámetros hipotéticos de política **sin persistir nada** -- nunca escribe en
        `reabastecimiento_politica`/`reabastecimiento_lead_time`, solo pasa los overrides
        a `get_lista_reabastecimiento` para esta llamada. Devuelve el resumen actual
        (configuración real vigente) junto al simulado, para que la UI compare
        directamente el efecto de la política hipotética."""
        resumen_actual = self.get_resumen(**filtros)
        resumen_simulado = self.get_resumen(
            niveles_servicio_override=niveles_servicio,
            lead_time_default_override=lead_time_default_dias,
            **filtros,
        )
        return {
            "resumen_actual": resumen_actual,
            "resumen_simulado": resumen_simulado,
            "parametros_simulados": {
                "niveles_servicio": niveles_servicio,
                "lead_time_default_dias": lead_time_default_dias,
            },
        }

    # ── F9 (§6.3/§8, bloque 5 Gestión Operativa): propuestas de compra persistidas ────
    def crear_propuesta(self, usuario_id: int | None, **filtros: Any) -> Any:
        """Recalcula la lista con los filtros dados y persiste un SNAPSHOT de las
        líneas con `cantidad_sugerida > 0` -- congelado desde este momento (mismo
        criterio que `comision_liquidaciones`): aprobar/rechazar más tarde es sobre lo
        que se vio al generar la propuesta, no sobre un recálculo con datos que
        cambiaron mientras tanto."""
        filas = self.get_lista_reabastecimiento(**filtros)
        con_recomendacion = [f for f in filas if f["cantidad_sugerida"] > 0]
        horizonte = filtros.get("horizonte_dias") or settings.BODEGA_HORIZONTE_COMPRA_DIAS
        lineas = [
            {
                "codart": f["codart"], "nombre": f["nombre"], "cantidad": f["cantidad_sugerida"],
                "costo_unitario": f["costo_unitario"], "costo_total": f["costo_total_sugerido"],
                "justificacion": {
                    "clase_abc": f["clase_abc"], "clase_xyz": f["clase_xyz"], "riesgo": f["riesgo"],
                    "cobertura_dias": f["cobertura_dias"], "punto_reorden": f["punto_reorden"],
                    "lead_time_dias": f["lead_time_dias"], "lead_time_origen": f["lead_time_origen"],
                    "razones": f["razones"],
                },
            }
            for f in con_recomendacion
        ]
        filtros_origen = {
            k: v for k, v in filtros.items()
            if k in {"almacen", "categoria", "proveedor", "tipo_movimiento"} and v is not None
        }
        return self.proposal_repo.crear(usuario_id, filtros_origen, horizonte, lineas)

    def listar_propuestas(self) -> list[Any]:
        return self.proposal_repo.listar()

    def get_propuesta(self, propuesta_id: int) -> Any:
        propuesta = self.proposal_repo.get(propuesta_id)
        if propuesta is None:
            raise NotFoundError(f"Propuesta de compra no encontrada: id={propuesta_id}")
        return propuesta

    def decidir_propuesta(self, propuesta_id: int, accion: str) -> Any:
        """`accion` es `aprobar`/`rechazar` -- solo transiciona desde `borrador`
        (RN-RB7): una propuesta ya aprobada o rechazada no se puede volver a decidir,
        para que el estado persistido siga siendo la decisión real tomada una vez."""
        if accion not in _TRANSICIONES_PROPUESTA:
            raise ValidationError(f"Acción de decisión inválida: {accion}")
        propuesta = self.get_propuesta(propuesta_id)
        if propuesta.estado != "borrador":
            raise ValidationError(
                f"La propuesta {propuesta_id} ya fue decidida (estado actual: {propuesta.estado}) -- no se puede volver a decidir.",
            )
        actualizada = self.proposal_repo.actualizar_estado(propuesta_id, _TRANSICIONES_PROPUESTA[accion])
        assert actualizada is not None  # ya se validó que existe arriba
        return actualizada
