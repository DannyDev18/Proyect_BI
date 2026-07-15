# backend/app/services/commission_bonus.py
"""Bonos complementarios del esquema de Comisiones Variables (§3.4 del plan: venta
cruzada aceptada, cliente nuevo/reactivado, cobranza sana). Extraído de
`CommissionService` (docs/auditoria/35_actualizacion_modulo_metas.md, H3) para que
`CommissionSimulationService` use exactamente el mismo cálculo -- antes la simulación
siempre pasaba `bonos_total=0.0` y subestimaba el costo real del esquema variable
frente a lo que realmente se liquida. El bono 4 (visitas) queda diferido -- brecha B3
(sin geolocalización en el EDW, auditoría 30)."""
from __future__ import annotations

from app.core.config import settings
from app.repositories.goal_repository import GoalRepository


def calcular_bonos_periodo(
    goal_repo: GoalRepository, vendedor_origen: str, anio: int, mes: int, comision_pre_bonos: float,
) -> float:
    bono_cross_sell = (
        goal_repo.get_cross_sell_accepted_amount(vendedor_origen, anio, mes)
        * (settings.COMISION_BONO_CROSS_SELL_PCT / 100.0)
    )
    clientes_nuevos = goal_repo.get_new_or_reactivated_clients(
        vendedor_origen, anio, mes, settings.COMISION_MESES_CLIENTE_REACTIVADO,
    )
    bono_cliente_nuevo = clientes_nuevos * settings.COMISION_BONO_CLIENTE_NUEVO

    perfil_credito = goal_repo.get_vendor_credit_profile(vendedor_origen, anio, mes)
    dias_cobro = perfil_credito.get("dias_cobro_promedio")
    bono_cobranza = 0.0
    if dias_cobro is not None and dias_cobro < settings.COMISION_BONO_COBRANZA_DIAS:
        bono_cobranza = max(0.0, comision_pre_bonos) * (settings.COMISION_BONO_COBRANZA_PCT / 100.0)

    return round(bono_cross_sell + bono_cliente_nuevo + bono_cobranza, 4)
