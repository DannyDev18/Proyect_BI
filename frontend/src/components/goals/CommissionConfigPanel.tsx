import { useState, type ReactNode } from 'react';
import { Settings, Plus, CreditCard, Users } from 'lucide-react';

import {
  useMatrizCategorias, useUpsertMatrizCategoria, useFactoresCredito, useReplaceFactoresCredito,
  useConfigVendedores, useUpsertConfigVendedor, useComisionConfigAuditoria,
} from '../../hooks/commissionConfig';
import type {
  ComisionConfigAuditoriaEntrada, ConfigVendedor, FactorCreditoPayload, GrupoComision, MatrizCategoria, TipoVendedor,
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
  const [tab, setTab] = useState<'matriz' | 'credito' | 'vendedores' | 'auditoria'>('matriz');

  return (
    <div className="p-6 bg-slate-900 text-white rounded-lg border border-slate-800 shadow-xl max-w-7xl mx-auto">
      <div className="flex items-center gap-3 mb-4">
        <Settings className="w-8 h-8 text-info" aria-hidden="true" />
        <div>
          <h2 className="text-2xl font-bold tracking-tight">Configuración de Comisiones Variables</h2>
          <p className="text-sm text-slate-500 mt-0.5">
            Matriz de categorías, plazos de crédito y tipo de vendedor -- editable sin desarrollo.
          </p>
        </div>
      </div>

      <div className="p-4 mb-5 bg-info/30 border border-info/50 rounded-lg text-sm text-slate-300 space-y-1.5">
        <p className="font-semibold text-info">¿Cómo se arma la comisión de una línea de venta?</p>
        <p className="font-mono text-xs text-slate-400">
          comisión = base_comisionable × tasa × factor_estratégico × factor_de_crédito
        </p>
        <p>
          Eso se suma para todas las líneas del vendedor en el mes, se multiplica por su{' '}
          <span className="text-slate-200 font-medium">factor de tipo</span> (pestaña "Tipo de vendedor") y por el{' '}
          <span className="text-slate-200 font-medium">multiplicador de cumplimiento de meta</span> (100%+ paga más,
          menos de 80% castiga fuerte), y al final se restan devoluciones estimadas y se suman bonos. Cada pestaña de
          abajo configura uno de los factores de esa fórmula.
        </p>
      </div>

      <Tabs
        className="mb-5"
        value={tab}
        onChange={(v) => setTab(v as typeof tab)}
        items={[
          { value: 'matriz', label: 'Matriz de categorías' },
          { value: 'credito', label: 'Factores de crédito' },
          { value: 'vendedores', label: 'Tipo de vendedor' },
          { value: 'auditoria', label: 'Bitácora de cambios' },
        ]}
      />

      {tab === 'matriz' && <MatrizTab />}
      {tab === 'credito' && <CreditoTab />}
      {tab === 'vendedores' && <VendedoresTab />}
      {tab === 'auditoria' && <AuditoriaTab />}
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
    { key: 'clase', header: 'Clase', headerTitle: 'Código de producto (dim_producto.clase). * = comodín default.', render: (r) => <span className="font-mono text-slate-200">{r.clase}</span> },
    { key: 'subclase', header: 'Subclase', headerTitle: 'Código de subclase; vacío = aplica a toda la clase.', render: (r) => <span className="font-mono text-slate-500">{r.subclase ?? 'Toda la clase'}</span> },
    { key: 'grupo', header: 'Grupo', headerTitle: 'A/B/C = categorías normales, S = servicio, X = excluido (no comisiona).', render: (r) => <AlertBadge variant={GRUPO_VARIANT[r.grupo]}>{r.grupo}</AlertBadge> },
    { key: 'tasa_pct', header: 'Tasa', headerTitle: '% aplicado sobre la base para calcular la comisión de la línea.', numeric: true, render: (r) => <span className="font-mono">{r.tasa_pct.toFixed(2)}%</span> },
    { key: 'base', header: 'Base', headerTitle: 'Monto sobre el que se aplica la tasa: margen bruto o valor de venta.', render: (r) => <span className="text-slate-400">{r.base === 'margen' ? 'Margen bruto' : 'Valor de venta'}</span> },
    { key: 'factor_estrategico', header: 'Factor estratégico', headerTitle: 'Multiplicador 0.5x-1.5x sobre la comisión ya calculada; 1.00x = neutro.', numeric: true, render: (r) => <span className="font-mono">{r.factor_estrategico.toFixed(2)}x</span> },
    { key: 'vigente_desde', header: 'Vigente desde', headerTitle: 'Fecha desde la que rige esta regla; la anterior queda cerrada, nunca se sobreescribe.', render: (r) => <span className="text-slate-500">{r.vigente_desde}</span> },
  ];

  return (
    <div className="space-y-5">
      <p className="text-xs text-slate-500">
        Cada fila define, para un tipo de producto, cuánto y sobre qué base comisiona. La regla más específica gana:
        (clase + subclase) exacta &gt; clase entera &gt; comodín <code className="font-mono">*</code> (default cuando
        el producto no matchea ninguna regla). Grupo <span className="font-mono">S</span> = servicio (siempre
        comisiona sobre valor de venta, no tiene margen); grupo <span className="font-mono">X</span> = excluido, no
        comisiona nunca (ej. líneas de regalo/promoción).
      </p>
      <div className="p-5 bg-slate-800/50 rounded-lg border border-slate-700/50 flex flex-wrap gap-4 items-end">
        <Field label="Clase (código)" help="Código de dim_producto.clase, ej. BAT (baterías). '*' = regla comodín que aplica cuando ningún otro código coincide.">
          <input value={form.clase} onChange={(e) => setForm({ ...form, clase: e.target.value })}
            placeholder="Ej. BAT / *" className="input-field w-28" />
        </Field>
        <Field label="Subclase (opcional)" help="Código de dim_producto.subclase. Déjalo vacío para que la regla aplique a toda la clase, sin distinguir subclase.">
          <input value={form.subclase} onChange={(e) => setForm({ ...form, subclase: e.target.value })}
            placeholder="Toda la clase" className="input-field w-28" />
        </Field>
        <Field label="Grupo" help="Etiqueta de negocio para reportes y reglas especiales: A/B/C son categorías normales (más alta = mayor prioridad estratégica), S = servicio, X = excluido de comisión.">
          <Select value={form.grupo} onChange={(e) => setForm({ ...form, grupo: e.target.value as GrupoComision })}>
            {GRUPOS.map((g) => <option key={g} value={g}>{g}</option>)}
          </Select>
        </Field>
        <Field label="Tasa (%)" help="Porcentaje que se aplica sobre la base elegida para calcular la comisión de esta línea.">
          <input type="number" step="0.1" min={0} max={100} value={form.tasa_pct}
            onChange={(e) => setForm({ ...form, tasa_pct: parseFloat(e.target.value) || 0 })} className="input-field w-20" />
        </Field>
        <Field label="Base" help="Sobre qué monto de la línea se aplica la tasa: Margen bruto (venta - costo, incentiva rentabilidad) o Valor de venta (monto bruto vendido, sin considerar costo).">
          <Select value={form.base} onChange={(e) => setForm({ ...form, base: e.target.value as 'margen' | 'valor' })}>
            <option value="margen">Margen bruto</option>
            <option value="valor">Valor de venta</option>
          </Select>
        </Field>
        <Field label="Factor estratégico" help="Multiplicador adicional (0.5x-1.5x) sobre la comisión ya calculada, para incentivar (>1x) o desincentivar (<1x) esta categoría sin tocar la tasa base. 1.00x = neutro.">
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
        Cada tramo penaliza (o no) la comisión de una línea según a cuántos días de plazo se vendió a crédito: más
        días de plazo para el cliente suele significar factor más bajo, porque el dinero tarda más en entrar. El
        motor busca el tramo donde cae <span className="font-mono">dias_plazo</span> de la venta y multiplica la
        comisión de esa línea por su <span className="font-mono">Factor</span>. Auditoría 30 (H4): el EDW actual solo
        registra tráfico real en 0 y 30 días de plazo -- los demás tramos son configuración disponible sin historial
        que la respalde todavía.
      </p>
      <div className="card overflow-hidden">
        <table className="w-full text-left text-sm">
          <thead className="bg-slate-950/60 text-slate-500 text-xs uppercase tracking-widest">
            <tr>
              <th className="px-4 py-2" title="Desde cuántos días de plazo de crédito empieza a aplicar este tramo (inclusive).">Días desde</th>
              <th className="px-4 py-2" title="Hasta cuántos días de plazo aplica este tramo (inclusive). Vacío = sin tope superior.">Días hasta</th>
              <th className="px-4 py-2" title="Multiplicador (0-1.5x) que se aplica a la comisión de la línea. 1.00 = sin penalización; menor a 1 reduce la comisión por el riesgo de cobranza a más plazo.">Factor</th>
              <th className="px-4 py-2" title="Reservado para una fase futura (split anticipo al facturar vs. al cobrar). Todavía no afecta el cálculo de comisión: dejar en 100.">% al facturar (no usado aún)</th>
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
        Este es el ÚLTIMO factor que se aplica: multiplica la suma de comisiones de todas las líneas del vendedor en
        el mes (después de tasa/base/factor estratégico/factor de crédito), antes del ajuste por cumplimiento de
        meta. Brecha B1 (auditoría 30): `dim_vendedor` no distingue externo/interno. Un vendedor sin configuración
        explícita se asume externo (factor 1.0) -- nunca se penaliza por omisión.
      </p>
      <div className="p-5 bg-slate-800/50 rounded-lg border border-slate-700/50 flex flex-wrap gap-4 items-end">
        <Field label="Código de vendedor" help="id_vendedor_origen tal como aparece en el ERP (dim_vendedor), no el nombre de la persona.">
          <input value={nuevo.vendedor} onChange={(e) => setNuevo({ ...nuevo, vendedor: e.target.value })}
            placeholder="Ej. VEN01" className="input-field w-28" />
        </Field>
        <Field label="Tipo" help="Externo = vendedor de campo/distribuidor (factor típico 1.0x); Interno = vendedor de mostrador/oficina (factor típico 0.70x, suele tener menor riesgo/esfuerzo comercial).">
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
        <Field label="Factor de comisión" help="Multiplicador (0-1.5x) sobre el total de comisión del vendedor en el mes. 1.00x = sin ajuste por tipo.">
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

// ── Bitácora de cambios (Fase 2 ítem 2) ──────────────────────────────────────────
const TABLA_LABEL: Record<string, string> = {
  comision_matriz_categorias: 'Matriz de categorías',
  comision_factores_credito: 'Factores de crédito',
  comision_config_vendedor: 'Tipo de vendedor',
};

const ACCION_LABEL: Record<string, string> = {
  upsert: 'Creó/actualizó',
  replace: 'Reemplazó',
};

function formatDetalle(detalle: Record<string, unknown>): string {
  if ('factores' in detalle && Array.isArray(detalle.factores)) {
    return `${detalle.factores.length} rango(s) de crédito`;
  }
  return Object.entries(detalle)
    .filter(([k]) => k !== 'id')
    .map(([k, v]) => `${k}=${v}`)
    .join(', ');
}

function AuditoriaTab() {
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
    <div className="space-y-4">
      <p className="text-sm text-slate-500">
        Quién cambió qué factor y cuándo -- append-only, no se puede editar ni borrar (últimas {auditoria.data.length}).
      </p>
      <DataTable
        columns={columns}
        data={auditoria.data}
        rowKey={(a) => a.id}
        loading={auditoria.loading}
        error={auditoria.error ?? undefined}
        onRetry={auditoria.refetch}
        density="compact"
        emptyTitle="Sin cambios registrados todavía"
        emptyDescription="Cada ajuste de matriz, crédito o tipo de vendedor queda registrado aquí."
      />
    </div>
  );
}

function Field({ label, help, children }: { label: string; help?: string; children: ReactNode }) {
  return (
    <div className="flex flex-col gap-1">
      <label className="text-xs font-semibold text-slate-400" title={help}>
        {label}
        {help && <span className="ml-1 text-slate-600 cursor-help" aria-hidden="true">ⓘ</span>}
      </label>
      {children}
    </div>
  );
}
