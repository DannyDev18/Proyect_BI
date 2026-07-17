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

export interface SimulacionVendedorMes {
  vendedor_origen: string;
  anio: number;
  mes: number;
  venta_neta: number;
  comision_plana: number;
  comision_variable: number;
  diferencia: number;
  diferencia_pct: number | null;
}

export interface SimulacionResumen {
  meses_simulados: number;
  vendedores_simulados: number;
  costo_total_plana: number;
  costo_total_variable: number;
  margen_bruto_total: number;
  pct_comision_sobre_margen_plana: number;
  pct_comision_sobre_margen_variable: number;
  detalle: SimulacionVendedorMes[];
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
