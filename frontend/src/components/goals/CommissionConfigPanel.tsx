import { useState, type ReactNode } from 'react';
import { Settings, Plus, CreditCard, Users } from 'lucide-react';

import {
  useMatrizCategorias, useUpsertMatrizCategoria, useFactoresCredito, useReplaceFactoresCredito,
  useConfigVendedores, useUpsertConfigVendedor,
} from '../../hooks/commissionConfig';
import type {
  ConfigVendedor, FactorCreditoPayload, GrupoComision, MatrizCategoria, TipoVendedor,
} from '../../types/commissionConfig';
import { Tabs } from '../ui/Tabs';
import { Button } from '../ui/Button';
import { Select } from '../ui/Select';
import { DataTable, type DataTableColumn } from '../ui/DataTable';
import { AlertBadge } from '../ui/AlertBadge';
import { useToast } from '../../store/toastStore';

const GRUPOS: GrupoComision[] = ['A', 'B', 'C', 'S', 'X'];
const GRUPO_VARIANT: Record<GrupoComision, 'success' | 'info' | 'warning' | 'critical'> = {
  A: 'success', B: 'info', C: 'warning', S: 'info', X: 'critical',
};

/** Panel de configuración de gerencia para el sistema de Comisiones Variables
 * (docs/features/plan_integracion_comisiones_variables.md §3.5, Fase 5: "gerencia
 * ajusta la matriz sin programar"). 3 pestañas: matriz de categorías, factores de
 * crédito y tipo de vendedor -- cada una es un CRUD directo contra los endpoints
 * `/gerencia/goals/commission-config/*`. */
export function CommissionConfigPanel() {
  const [tab, setTab] = useState<'matriz' | 'credito' | 'vendedores'>('matriz');

  return (
    <div className="p-6 bg-slate-900 text-white rounded-lg border border-slate-800 shadow-xl max-w-7xl mx-auto">
      <div className="flex items-center gap-3 mb-4">
        <Settings className="w-8 h-8 text-cyan-400" aria-hidden="true" />
        <div>
          <h2 className="text-2xl font-bold tracking-tight">Configuración de Comisiones Variables</h2>
          <p className="text-sm text-slate-500 mt-0.5">
            Matriz de categorías, plazos de crédito y tipo de vendedor -- editable sin desarrollo.
          </p>
        </div>
      </div>

      <Tabs
        className="mb-5"
        value={tab}
        onChange={(v) => setTab(v as typeof tab)}
        items={[
          { value: 'matriz', label: 'Matriz de categorías' },
          { value: 'credito', label: 'Factores de crédito' },
          { value: 'vendedores', label: 'Tipo de vendedor' },
        ]}
      />

      {tab === 'matriz' && <MatrizTab />}
      {tab === 'credito' && <CreditoTab />}
      {tab === 'vendedores' && <VendedoresTab />}
    </div>
  );
}

// ── Matriz de categorías ────────────────────────────────────────────────────────
function MatrizTab() {
  const matriz = useMatrizCategorias();
  const upsertMut = useUpsertMatrizCategoria();
  const toast = useToast();

  const [form, setForm] = useState({ clase: '', subclase: '', grupo: 'B' as GrupoComision, tasa_pct: 8, base: 'margen' as 'margen' | 'valor', factor_estrategico: 1.0 });

  const handleSubmit = async () => {
    if (!form.clase.trim()) {
      toast('La clase (código de producto) es obligatoria.', 'error');
      return;
    }
    try {
      await upsertMut.upsert({
        clase: form.clase.trim().toUpperCase(),
        subclase: form.subclase.trim() ? form.subclase.trim().toUpperCase() : null,
        grupo: form.grupo,
        tasa_pct: form.tasa_pct,
        base: form.base,
        factor_estrategico: form.factor_estrategico,
      });
      toast('Regla de categoría guardada. La vigencia anterior (si existía) quedó cerrada.', 'success');
      setForm({ clase: '', subclase: '', grupo: 'B', tasa_pct: 8, base: 'margen', factor_estrategico: 1.0 });
    } catch {
      toast('No se pudo guardar la regla de categoría.', 'error');
    }
  };

  const columns: DataTableColumn<MatrizCategoria>[] = [
    { key: 'clase', header: 'Clase', render: (r) => <span className="font-mono text-slate-200">{r.clase}</span> },
    { key: 'subclase', header: 'Subclase', render: (r) => <span className="font-mono text-slate-500">{r.subclase ?? 'Toda la clase'}</span> },
    { key: 'grupo', header: 'Grupo', render: (r) => <AlertBadge variant={GRUPO_VARIANT[r.grupo]}>{r.grupo}</AlertBadge> },
    { key: 'tasa_pct', header: 'Tasa', numeric: true, render: (r) => <span className="font-mono">{r.tasa_pct.toFixed(2)}%</span> },
    { key: 'base', header: 'Base', render: (r) => <span className="text-slate-400">{r.base === 'margen' ? 'Margen bruto' : 'Valor de venta'}</span> },
    { key: 'factor_estrategico', header: 'Factor estratégico', numeric: true, render: (r) => <span className="font-mono">{r.factor_estrategico.toFixed(2)}x</span> },
    { key: 'vigente_desde', header: 'Vigente desde', render: (r) => <span className="text-slate-500">{r.vigente_desde}</span> },
  ];

  return (
    <div className="space-y-5">
      <div className="p-5 bg-slate-800/50 rounded-lg border border-slate-700/50 flex flex-wrap gap-4 items-end">
        <Field label="Clase (código)">
          <input value={form.clase} onChange={(e) => setForm({ ...form, clase: e.target.value })}
            placeholder="Ej. BAT / *" className="input-field w-28" />
        </Field>
        <Field label="Subclase (opcional)">
          <input value={form.subclase} onChange={(e) => setForm({ ...form, subclase: e.target.value })}
            placeholder="Toda la clase" className="input-field w-28" />
        </Field>
        <Field label="Grupo">
          <Select value={form.grupo} onChange={(e) => setForm({ ...form, grupo: e.target.value as GrupoComision })}>
            {GRUPOS.map((g) => <option key={g} value={g}>{g}</option>)}
          </Select>
        </Field>
        <Field label="Tasa (%)">
          <input type="number" step="0.1" min={0} max={100} value={form.tasa_pct}
            onChange={(e) => setForm({ ...form, tasa_pct: parseFloat(e.target.value) || 0 })} className="input-field w-20" />
        </Field>
        <Field label="Base">
          <Select value={form.base} onChange={(e) => setForm({ ...form, base: e.target.value as 'margen' | 'valor' })}>
            <option value="margen">Margen bruto</option>
            <option value="valor">Valor de venta</option>
          </Select>
        </Field>
        <Field label="Factor estratégico">
          <input type="number" step="0.05" min={0.5} max={1.5} value={form.factor_estrategico}
            onChange={(e) => setForm({ ...form, factor_estrategico: parseFloat(e.target.value) || 1.0 })} className="input-field w-20" />
        </Field>
        <Button variant="primary" onClick={handleSubmit} loading={upsertMut.loading} icon={<Plus className="w-4 h-4" aria-hidden="true" />}>
          Guardar regla
        </Button>
      </div>

      <DataTable
        columns={columns}
        data={matriz.data}
        rowKey={(r) => r.id}
        loading={matriz.loading}
        error={matriz.error ?? undefined}
        onRetry={matriz.refetch}
        emptyTitle="Sin reglas de categoría configuradas"
        emptyDescription="Agrega la primera regla arriba (ej. clase '*' como default)."
      />
    </div>
  );
}

// ── Factores de crédito ─────────────────────────────────────────────────────────
function CreditoTab() {
  const credito = useFactoresCredito();
  const replaceMut = useReplaceFactoresCredito();
  const toast = useToast();
  const [rows, setRows] = useState<FactorCreditoPayload[] | null>(null);

  const activos = rows ?? credito.data.map((f) => ({
    dias_desde: f.dias_desde, dias_hasta: f.dias_hasta, factor: f.factor, pct_al_facturar: f.pct_al_facturar,
  }));

  const updateRow = (idx: number, patch: Partial<FactorCreditoPayload>) => {
    const next = [...activos];
    next[idx] = { ...next[idx], ...patch };
    setRows(next);
  };

  const addRow = () => setRows([...activos, { dias_desde: 0, dias_hasta: null, factor: 1.0, pct_al_facturar: 100 }]);
  const removeRow = (idx: number) => setRows(activos.filter((_, i) => i !== idx));

  const handleSave = async () => {
    try {
      await replaceMut.replace(activos);
      toast('Matriz de crédito actualizada.', 'success');
      setRows(null);
    } catch {
      toast('No se pudo guardar la matriz de crédito.', 'error');
    }
  };

  return (
    <div className="space-y-4">
      <p className="text-xs text-slate-500">
        Auditoría 30 (H4): el EDW actual solo registra tráfico real en 0 y 30 días de plazo -- los demás tramos son
        configuración disponible sin historial que la respalde todavía.
      </p>
      <div className="card overflow-hidden">
        <table className="w-full text-left text-sm">
          <thead className="bg-slate-950/60 text-slate-500 text-xs uppercase tracking-widest">
            <tr>
              <th className="px-4 py-2">Días desde</th>
              <th className="px-4 py-2">Días hasta</th>
              <th className="px-4 py-2">Factor</th>
              <th className="px-4 py-2">% al facturar</th>
              <th className="px-4 py-2 text-right">Acciones</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-800/80">
            {activos.map((r, idx) => (
              <tr key={idx}>
                <td className="px-4 py-2">
                  <input type="number" min={0} value={r.dias_desde} className="input-field w-20"
                    onChange={(e) => updateRow(idx, { dias_desde: parseInt(e.target.value) || 0 })} />
                </td>
                <td className="px-4 py-2">
                  <input type="number" min={0} value={r.dias_hasta ?? ''} placeholder="Sin tope" className="input-field w-24"
                    onChange={(e) => updateRow(idx, { dias_hasta: e.target.value ? parseInt(e.target.value) : null })} />
                </td>
                <td className="px-4 py-2">
                  <input type="number" step="0.01" min={0} max={1.5} value={r.factor} className="input-field w-20"
                    onChange={(e) => updateRow(idx, { factor: parseFloat(e.target.value) || 0 })} />
                </td>
                <td className="px-4 py-2">
                  <input type="number" step="1" min={0} max={100} value={r.pct_al_facturar} className="input-field w-20"
                    onChange={(e) => updateRow(idx, { pct_al_facturar: parseFloat(e.target.value) || 0 })} />
                </td>
                <td className="px-4 py-2 text-right">
                  <Button variant="danger" size="sm" onClick={() => removeRow(idx)}>Quitar</Button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="flex gap-3">
        <Button variant="ghost" onClick={addRow} icon={<Plus className="w-4 h-4" aria-hidden="true" />}>Agregar tramo</Button>
        <Button variant="primary" onClick={handleSave} loading={replaceMut.loading} icon={<CreditCard className="w-4 h-4" aria-hidden="true" />}>
          Guardar matriz de crédito
        </Button>
      </div>
    </div>
  );
}

// ── Tipo de vendedor ────────────────────────────────────────────────────────────
function VendedoresTab() {
  const vendedores = useConfigVendedores();
  const upsertMut = useUpsertConfigVendedor();
  const toast = useToast();
  const [nuevo, setNuevo] = useState({ vendedor: '', tipo: 'externo' as TipoVendedor, factor: 1.0 });

  const handleAdd = async () => {
    if (!nuevo.vendedor.trim()) {
      toast('El código de vendedor (id_vendedor_origen) es obligatorio.', 'error');
      return;
    }
    try {
      await upsertMut.upsert({ vendedorOrigen: nuevo.vendedor.trim(), tipo: nuevo.tipo, factor_tipo: nuevo.factor });
      toast('Configuración de vendedor guardada.', 'success');
      setNuevo({ vendedor: '', tipo: 'externo', factor: 1.0 });
    } catch {
      toast('No se pudo guardar la configuración del vendedor.', 'error');
    }
  };

  const handleUpdate = async (v: ConfigVendedor, patch: Partial<{ tipo: TipoVendedor; factor_tipo: number }>) => {
    try {
      await upsertMut.upsert({ vendedorOrigen: v.id_vendedor_origen, tipo: patch.tipo ?? v.tipo, factor_tipo: patch.factor_tipo ?? v.factor_tipo, fecha_ingreso: v.fecha_ingreso });
      toast(`Vendedor ${v.id_vendedor_origen} actualizado.`, 'success');
    } catch {
      toast('No se pudo actualizar el vendedor.', 'error');
    }
  };

  const columns: DataTableColumn<ConfigVendedor>[] = [
    { key: 'id_vendedor_origen', header: 'Vendedor (código SAP)', render: (v) => <span className="font-mono text-slate-200">{v.id_vendedor_origen}</span> },
    {
      key: 'tipo', header: 'Tipo',
      render: (v) => (
        <Select
          size="sm"
          value={v.tipo}
          disabled={upsertMut.pendingVendedor === v.id_vendedor_origen}
          onChange={(e) => handleUpdate(v, { tipo: e.target.value as TipoVendedor, factor_tipo: e.target.value === 'externo' ? 1.0 : 0.70 })}
        >
          <option value="externo">Externo</option>
          <option value="interno">Interno</option>
        </Select>
      ),
    },
    {
      key: 'factor_tipo', header: 'Factor de comisión', numeric: true,
      render: (v) => (
        <input
          type="number" step="0.05" min={0} max={1.5} value={v.factor_tipo}
          disabled={upsertMut.pendingVendedor === v.id_vendedor_origen}
          onChange={(e) => handleUpdate(v, { factor_tipo: parseFloat(e.target.value) || 0 })}
          className="input-field w-20"
        />
      ),
    },
    { key: 'fecha_ingreso', header: 'Fecha de ingreso', render: (v) => <span className="text-slate-500">{v.fecha_ingreso ?? '—'}</span> },
  ];

  return (
    <div className="space-y-4">
      <p className="text-xs text-slate-500">
        Brecha B1 (auditoría 30): `dim_vendedor` no distingue externo/interno. Un vendedor sin configuración explícita
        se asume externo (factor 1.0) -- nunca se penaliza por omisión.
      </p>
      <div className="p-5 bg-slate-800/50 rounded-lg border border-slate-700/50 flex flex-wrap gap-4 items-end">
        <Field label="Código de vendedor">
          <input value={nuevo.vendedor} onChange={(e) => setNuevo({ ...nuevo, vendedor: e.target.value })}
            placeholder="Ej. VEN01" className="input-field w-28" />
        </Field>
        <Field label="Tipo">
          <Select
            value={nuevo.tipo}
            onChange={(e) => {
              const tipo = e.target.value as TipoVendedor;
              setNuevo({ ...nuevo, tipo, factor: tipo === 'externo' ? 1.0 : 0.70 });
            }}
          >
            <option value="externo">Externo</option>
            <option value="interno">Interno</option>
          </Select>
        </Field>
        <Field label="Factor de comisión">
          <input type="number" step="0.05" min={0} max={1.5} value={nuevo.factor}
            onChange={(e) => setNuevo({ ...nuevo, factor: parseFloat(e.target.value) || 0 })} className="input-field w-20" />
        </Field>
        <Button variant="primary" onClick={handleAdd} loading={upsertMut.pendingVendedor !== null} icon={<Users className="w-4 h-4" aria-hidden="true" />}>
          Guardar vendedor
        </Button>
      </div>

      <DataTable
        columns={columns}
        data={vendedores.data}
        rowKey={(v) => v.id_vendedor_origen}
        loading={vendedores.loading}
        error={vendedores.error ?? undefined}
        onRetry={vendedores.refetch}
        emptyTitle="Sin vendedores configurados"
        emptyDescription="Todos se tratan como externos (factor 1.0) hasta que se configuren explícitamente."
      />
    </div>
  );
}

function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="flex flex-col gap-1">
      <label className="text-xs font-semibold text-slate-400">{label}</label>
      {children}
    </div>
  );
}
