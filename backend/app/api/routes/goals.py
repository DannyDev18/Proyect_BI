# backend/app/api/routes/goals.py
import datetime
from dataclasses import asdict

from fastapi import APIRouter, Depends, status

from app.api.dependencies import (
    AnalyticsServiceDep, CommissionConfigServiceDep, CommissionServiceDep, CommissionSimulationServiceDep,
    GoalMLServiceDep, GoalsServiceDep, MetaConfigModuloServiceDep, MetaConfigServiceDep, resolve_sucursal_filter,
)
from app.core.deps import CurrentUserDep, PermissionChecker
from app.core.exceptions import ValidationError
from app.schemas.commission import (
    CommissionTrackingResponse, CumplimientoMetaPeriodoResponse, VendorCommissionRowResponse,
)
from app.schemas.commission_config import (
    ClaseBusqueda, ComisionConfigAuditoriaListResponse, ComisionConfigAuditoriaResponse,
    ConfigVendedorPayload, ConfigVendedoresResponse, ConfigVendedorResponse, FactorCreditoResponse,
    FactoresCreditoPayload, FactoresCreditoResponse, FormulaComponentesPayload, FormulaResponse, FormulasResponse,
    LineasSinCostoResponse, LineaSinCostoResponse, MatrizCategoriaPayload, MatrizCategoriaResponse,
    MatrizCategoriasResponse, PerfilCategoriaResponse, PerfilCategoriasResponse, ProyeccionComisionRequest,
    ProyeccionComisionResponse, ProyeccionVendedorResponse, TodosTramosCobranzaResponse, TramoCobranzaResponse,
    TramoCumplimientoResponse, TramosCobranzaPayload, TramosCumplimientoPayload, VendedorBusqueda,
)
from app.schemas.analytics import MetaSugeridaResponse
from app.schemas.goal import (
    CategoryRecommendationItem, GoalReviewPayload, GoalsAISummaryResponse, GoalTrackingResponse, VendorRiskItem,
)
from app.schemas.meta_config import MetaConfigAuditoriaItem, MetaConfigParametroOut, MetaConfigParametroUpdate
from app.schemas.meta_config_modulo import (
    MetaConfigModuloCatalogoEtapaOut, MetaConfigModuloOut, MetaConfigModuloUpdate,
)

router = APIRouter()

only_management = PermissionChecker(allowed_roles=["gerencia", "administrador"])
management_o_ventas = PermissionChecker(allowed_roles=["gerencia", "administrador", "ventas"])
sucursal_gerencia = resolve_sucursal_filter(allow_override=True)


@router.get(
    "/tracking", response_model=GoalTrackingResponse, summary="Obtiene metas y seguimiento del periodo",
    dependencies=[Depends(only_management)],
)
def get_goals_tracking(
    anio: int, mes: int, goals_service: GoalsServiceDep, vendedor: str | None = None,
) -> GoalTrackingResponse:
    reporte = goals_service.get_commission_tracking(anio=anio, mes=mes, vendedor=vendedor)
    return GoalTrackingResponse(reporte_cumplimiento=reporte)


@router.get(
    "/meta-sugerida", response_model=MetaSugeridaResponse, dependencies=[Depends(only_management)],
    summary="Desglose del motor v2 para un vendedor (transparencia del cálculo real)",
)
def get_meta_sugerida_vendedor(
    vendedor_origen: str, goal_ml_service: GoalMLServiceDep, anio: int | None = None, mes: int | None = None,
) -> MetaSugeridaResponse:
    """Fase 2 Metas (docs/features/plan_correcciones_pendientes.md §3, ampliado por
    docs/auditoria/46_motor_metas_configurable.md): expone la trazabilidad completa del
    motor v2 -- método, meses de histórico usados, picos recortados por IQR, índice
    estacional aplicado (propio o de empresa), tendencia, banda de alcanzabilidad.

    `anio`/`mes` (nuevos, H-1): el período sobre el que se quiere ver el cálculo -- si
    ya existe una meta generada para ese período, se devuelve la traza REAL persistida
    junto a ella (`es_trazabilidad_persistida=true`, H-5), no un recálculo con la
    configuración/histórico de HOY. Sin `anio`/`mes`, cae al comportamiento legado (mes
    siguiente al último dato, siempre en vivo).

    Equivalente gerencial de `GET /analytics/ventas/goals/meta-sugerida` (esa usa
    `current_user.id_vendedor_origen`; esta acepta cualquier `vendedor_origen` para que
    el drawer de revisión de gerencia pueda mostrar el desglose de cualquier fila)."""
    resultado = goal_ml_service.suggest_goal(vendedor_origen, anio, mes)
    return MetaSugeridaResponse(**resultado.__dict__)


# ══════════════════════════════════════════════════════════════════════════════════
# Configuración editable del motor de metas v2 (docs/features/plan_motor_metas_
# configurable.md §5.5, docs/auditoria/46_motor_metas_configurable.md)
# ══════════════════════════════════════════════════════════════════════════════════
@router.get(
    "/meta-config/parametros", response_model=list[MetaConfigParametroOut], dependencies=[Depends(only_management)],
    summary="Parámetros editables del motor de metas v2 (ventana, banda de alcanzabilidad, etc.)",
)
def get_meta_config_parametros(meta_config_service: MetaConfigServiceDep) -> list[MetaConfigParametroOut]:
    return [MetaConfigParametroOut.model_validate(p) for p in meta_config_service.get_parametros_configurables()]


@router.put(
    "/meta-config/parametros/{clave}", response_model=MetaConfigParametroOut, dependencies=[Depends(only_management)],
    summary="Actualiza un parámetro del motor de metas v2 (afecta solo a las metas que se generen desde ahora)",
)
def put_meta_config_parametro(
    clave: str, payload: MetaConfigParametroUpdate, meta_config_service: MetaConfigServiceDep, current_user: CurrentUserDep,
) -> MetaConfigParametroOut:
    parametro = meta_config_service.update_parametro(clave, payload.valor, usuario_id=current_user.id)
    return MetaConfigParametroOut.model_validate(parametro)


@router.get(
    "/meta-config/auditoria", response_model=list[MetaConfigAuditoriaItem], dependencies=[Depends(only_management)],
    summary="Bitácora de cambios a la configuración del motor de metas (quién cambió qué y cuándo)",
)
def get_meta_config_auditoria(meta_config_service: MetaConfigServiceDep, limit: int = 100) -> list[MetaConfigAuditoriaItem]:
    return [
        MetaConfigAuditoriaItem(usuario=nombre, accion=entrada.accion, detalle=entrada.detalle_json, fecha=entrada.fecha_creacion)
        for entrada, nombre in meta_config_service.get_auditoria(limit=limit)
    ]



# ══════════════════════════════════════════════════════════════════════════════════
# Configuración modular del motor de metas v3 (docs/features/plan_motor_metas_v3_y_
# comisiones_unificadas.md §9/§18, Fase 6) -- reemplaza a /meta-config/parametros como
# fuente real del motor; esa ruta se conserva sin cambios por compatibilidad.
# ══════════════════════════════════════════════════════════════════════════════════
@router.get(
    "/meta-config/catalogo", response_model=dict[str, MetaConfigModuloCatalogoEtapaOut],
    dependencies=[Depends(only_management)],
    summary="Catálogo cerrado de las 14 etapas del pipeline v3 y sus métodos (implementados y declarados)",
)
def get_meta_config_catalogo(meta_config_modulo_service: MetaConfigModuloServiceDep) -> dict[str, MetaConfigModuloCatalogoEtapaOut]:
    return {
        etapa: MetaConfigModuloCatalogoEtapaOut(**info)
        for etapa, info in meta_config_modulo_service.get_catalogo().items()
    }


@router.get(
    "/meta-config/modulos", response_model=list[MetaConfigModuloOut], dependencies=[Depends(only_management)],
    summary="Configuración modular vigente del motor de metas v3, una fila por etapa",
)
def get_meta_config_modulos(meta_config_modulo_service: MetaConfigModuloServiceDep) -> list[MetaConfigModuloOut]:
    return [MetaConfigModuloOut.model_validate(m) for m in meta_config_modulo_service.get_modulos()]


@router.put(
    "/meta-config/modulos/{etapa}", response_model=MetaConfigModuloOut, dependencies=[Depends(only_management)],
    summary="Activa/desactiva una etapa del pipeline v3 y edita su método/parámetros",
)
def put_meta_config_modulo(
    etapa: str, payload: MetaConfigModuloUpdate, meta_config_modulo_service: MetaConfigModuloServiceDep,
    current_user: CurrentUserDep,
) -> MetaConfigModuloOut:
    modulo = meta_config_modulo_service.update_modulo(
        etapa, payload.metodo, payload.activo, payload.parametros, usuario_id=current_user.id,
    )
    return MetaConfigModuloOut.model_validate(modulo)


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
def get_commissions(
    anio: int, mes: int, commission_service: CommissionServiceDep, vendedor: str | None = None,
) -> CommissionTrackingResponse:
    """Cierra el hallazgo R-1 (`docs/auditoria/14_...md`): `/tracking` solo muestra la
    meta configurada; este endpoint agrega la venta real del período y el tramo de
    comisión resultante (`commission_engine.calcular_comision`). Fase 3 §3.1
    (`docs/features/plan_correcciones_integrales_sistema.md`): `vendedor` opcional --
    sin selección devuelve la vista agregada de todos los vendedores (comportamiento
    previo, intacto); con selección, progreso individual de un solo vendedor."""
    filas = commission_service.get_commission_tracking(anio=anio, mes=mes, vendedor=vendedor)
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


@router.delete(
    "/commission-config/matriz/{regla_id}", response_model=MatrizCategoriaResponse, dependencies=[Depends(only_management)],
    summary="Elimina una regla de categoría (cierra su vigencia, no borra el historial)",
)
def eliminar_matriz_categoria(
    regla_id: int, commission_config_service: CommissionConfigServiceDep, current_user: CurrentUserDep,
) -> MatrizCategoriaResponse:
    r = commission_config_service.eliminar_regla_categoria(regla_id, usuario_id=current_user.id)
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
        fecha_ingreso=payload.fecha_ingreso, usuario_id=current_user.id, agencia=payload.agencia,
    )
    return ConfigVendedorResponse(**v)


# ── Comisión sobre COBROS (auditoría 44, docs/features/plan_comisiones_sobre_cobros.md) ──
@router.get(
    "/commission-config/tramos-cobranza", response_model=TodosTramosCobranzaResponse,
    dependencies=[Depends(only_management)],
    summary="Tramos de comisión sobre cobros por perfil (externo/interno/jefe de agencia)",
)
def get_tramos_cobranza(commission_config_service: CommissionConfigServiceDep) -> TodosTramosCobranzaResponse:
    por_perfil = commission_config_service.get_todos_tramos_cobranza()
    return TodosTramosCobranzaResponse(
        externo=[TramoCobranzaResponse(**t) for t in por_perfil["externo"]],
        interno=[TramoCobranzaResponse(**t) for t in por_perfil["interno"]],
        jefe_agencia=[TramoCobranzaResponse(**t) for t in por_perfil["jefe_agencia"]],
    )


@router.put(
    "/commission-config/tramos-cobranza", response_model=list[TramoCobranzaResponse],
    dependencies=[Depends(only_management)],
    summary="Reemplaza los tramos de comisión sobre cobros de UN perfil",
)
def put_tramos_cobranza(
    payload: TramosCobranzaPayload, commission_config_service: CommissionConfigServiceDep, current_user: CurrentUserDep,
) -> list[TramoCobranzaResponse]:
    nuevos = commission_config_service.replace_tramos_cobranza(
        perfil=payload.perfil, tramos=[t.model_dump() for t in payload.tramos], usuario_id=current_user.id,
    )
    return [TramoCobranzaResponse(**t) for t in nuevos]


@router.get(
    "/commission-config/tramos-cumplimiento", response_model=list[TramoCumplimientoResponse],
    dependencies=[Depends(only_management)],
    summary="Tramos del multiplicador de cumplimiento (auditoría 45: umbral 90% + escala de sobrecumplimiento)",
)
def get_tramos_cumplimiento(commission_config_service: CommissionConfigServiceDep) -> list[TramoCumplimientoResponse]:
    return [TramoCumplimientoResponse(**t) for t in commission_config_service.get_tramos_cumplimiento()]


@router.put(
    "/commission-config/tramos-cumplimiento", response_model=list[TramoCumplimientoResponse],
    dependencies=[Depends(only_management)],
    summary="Reemplaza los tramos del multiplicador de cumplimiento",
)
def put_tramos_cumplimiento(
    payload: TramosCumplimientoPayload, commission_config_service: CommissionConfigServiceDep,
    current_user: CurrentUserDep,
) -> list[TramoCumplimientoResponse]:
    nuevos = commission_config_service.replace_tramos_cumplimiento(
        tramos=[t.model_dump() for t in payload.tramos], usuario_id=current_user.id,
    )
    return [TramoCumplimientoResponse(**t) for t in nuevos]


@router.get(
    "/commission-config/formula", response_model=FormulasResponse, dependencies=[Depends(only_management)],
    summary="Fórmulas de comisión variable (estructura editable) + catálogo de componentes válidos",
)
def get_formulas(commission_config_service: CommissionConfigServiceDep) -> FormulasResponse:
    return FormulasResponse(**commission_config_service.get_formulas())


@router.put(
    "/commission-config/formula/{formula_id}/componentes", response_model=FormulaResponse,
    dependencies=[Depends(only_management)],
    summary="Reemplaza la tubería de componentes de una fórmula",
)
def put_formula_componentes(
    formula_id: int, payload: FormulaComponentesPayload, commission_config_service: CommissionConfigServiceDep,
    current_user: CurrentUserDep,
) -> FormulaResponse:
    componentes = commission_config_service.reemplazar_componentes_formula(
        formula_id=formula_id, componentes=[c.model_dump() for c in payload.componentes], usuario_id=current_user.id,
    )
    formulas = commission_config_service.get_formulas()["formulas"]
    formula = next(f for f in formulas if f["id"] == formula_id)
    return FormulaResponse(**{**formula, "componentes": componentes})



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
    "/commission-simulation", response_model=ProyeccionComisionResponse, dependencies=[Depends(only_management)],
    summary="Proyección de comisión variable del próximo mes (3/6 meses de historial) o "
             "reconstrucción real de un mes específico ya cerrado",
)
def post_commission_simulation(
    payload: ProyeccionComisionRequest, commission_simulation_service: CommissionSimulationServiceDep,
) -> ProyeccionComisionResponse:
    """Exclusivamente esquema variable (sin comparar contra el plano) -- ver
    `CommissionSimulationService.proyectar_comision_variable`/`reconstruir_mes_especifico`
    para el porqué de cada decisión de diseño. La comparación retroactiva plano vs.
    variable (`simular()`) sigue existiendo internamente para la alerta de divergencia
    del piloto en sombra, pero ya no se expone por este endpoint.

    `anio`+`mes`: reconstruye lo que se hubiera pagado ESE mes específico con la
    configuración vigente hoy (meta/bonos/devoluciones reales de ese período).
    `meses_historico` (default 3 si no se especifica nada): proyecta el próximo mes
    calendario promediando los últimos 3 o 6 meses cerrados. Son mutuamente
    excluyentes -- pasar `anio`/`mes` tiene prioridad si por error llegan ambos."""
    if (payload.anio is None) != (payload.mes is None):
        raise ValidationError("Para reconstruir un mes específico se requieren `anio` y `mes` juntos.")
    if payload.anio is not None and payload.mes is not None:
        r = commission_simulation_service.reconstruir_mes_especifico(
            payload.anio, payload.mes, usar_configuracion_de_hoy=payload.usar_configuracion_de_hoy,
        )
    else:
        r = commission_simulation_service.proyectar_comision_variable(payload.meses_historico or 3)
    return ProyeccionComisionResponse(
        meses_historico=r.meses_historico, periodo_proyectado=r.periodo_proyectado,
        vendedores_proyectados=r.vendedores_proyectados,
        comision_variable_total_proyectada=r.comision_variable_total_proyectada,
        margen_bruto_total_promedio=r.margen_bruto_total_promedio,
        tasa_efectiva_pct_global=r.tasa_efectiva_pct_global,
        modo=r.modo,
        detalle=[
            ProyeccionVendedorResponse(**{**d.__dict__, "componentes": [asdict(c) for c in d.componentes]})
            for d in r.detalle
        ],
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
