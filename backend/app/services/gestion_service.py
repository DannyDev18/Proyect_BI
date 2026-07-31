# backend/app/services/gestion_service.py
"""Servicio de escritura/trazabilidad de "Mi Ruta Inteligente de Ventas"
(docs/features/plan_refactor_cartera360_ruta_inteligente.md §2.1, §13): separa
escritura de gestión + timeline + efectividad de `Cartera360Service` (que queda
enfocado en lectura/priorización). Mismo patrón de composición que
`CrossSellEngineService` -- no reentrena ni duplica inferencia, solo orquesta
repositorios y valida RLS."""
import datetime
import logging
from typing import Any

from app.core.config import settings
from app.core.exceptions import PermissionDeniedError, ValidationError
from app.models.gestion_cartera_evento import CANALES_VALIDOS, EVENTOS_VALIDOS
from app.repositories.catalog_repository import CatalogRepository
from app.repositories.cartera360_repository import Cartera360Repository

logger = logging.getLogger("Backend.GestionService")


class GestionService:
    def __init__(self, cartera360_repo: Cartera360Repository, catalog_repo: CatalogRepository):
        self.cartera360_repo = cartera360_repo
        self.catalog_repo = catalog_repo

    def _verificar_pertenencia_cartera(self, cliente_id: str, codven_restriccion: str | None) -> None:
        """Mismo criterio de RLS que el resto del módulo (H-V2, auditoría 34) -- riesgo
        R-3 del plan: obligatorio en todo endpoint nuevo por-cliente, sin excepción."""
        if codven_restriccion is None:
            return
        if not self.catalog_repo.cliente_pertenece_a_vendedor(cliente_id, codven_restriccion):
            raise PermissionDeniedError(
                f"El cliente '{cliente_id}' no pertenece a la cartera del vendedor autenticado."
            )

    def registrar_gestion(
        self, usuario_id: int, cliente_id: str, evento: str, codven_restriccion: str | None,
        canal: str | None = None, resultado: str | None = None,
        proxima_accion_fecha: str | None = None, nota: str | None = None,
    ) -> dict[str, Any]:
        self._verificar_pertenencia_cartera(cliente_id, codven_restriccion)
        if evento not in EVENTOS_VALIDOS:
            raise ValidationError(f"Evento de gestión inválido: '{evento}'.")
        if canal is not None and canal not in CANALES_VALIDOS:
            raise ValidationError(f"Canal de gestión inválido: '{canal}'.")

        fecha_parseada: datetime.date | None = None
        if proxima_accion_fecha:
            try:
                fecha_parseada = datetime.date.fromisoformat(proxima_accion_fecha)
            except ValueError as e:
                raise ValidationError(f"proxima_accion_fecha inválida (esperado YYYY-MM-DD): {e}") from e

        cliente_sk = self.catalog_repo.get_cliente_sk_vigente(cliente_id)
        registro = self.cartera360_repo.log_gestion(
            usuario_id=usuario_id, cliente_sk=cliente_sk, evento=evento, motivo=nota,
            canal=canal, resultado=resultado, proxima_accion_fecha=fecha_parseada, nota=nota,
        )
        return {
            "id": registro.id, "evento": registro.evento, "canal": registro.canal,
            "fecha": registro.fecha.isoformat(),
        }

    def get_timeline_cliente(self, cliente_id: str, codven_restriccion: str | None) -> dict[str, Any]:
        """Timeline real (§4.6): eventos EDW reales + gestiones registradas. Poblado
        desde el día 1 aunque `gestion_cartera_eventos` esté vacía (D-1) -- las compras,
        devoluciones y cobros reales del cliente ya existen en el EDW."""
        self._verificar_pertenencia_cartera(cliente_id, codven_restriccion)
        cliente_sk = self.catalog_repo.get_cliente_sk_vigente(cliente_id)
        eventos = self.cartera360_repo.get_timeline_cliente(cliente_id, cliente_sk)
        return {"cliente_id": cliente_id, "eventos": eventos}

    def get_efectividad_comercial(self, usuario_id: int | None) -> dict[str, Any]:
        """Efectividad Comercial (§4.8), reemplaza "Tasa de recuperación". Con menos de
        `CARTERA360_MIN_GESTIONES_EFECTIVIDAD` gestiones, el panel declara
        `tiene_datos=False` -- estado vacío real (RN-CS5), nunca una tasa calculada
        sobre una muestra insuficiente presentada como si fuera confiable."""
        datos = self.cartera360_repo.get_efectividad_gestiones(usuario_id)
        tiene_datos = datos["total_gestiones"] >= settings.CARTERA360_MIN_GESTIONES_EFECTIVIDAD
        return {
            "tiene_datos": tiene_datos,
            "total_gestiones": datos["total_gestiones"],
            "total_ventas_atribuidas": datos["total_ventas_atribuidas"] if tiene_datos else 0,
            "conversion_pct": datos["conversion_pct"] if tiene_datos else None,
            "tiempo_promedio_cierre_dias": datos["tiempo_promedio_cierre_dias"] if tiene_datos else None,
            "ingresos_atribuidos": None,  # sin fuente real de "venta atribuible en $" -- ver R-0, motivo documentado en el plan §4.8
            "por_canal": datos["por_canal"] if tiene_datos else [],
        }

    def get_proximas_acciones(self, codven: str) -> dict[str, Any]:
        """Auditoría 43 (H43-13): agenda propia del vendedor, fuera del top-N de
        `/ruta/hoy` -- ver `Cartera360Repository.get_proximas_acciones_por_vendedor` para
        el porqué de la separación. `estado` se deriva aquí (capa de servicio, no SQL)
        comparando contra la fecha de hoy: `vencida` (ya pasó y sigue sin gestionarse),
        `hoy`, o `proxima`."""
        hoy = datetime.date.today().isoformat()
        filas = self.cartera360_repo.get_proximas_acciones_por_vendedor(codven)
        acciones = []
        for f in filas:
            fecha = f["proxima_accion_fecha"]
            estado = "vencida" if fecha < hoy else ("hoy" if fecha == hoy else "proxima")
            acciones.append({**f, "estado": estado})
        return {"acciones": acciones}

    def get_plan_semanal(self, ruta_clientes: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Planificador semanal (§4.9): regla determinista de reparto, no una
        optimización aprendida -- se etiqueta como "plan sugerido" en la UI. Reparte
        los clientes YA priorizados de la ruta del día (mismo orden, sin recalcular)
        en cupos configurables lunes-viernes."""
        cupos = [
            ("lunes", settings.CARTERA360_PLAN_CUPO_LUNES),
            ("martes", settings.CARTERA360_PLAN_CUPO_MARTES),
            ("miercoles", settings.CARTERA360_PLAN_CUPO_MIERCOLES),
            ("jueves", settings.CARTERA360_PLAN_CUPO_JUEVES),
            ("viernes", settings.CARTERA360_PLAN_CUPO_VIERNES),
        ]
        plan = []
        cursor = 0
        for dia, cupo in cupos:
            asignados = ruta_clientes[cursor:cursor + cupo]
            plan.append({"dia": dia, "cupo": cupo, "clientes": [c["cliente_id"] for c in asignados]})
            cursor += cupo
        return plan
