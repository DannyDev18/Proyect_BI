// Configuración del sistema de Comisiones Variables
// (docs/features/plan_integracion_comisiones_variables.md §3.5)

export type GrupoComision = 'A' | 'B' | 'C' | 'S' | 'X';
export type BaseComision = 'margen' | 'valor';
// 'jefe_agencia' (auditoría 44, docs/features/plan_comisiones_sobre_cobros.md): tercer
// perfil real de la empresa, con tramos de cobranza propios y el componente
// 'contado_agencia' (requiere `agencia`).
export type TipoVendedor = 'externo' | 'interno' | 'jefe_agencia';

export interface MatrizCategoria {
  id: number;
  clase: string;
  subclase: string | null;
  grupo: GrupoComision;
  tasa_pct: number;
  base: BaseComision;
  factor_estrategico: number;
  vigente_desde: string;
  vigente_hasta: string | null;
}

export interface MatrizCategoriaPayload {
  clase: string;
  subclase?: string | null;
  grupo: GrupoComision;
  tasa_pct: number;
  base: BaseComision;
  factor_estrategico: number;
}

export interface FactorCredito {
  id: number;
  dias_desde: number;
  dias_hasta: number | null;
  factor: number;
  vigente_desde: string;
  vigente_hasta: string | null;
}

export interface FactorCreditoPayload {
  dias_desde: number;
  dias_hasta?: number | null;
  factor: number;
}

export interface ConfigVendedor {
  id_vendedor_origen: string;
  nombre_vendedor: string | null;
  tipo: TipoVendedor;
  factor_tipo: number;
  fecha_ingreso: string | null;
  activo: boolean;
  agencia: string | null;
}

export interface VendedorBusqueda {
  codven: string;
  nombre_vendedor: string | null;
}

export interface ClaseBusqueda {
  clase: string;
  productos: number;
}

export interface ConfigVendedorPayload {
  tipo: TipoVendedor;
  factor_tipo: number;
  fecha_ingreso?: string | null;
  agencia?: string | null;
}

// ── Comisión sobre COBROS (auditoría 44 §2.1) ───────────────────────────────────
export interface TramoCobranza {
  id: number;
  perfil: TipoVendedor;
  dias_hasta: number | null;
  tasa_pct: number;
  vigente_desde: string;
  vigente_hasta: string | null;
}

export interface TramoCobranzaPayload {
  dias_hasta: number | null;
  tasa_pct: number;
}

export interface TramosCobranzaPayload {
  perfil: TipoVendedor;
  tramos: TramoCobranzaPayload[];
}

export interface TodosTramosCobranza {
  externo: TramoCobranza[];
  interno: TramoCobranza[];
  jefe_agencia: TramoCobranza[];
}

// ── Fórmula de comisión (auditoría 44 §2.2: estructura editable, no quemada) ────
export type OperadorFormula = 'sumar' | 'restar' | 'multiplicar';

/** Catálogo cerrado de componentes -- debe reflejar exactamente
 * `backend/app/services/commission_engine.py::COMPONENTES_FORMULA`. El backend valida
 * de nuevo (nunca confiar solo en el frontend), pero mantenerlo aquí evita que el
 * editor ofrezca una clave que el motor no sabe resolver. */
export type ComponenteFormula =
  | 'base_lineas_venta'
  | 'base_cobranza'
  | 'contado_agencia'
  | 'factor_tipo_vendedor'
  | 'multiplicador_cumplimiento'
  | 'devoluciones'
  | 'bonos';

export interface FormulaComponente {
  id: number;
  orden: number;
  componente: ComponenteFormula;
  operador: OperadorFormula;
  activo: boolean;
  parametros: Record<string, unknown>;
}

export interface Formula {
  id: number;
  clave: string;
  nombre: string;
  activa: boolean;
  componentes: FormulaComponente[];
}

export interface Formulas {
  formulas: Formula[];
  catalogo_componentes: ComponenteFormula[];
}

export interface FormulaComponentePayload {
  orden: number;
  componente: ComponenteFormula;
  operador: OperadorFormula;
  activo: boolean;
  parametros: Record<string, unknown>;
}

/** Dos modos mutuamente excluyentes (ver backend/app/schemas/commission_config.py::
 * ProyeccionComisionRequest): `mesesHistorico` proyecta el próximo mes promediando 3 o
 * 6 meses cerrados (cumplimiento neutro); `anio`+`mes` reconstruye lo que se hubiera
 * pagado REALMENTE ese mes específico ya cerrado, con la configuración vigente hoy y
 * la meta/bonos/devoluciones reales de ese período. */
export type SimulacionComisionPayload =
  | { mesesHistorico: 3 | 6 }
  | { anio: number; mes: number };

/** Proyección de Comisiones Variables (panel "Simulación" de gerencia): toma los
 * últimos 3 o 6 meses YA CERRADOS como base histórica y proyecta la comisión variable
 * del próximo mes calendario -- solo esquema variable, sin comparar contra el plano
 * (ver backend/app/services/commission_simulation_service.py::proyectar_comision_variable). */
export interface ProyeccionVendedor {
  vendedor_origen: string;
  nombre_vendedor: string | null;
  periodo_proyectado: string;
  meses_historico_usados: number;
  venta_neta_promedio: number;
  margen_bruto_promedio: number;
  comision_variable_proyectada: number;
  tasa_efectiva_pct: number;
}

export interface ProyeccionComision {
  meses_historico: number;
  periodo_proyectado: string;
  vendedores_proyectados: number;
  comision_variable_total_proyectada: number;
  margen_bruto_total_promedio: number;
  tasa_efectiva_pct_global: number;
  detalle: ProyeccionVendedor[];
}

export interface PerfilCategoria {
  clase: string;
  es_servicio: boolean;
  venta_total: number;
  margen_total: number;
  margen_pct: number;
  num_vendedores: number;
  num_lineas: number;
  tasa_descuento_prom_pct: number;
}

export interface LineaSinCosto {
  codart: string;
  vendedor_origen: string;
  venta_afectada: number;
  num_lineas: number;
}

export interface ComisionConfigAuditoriaEntrada {
  id: number;
  usuario_id: number | null;
  usuario_nombre: string | null;
  tabla: string;
  accion: string;
  detalle_json: Record<string, unknown>;
  fecha_creacion: string;
}
