import { FileClock } from 'lucide-react';

import { useComisionConfigAuditoria } from '../../hooks/commissionConfig';
import type { ComisionConfigAuditoriaEntrada } from '../../types/commissionConfig';
import { DataTable, type DataTableColumn } from '../ui/DataTable';

// docs/features/plan_motor_metas_v3_y_comisiones_unificadas.md, Fase 8, R-11: la
// bitácora vivía como una pestaña escondida DENTRO de CommissionConfigPanel
// ("auditoria") y solo cubría configuración de comisiones. Se promueve a pestaña
// propia de primer nivel en DashboardMetas.tsx, y registra cambios de AMBOS dominios
// (comisiones y metas) porque `public.comision_config_auditoria` ya es una bitácora
// genérica reutilizada por las dos configuraciones (migración 0013 amplió su CHECK
// para admitir 'metas_config_parametros'/'metas_config_modulos'). Estrictamente de
// solo lectura: sin acciones, sin edición, sin borrado -- la tabla ya es append-only.
const TABLA_LABEL: Record<string, string> = {
  comision_matriz_categorias: 'Comisiones · Matriz de categorías',
  comision_config_vendedor: 'Comisiones · Tipo de vendedor',
  comision_tramos_cobranza: 'Comisiones · Comisión sobre cobros',
  comision_tramos_cumplimiento: 'Comisiones · Tramos de cumplimiento',
  comision_formula: 'Comisiones · Fórmula',
  metas_config_parametros: 'Metas · Parámetros (legado)',
  metas_config_modulos: 'Metas · Fórmula modular',
};

const ACCION_LABEL: Record<string, string> = {
  upsert: 'Creó/actualizó',
  replace: 'Reemplazó',
  reemplazar_componentes: 'Reemplazó componentes',
  activar: 'Activó',
};

function formatDetalle(detalle: Record<string, unknown>): string {
  return Object.entries(detalle)
    .filter(([k]) => k !== 'id')
    .map(([k, v]) => `${k}=${v}`)
    .join(', ');
}

/** Bitácora de cambios de Metas y Comisiones -- de solo lectura (R-11). */
export function BitacoraPanel() {
  const auditoria = useComisionConfigAuditoria();

  const columns: DataTableColumn<ComisionConfigAuditoriaEntrada>[] = [
    {
      key: 'fecha_creacion', header: 'Fecha',
      render: (a) => new Date(a.fecha_creacion).toLocaleString('es-EC', { dateStyle: 'medium', timeStyle: 'short' }),
    },
    { key: 'usuario_nombre', header: 'Usuario', render: (a) => a.usuario_nombre ?? '—' },
    { key: 'tabla', header: 'Configuración', render: (a) => TABLA_LABEL[a.tabla] ?? a.tabla },
    { key: 'accion', header: 'Acción', render: (a) => ACCION_LABEL[a.accion] ?? a.accion },
    { key: 'detalle_json', header: 'Detalle', render: (a) => <span className="text-xs text-slate-400">{formatDetalle(a.detalle_json)}</span> },
  ];

  return (
    <div className="p-6 bg-slate-900 text-white rounded-lg border border-slate-800 shadow-xl max-w-7xl mx-auto space-y-4">
      <div className="flex items-center gap-3 mb-2">
        <FileClock className="w-8 h-8 text-info" aria-hidden="true" />
        <div>
          <h2 className="text-2xl font-bold tracking-tight">Bitácora de cambios</h2>
          <p className="text-sm text-slate-500 mt-0.5">
            Quién cambió qué configuración de metas o comisiones y cuándo -- solo lectura, append-only.
          </p>
        </div>
      </div>
      <DataTable
        columns={columns}
        data={auditoria.data}
        rowKey={(a) => a.id}
        loading={auditoria.loading}
        error={auditoria.error ?? undefined}
        onRetry={auditoria.refetch}
        density="compact"
        emptyTitle="Sin cambios registrados todavía"
        emptyDescription="Cada ajuste de configuración de metas o comisiones queda registrado aquí."
      />
    </div>
  );
}
