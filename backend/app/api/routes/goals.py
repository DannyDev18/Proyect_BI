# backend/app/api/routes/goals.py
import datetime

from fastapi import APIRouter, Depends, status

from app.api.dependencies import (
    AnalyticsServiceDep, CommissionConfigServiceDep, CommissionServiceDep, CommissionSimulationServiceDep,
    GoalMLServiceDep, GoalsServiceDep, resolve_sucursal_filter,
)
from app.core.deps import CurrentUserDep, PermissionChecker
from app.schemas.commission import (
    CommissionTrackingResponse, CumplimientoMetaPeriodoResponse, VendorCommissionRowResponse,
)
from app.schemas.commission_config import (
    ClaseBusqueda, ComisionConfigAuditoriaListResponse, ComisionConfigAuditoriaResponse,
    ConfigVendedorPayload, ConfigVendedoresResponse, ConfigVendedorResponse, FactorCreditoResponse,
    FactoresCreditoPayload, FactoresCreditoResponse, LineasSinCostoResponse, LineaSinCostoResponse,
    MatrizCategoriaPayload, MatrizCategoriaResponse, MatrizCategoriasResponse, PerfilCategoriaResponse,
    PerfilCategoriasResponse, SimulacionRequest, SimulacionResponse, SimulacionVendedorMesResponse,
    VendedorBusqueda,
)
from app.schemas.analytics import MetaSugeridaResponse
from app.schemas.goal import (
    CategoryRecommendationItem, GoalReviewPayload, GoalsAISummaryResponse, GoalTrackingResponse, VendorRiskItem,
)

router = APIRouter()

only_management = PermissionChecker(allowed_roles=["gerencia", "administrador"])
management_o_ventas = PermissionChecker(allowed_roles=["gerencia", "administrador", "ventas"])
sucursal_gerencia = resolve_sucursal_filter(allow_override=True)


@router.get(
    "/tracking", response_model=GoalTrackingResponse, summary="Obtiene metas y seguimiento del periodo",
    dependencies=[Depends(only_management)],
)
def get_goals_tracking(anio: int, mes: int, goals_service: GoalsServiceDep) -> GoalTrackingResponse:
    reporte = goals_service.get_commission_tracking(anio=anio, mes=mes)
    return GoalTrackingResponse(reporte_cumplimiento=reporte)


@router.get(
    "/meta-sugerida", response_model=MetaSugeridaResponse, dependencies=[Depends(only_management)],
    summary="Desglose del motor estadístico para un vendedor (transparencia del cálculo IQR)",
)
def get_meta_sugerida_vendedor(vendedor_origen: str, goal_ml_service: GoalMLServiceDep) -> MetaSugeridaResponse:
    """Fase 2 Metas (docs/features/plan_correcciones_pendientes.md §3): expone la misma
    trazabilidad que `SugerenciaMeta`/`IQRGoalCalculationEngine` ya calculaba pero
    descartaba tras `generate_proposals` -- método, meses de histórico usados, picos
    recortados por IQR, componente estacional/tendencia, factor de tendencia aplicado.
    Equivalente gerencial de `GET /analytics/ventas/goals/meta-sugerida` (esa usa
    `current_user.id_vendedor_origen`; esta acepta cualquier `vendedor_origen` para que
    el drawer de revisión de gerencia pueda mostrar el desglose de cualquier fila)."""
    resultado = goal_ml_service.suggest_goal(vendedor_origen)
    return MetaSugeridaResponse(**resultado.__dict__)


@router.get(
    "/periods", status_code=status.HTTP_200_OK, summary="Obtiene los periodos disponibles para metas",
    dependencies=[Depends(management_o_ventas)],
)
def get_goals_periods(goals_service: GoalsServiceDep):
    """Catálogo de `(anio, mes)` con datos -- global, no sensible por vendedor. Abierto
    también a `ventas` (docs/auditoria/34_actualizacion_modulo_ventas.md, H-V3) para
    poblar el selector de período del propio dashboard del vendedor, antes limitado a
    `only_management` pese a no exponer nada específico de otro vendedor."""
    return goals_service.get_periods()


@router.post(
    "/generate", status_code=status.HTTP_200_OK, summary="Genera metas automatizadas",
    dependencies=[Depends(only_management)],
)
def generate_goals(anio: int, mes: int, pressure_factor: float, goal_ml_service: GoalMLServiceDep):
    """Generador OFICIAL de metas (docs/auditoria/19_...md): una fila por vendedor
    (nunca por vendedor×sucursal), usando el motor estadístico IQR sobre Venta Neta
    (`GoalMLService.generate_proposals`), no `goals_rf`."""
    creados = goal_ml_service.generate_proposals(anio=anio, mes=mes, factor_presion=pressure_factor)
    return {"registros_creados": creados, "message": "Generación completada exitosamente"}


@router.get(
    "/ai-summary", response_model=GoalsAISummaryResponse, dependencies=[Depends(only_management)],
    summary="Metas sugeridas por IA, vendedores en riesgo/alta probabilidad, recomendaciones por categoría",
)
def get_goals_ai_summary(
    goal_ml_service: GoalMLServiceDep,
    analytics_service: AnalyticsServiceDep,
    sucursal_filtro: str | None = Depends(sucursal_gerencia),
) -> GoalsAISummaryResponse:
    """Integración ML del módulo Metas y Comisiones (docs/auditoria/15_...): compone
    `ranking_vendedores` real (ventas vs. meta del período vigente) con una
    clasificación de ritmo, y las reglas de recomendación agregadas por categoría."""
    kpis = analytics_service.get_sales_kpis(sucursal=sucursal_filtro)
    clasificacion = goal_ml_service.classify_vendor_risk(kpis["ranking_vendedores"])
    recomendaciones = goal_ml_service.get_category_recommendations()

    en_riesgo = [c for c in clasificacion if c.estado == "en_riesgo"]
    alta_probabilidad = [c for c in clasificacion if c.estado == "alta_probabilidad"]

    return GoalsAISummaryResponse(
        vendedores_en_riesgo=[VendorRiskItem(**c.__dict__) for c in en_riesgo],
        vendedores_alta_probabilidad=[VendorRiskItem(**c.__dict__) for c in alta_probabilidad],
        recomendaciones_por_categoria=[CategoryRecommendationItem(**r.__dict__) for r in recomendaciones],
    )


@router.get(
    "/commissions", response_model=CommissionTrackingResponse, dependencies=[Depends(only_management)],
    summary="Cumplimiento real (Venta Neta) y comisión devengada por vendedor en el período",
)
def get_commissions(anio: int, mes: int, commission_service: CommissionServiceDep) -> CommissionTrackingResponse:
    """Cierra el hallazgo R-1 (`docs/auditoria/14_...md`): `/tracking` solo muestra la
    meta configurada; este endpoint agrega la venta real del período y el tramo de
    comisión resultante (`commission_engine.calcular_comision`)."""
    filas = commission_service.get_commission_tracking(anio=anio, mes=mes)
    return CommissionTrackingResponse(comisiones=[VendorCommissionRowResponse(**f.__dict__) for f in filas])


@router.get(
    "/cumplimiento", response_model=CumplimientoMetaPeriodoResponse, dependencies=[Depends(only_management)],
    summary="KPI de cumplimiento vs metas del período (dashboard principal de Gerencia)",
)
def get_cumplimiento_meta_periodo(
    anio: int, mes: int, commission_service: CommissionServiceDep,
) -> CumplimientoMetaPeriodoResponse:
    """Fase 2 Gerencia (docs/features/plan_correcciones_pendientes.md §3): agregado
    company-wide de metas `APROBADA` -- monto meta total, venta real total, % de
    cumplimiento. Reutiliza `public.metas_comerciales_operativas` vía
    `CommissionService`/`GoalRepository`, sin ningún modelo ML (regla de negocio 10)."""
    return CumplimientoMetaPeriodoResponse(**commission_service.get_cumplimiento_meta_periodo(anio=anio, mes=mes))


@router.put(
    "/{goal_id}/review", status_code=status.HTTP_200_OK, summary="Aprobar o rechazar meta y actualizar comisión",
    dependencies=[Depends(only_management)],
)
def review_goal(
    goal_id: int,
    payload: GoalReviewPayload,
    goals_service: GoalsServiceDep,
    current_user: CurrentUserDep,
) -> dict:
    """Antes accedía al ORM directamente en el router (`db.query(Goal)...db.commit()`);
    ahora delega en `GoalsService.review_goal`, que usa `GoalRepository`."""
    goals_service.review_goal(
        goal_id=goal_id,
        estado=payload.estado,
        approved_by_user_id=current_user.id,
        monto_meta=payload.monto_meta,
        comision_base_pct=payload.comision_base_pct,
    )
    return {"message": f"Meta {payload.estado.lower()}"}


# ══════════════════════════════════════════════════════════════════════════════════
# Comisiones Variables (docs/features/plan_integracion_comisiones_variables.md)
# ══════════════════════════════════════════════════════════════════════════════════
@router.get(
    "/commission-config/matriz", response_model=MatrizCategoriasResponse, dependencies=[Depends(only_management)],
    summary="Matriz de categorías/tasas vigente (A/B/C/S/X)",
)
def get_matriz_categorias(commission_config_service: CommissionConfigServiceDep) -> MatrizCategoriasResponse:
    return MatrizCategoriasResponse(reglas=[MatrizCategoriaResponse(**r) for r in commission_config_service.get_matriz()])


@router.post(
    "/commission-config/matriz", response_model=MatrizCategoriaResponse, status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(only_management)], summary="Crea/actualiza una regla de categoría (cierra la vigencia anterior)",
)
def upsert_matriz_categoria(
    payload: MatrizCategoriaPayload, commission_config_service: CommissionConfigServiceDep, current_user: CurrentUserDep,
) -> MatrizCategoriaResponse:
    r = commission_config_service.upsert_regla_categoria(
        clase=payload.clase, subclase=payload.subclase, grupo=payload.grupo, tasa_pct=payload.tasa_pct,
        base=payload.base, factor_estrategico=payload.factor_estrategico, creado_por=current_user.id,
    )
    return MatrizCategoriaResponse(**r)


@router.get(
    "/commission-config/credito", response_model=FactoresCreditoResponse, dependencies=[Depends(only_management)],
    summary="Factores de ajuste por plazo de crédito vigentes",
)
def get_factores_credito(commission_config_service: CommissionConfigServiceDep) -> FactoresCreditoResponse:
    return FactoresCreditoResponse(
        factores=[FactorCreditoResponse(**f) for f in commission_config_service.get_factores_credito()],
    )


@router.put(
    "/commission-config/credito", response_model=FactoresCreditoResponse, dependencies=[Depends(only_management)],
    summary="Reemplaza la matriz de crédito vigente completa",
)
def replace_factores_credito(
    payload: FactoresCreditoPayload, commission_config_service: CommissionConfigServiceDep, current_user: CurrentUserDep,
) -> FactoresCreditoResponse:
    nuevos = commission_config_service.replace_factores_credito(
        [f.model_dump() for f in payload.factores], usuario_id=current_user.id,
    )
    return FactoresCreditoResponse(factores=[FactorCreditoResponse(**f) for f in nuevos])


@router.get(
    "/commission-config/vendedores", response_model=ConfigVendedoresResponse, dependencies=[Depends(only_management)],
    summary="Tipo (externo/interno) y parámetros por vendedor",
)
def get_config_vendedores(commission_config_service: CommissionConfigServiceDep) -> ConfigVendedoresResponse:
    return ConfigVendedoresResponse(
        vendedores=[ConfigVendedorResponse(**v) for v in commission_config_service.get_config_vendedores()],
    )


@router.put(
    "/commission-config/vendedores/{vendedor_origen}", response_model=ConfigVendedorResponse,
    dependencies=[Depends(only_management)], summary="Crea/actualiza el tipo de un vendedor (externo/interno)",
)
def upsert_config_vendedor(
    vendedor_origen: str, payload: ConfigVendedorPayload, commission_config_service: CommissionConfigServiceDep,
    current_user: CurrentUserDep,
) -> ConfigVendedorResponse:
    v = commission_config_service.upsert_config_vendedor(
        vendedor_origen=vendedor_origen, tipo=payload.tipo, factor_tipo=payload.factor_tipo,
        fecha_ingreso=payload.fecha_ingreso, usuario_id=current_user.id,
    )
    return ConfigVendedorResponse(**v)


@router.get(
    "/commission-config/search/clases", response_model=list[ClaseBusqueda],
    dependencies=[Depends(only_management)],
    summary="Autocompletar clase de producto (edw.dim_producto) para la Matriz de categorías",
)
def search_clases_producto(q: str, commission_config_service: CommissionConfigServiceDep) -> list[ClaseBusqueda]:
    return [ClaseBusqueda(**c) for c in commission_config_service.search_clases_producto(q)]


@router.get(
    "/commission-config/search/vendedores", response_model=list[VendedorBusqueda],
    dependencies=[Depends(only_management)],
    summary="Autocompletar vendedor por código SAP o nombre (edw.dim_vendedor) para Tipo de vendedor",
)
def search_commission_config_vendedores(
    q: str, commission_config_service: CommissionConfigServiceDep,
) -> list[VendedorBusqueda]:
    return [VendedorBusqueda(**v) for v in commission_config_service.search_vendedores(q)]


@router.get(
    "/commission-config/auditoria", response_model=ComisionConfigAuditoriaListResponse,
    dependencies=[Depends(only_management)],
    summary="Bitácora de cambios a la configuración de comisiones (quién cambió qué y cuándo)",
)
def get_commission_config_auditoria(
    commission_config_service: CommissionConfigServiceDep, limit: int = 100,
) -> ComisionConfigAuditoriaListResponse:
    """Fase 2 Metas (docs/features/plan_actualizacion_modulo_metas_comisiones.md §3
    ítem 2): antes solo `comision_matriz_categorias` guardaba `creado_por` en la fila
    vigente y ese rastro se perdía al cerrarla; esta bitácora append-only registra cada
    cambio (matriz, crédito, vendedor) con quién y cuándo, sin importar qué tabla."""
    return ComisionConfigAuditoriaListResponse(
        entradas=[ComisionConfigAuditoriaResponse(**a) for a in commission_config_service.get_auditoria(limit)],
    )


@router.post(
    "/commission-simulation", response_model=SimulacionResponse, dependencies=[Depends(only_management)],
    summary="Simulación retroactiva N meses: esquema plano vs. variable (Fase 2 del plan)",
)
def post_commission_simulation(
    payload: SimulacionRequest, commission_simulation_service: CommissionSimulationServiceDep,
) -> SimulacionResponse:
    r = commission_simulation_service.simular(meses=payload.meses, anio_desde=payload.anio_desde, mes_desde=payload.mes_desde)
    return SimulacionResponse(
        meses_simulados=r.meses_simulados, vendedores_simulados=r.vendedores_simulados,
        costo_total_plana=r.costo_total_plana, costo_total_variable=r.costo_total_variable,
        margen_bruto_total=r.margen_bruto_total,
        pct_comision_sobre_margen_plana=r.pct_comision_sobre_margen_plana,
        pct_comision_sobre_margen_variable=r.pct_comision_sobre_margen_variable,
        detalle=[SimulacionVendedorMesResponse(**d.__dict__) for d in r.detalle],
    )


@router.get(
    "/commission-analysis/categorias", response_model=PerfilCategoriasResponse, dependencies=[Depends(only_management)],
    summary="Perfil de margen por categoría (24 meses) -- insumo de la clasificación A/B/C/S/X (Fase 1)",
)
def get_commission_analysis_categorias(
    commission_config_service: CommissionConfigServiceDep, meses: int = 24,
) -> PerfilCategoriasResponse:
    return PerfilCategoriasResponse(
        perfiles=[PerfilCategoriaResponse(**p) for p in commission_config_service.get_perfil_categorias(meses)],
    )


@router.get(
    "/lineas-sin-costo", response_model=LineasSinCostoResponse, dependencies=[Depends(only_management)],
    summary="Salvaguarda 2: líneas del período sin costo registrado en SAP (margen no calculable)",
)
def get_lineas_sin_costo(
    commission_config_service: CommissionConfigServiceDep, anio: int | None = None, mes: int | None = None,
) -> LineasSinCostoResponse:
    hoy = datetime.date.today()
    anio = anio or hoy.year
    mes = mes or hoy.month
    return LineasSinCostoResponse(
        lineas=[LineaSinCostoResponse(**l) for l in commission_config_service.get_lineas_sin_costo(anio, mes)],
    )
