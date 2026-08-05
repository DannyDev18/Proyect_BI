# backend/app/services/commission_bonus.py
"""Bonos complementarios del esquema de Comisiones Variables (§3.4 del plan: venta
cruzada aceptada, cliente nuevo/reactivado, cobranza sana). Extraído de
`CommissionService` (docs/auditoria/35_actualizacion_modulo_metas.md, H3) para que
`CommissionSimulationService` use exactamente el mismo cálculo -- antes la simulación
siempre pasaba `bonos_total=0.0` y subestimaba el costo real del esquema variable
frente a lo que realmente se liquida. El bono 4 (visitas) queda diferido -- brecha B3
(sin geolocalización en el EDW, auditoría 30).

Techo relativo (docs/features/plan_motor_metas_v3_y_comisiones_unificadas.md, Fase 2,
R-6, auditoría 47): sin techo, el bono de cliente nuevo/reactivado puede superar en
varias veces la base real que un vendedor generó (caso real VEN01/julio-2026: bonos
$25.444,91 vs. base $665,52, 97.4% de la comisión final) -- un mostrador con alta
rotación de compradores ocasionales no está "captando cartera" al ritmo que el bono
asume. `COMISION_BONO_TOPE_PCT_SOBRE_BASE` acota la SUMA de los 3 bonos como
porcentaje de `comision_pre_bonos` (la base ya afectada por tipo de vendedor y
cumplimiento -- el mismo punto de referencia que ya usaba el bono de cobranza sana),
nunca un bono individual por separado: es la combinación la que debe ser proporcional
al desempeño real, no cada bono aislado."""
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

    bonos_total = bono_cross_sell + bono_cliente_nuevo + bono_cobranza

    # Techo relativo (R-6): sin base positiva (comision_pre_bonos <= 0) no hay
    # referencia contra la cual acotar -- se deja el bono tal cual en vez de anularlo
    # por completo, para no castigar a un vendedor cuya base es 0 solo por redondeo o
    # por depender enteramente de cobranza sin líneas de venta ese mes.
    if comision_pre_bonos > 0:
        tope = comision_pre_bonos * (settings.COMISION_BONO_TOPE_PCT_SOBRE_BASE / 100.0)
        bonos_total = min(bonos_total, tope)

    return round(bonos_total, 4)
