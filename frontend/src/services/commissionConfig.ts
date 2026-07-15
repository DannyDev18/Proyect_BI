import { api } from './http';
import type {
  ConfigVendedor, ConfigVendedorPayload, FactorCredito, FactorCreditoPayload, LineaSinCosto,
  MatrizCategoria, MatrizCategoriaPayload, PerfilCategoria, SimulacionResumen,
} from '../types/commissionConfig';

// Configuración del sistema de Comisiones Variables
// (docs/features/plan_integracion_comisiones_variables.md §3.5)

export const getMatrizCategorias = () =>
  api.get<{ reglas: MatrizCategoria[] }>('/api/v1/gerencia/goals/commission-config/matriz');

export const upsertMatrizCategoria = (payload: MatrizCategoriaPayload) =>
  api.post<MatrizCategoria>('/api/v1/gerencia/goals/commission-config/matriz', payload);

export const getFactoresCredito = () =>
  api.get<{ factores: FactorCredito[] }>('/api/v1/gerencia/goals/commission-config/credito');

export const replaceFactoresCredito = (factores: FactorCreditoPayload[]) =>
  api.put<{ factores: FactorCredito[] }>('/api/v1/gerencia/goals/commission-config/credito', { factores });

export const getConfigVendedores = () =>
  api.get<{ vendedores: ConfigVendedor[] }>('/api/v1/gerencia/goals/commission-config/vendedores');

export const upsertConfigVendedor = (vendedorOrigen: string, payload: ConfigVendedorPayload) =>
  api.put<ConfigVendedor>(`/api/v1/gerencia/goals/commission-config/vendedores/${vendedorOrigen}`, payload);

export const postCommissionSimulation = (meses: number, anioDesde?: number, mesDesde?: number) =>
  api.post<SimulacionResumen>('/api/v1/gerencia/goals/commission-simulation', {
    meses, anio_desde: anioDesde, mes_desde: mesDesde,
  });

export const getPerfilCategorias = (meses = 24) =>
  api.get<{ perfiles: PerfilCategoria[] }>('/api/v1/gerencia/goals/commission-analysis/categorias', {
    params: { meses },
  });

export const getLineasSinCosto = (anio?: number, mes?: number) =>
  api.get<{ lineas: LineaSinCosto[] }>('/api/v1/gerencia/goals/lineas-sin-costo', {
    params: { anio, mes },
  });
