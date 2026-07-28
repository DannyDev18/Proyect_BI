// Configuración del sistema de Comisiones Variables
// (docs/features/plan_integracion_comisiones_variables.md §3.5)

export type GrupoComision = 'A' | 'B' | 'C' | 'S' | 'X';
export type BaseComision = 'margen' | 'valor';
export type TipoVendedor = 'externo' | 'interno';

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
  pct_al_facturar: number;
  vigente_desde: string;
  vigente_hasta: string | null;
}

export interface FactorCreditoPayload {
  dias_desde: number;
  dias_hasta?: number | null;
  factor: number;
  pct_al_facturar: number;
}

export interface ConfigVendedor {
  id_vendedor_origen: string;
  nombre_vendedor: string | null;
  tipo: TipoVendedor;
  factor_tipo: number;
  fecha_ingreso: string | null;
  activo: boolean;
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
}

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
