import { api } from './http';
import type {
  ClaseBusqueda, ComisionConfigAuditoriaEntrada, ConfigVendedor, ConfigVendedorPayload, FactorCredito,
  FactorCreditoPayload, Formula, FormulaComponentePayload, Formulas, LineaSinCosto, MatrizCategoria,
  MatrizCategoriaPayload, PerfilCategoria, ProyeccionComision, SimulacionComisionPayload,
  TodosTramosCobranza, TramoCobranza, TramosCobranzaPayload, VendedorBusqueda,
} from '../types/commissionConfig';

// Configuración del sistema de Comisiones Variables
// (docs/features/plan_integracion_comisiones_variables.md §3.5)

export const getMatrizCategorias = () =>
  api.get<{ reglas: MatrizCategoria[] }>('/api/v1/gerencia/goals/commission-config/matriz');

export const upsertMatrizCategoria = (payload: MatrizCategoriaPayload) =>
  api.post<MatrizCategoria>('/api/v1/gerencia/goals/commission-config/matriz', payload);

export const deleteMatrizCategoria = (id: number) =>
  api.delete<MatrizCategoria>(`/api/v1/gerencia/goals/commission-config/matriz/${id}`);

export const getFactoresCredito = () =>
  api.get<{ factores: FactorCredito[] }>('/api/v1/gerencia/goals/commission-config/credito');

export const replaceFactoresCredito = (factores: FactorCreditoPayload[]) =>
  api.put<{ factores: FactorCredito[] }>('/api/v1/gerencia/goals/commission-config/credito', { factores });

export const getConfigVendedores = () =>
  api.get<{ vendedores: ConfigVendedor[] }>('/api/v1/gerencia/goals/commission-config/vendedores');

export const upsertConfigVendedor = (vendedorOrigen: string, payload: ConfigVendedorPayload) =>
  api.put<ConfigVendedor>(`/api/v1/gerencia/goals/commission-config/vendedores/${vendedorOrigen}`, payload);

/** Proyección de comisión variable del próximo mes (3/6 meses de historial) o
 * reconstrucción real de un mes específico ya cerrado -- no compara contra el esquema
 * plano (ver types/commissionConfig.ts::SimulacionComisionPayload). */
export const postCommissionSimulation = (payload: SimulacionComisionPayload) =>
  api.post<ProyeccionComision>('/api/v1/gerencia/goals/commission-simulation', {
    meses_historico: 'mesesHistorico' in payload ? payload.mesesHistorico : null,
    anio: 'anio' in payload ? payload.anio : null,
    mes: 'mes' in payload ? payload.mes : null,
  });

export const getPerfilCategorias = (meses = 24) =>
  api.get<{ perfiles: PerfilCategoria[] }>('/api/v1/gerencia/goals/commission-analysis/categorias', {
    params: { meses },
  });

export const getLineasSinCosto = (anio?: number, mes?: number) =>
  api.get<{ lineas: LineaSinCosto[] }>('/api/v1/gerencia/goals/lineas-sin-costo', {
    params: { anio, mes },
  });

/** Bitácora de cambios de configuración (plan_actualizacion_modulo_metas_comisiones.md
 * Fase 2 ítem 2): quién cambió qué factor y cuándo, sin importar la tabla. */
export const getComisionConfigAuditoria = (limit = 100) =>
  api.get<{ entradas: ComisionConfigAuditoriaEntrada[] }>('/api/v1/gerencia/goals/commission-config/auditoria', {
    params: { limit },
  });

/** Búsqueda inteligente (autocomplete) para los formularios de configuración -- una
 * sola consulta por letra con `q`, nunca el catálogo completo, para no sobrecargar
 * el backend con cada tecla escrita. */
export const searchClasesProducto = (q: string) =>
  api.get<ClaseBusqueda[]>('/api/v1/gerencia/goals/commission-config/search/clases', { params: { q } });

export const searchVendedoresComision = (q: string) =>
  api.get<VendedorBusqueda[]>('/api/v1/gerencia/goals/commission-config/search/vendedores', { params: { q } });

// ── Comisión sobre COBROS (auditoría 44, docs/features/plan_comisiones_sobre_cobros.md) ──
export const getTramosCobranza = () =>
  api.get<TodosTramosCobranza>('/api/v1/gerencia/goals/commission-config/tramos-cobranza');

export const replaceTramosCobranza = (payload: TramosCobranzaPayload) =>
  api.put<TramoCobranza[]>('/api/v1/gerencia/goals/commission-config/tramos-cobranza', payload);

export const getFormulas = () =>
  api.get<Formulas>('/api/v1/gerencia/goals/commission-config/formula');

export const replaceFormulaComponentes = (formulaId: number, componentes: FormulaComponentePayload[]) =>
  api.put<Formula>(`/api/v1/gerencia/goals/commission-config/formula/${formulaId}/componentes`, { componentes });
