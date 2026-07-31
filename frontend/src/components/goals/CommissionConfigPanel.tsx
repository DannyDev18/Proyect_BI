import { useState, type ReactNode } from 'react';
import { Settings, Plus, CreditCard, Users, Pencil, Trash2, X, Percent, Sigma, ArrowUp, ArrowDown } from 'lucide-react';

import {
  useMatrizCategorias, useUpsertMatrizCategoria, useDeleteMatrizCategoria, useFactoresCredito, useReplaceFactoresCredito,
  useConfigVendedores, useUpsertConfigVendedor, useComisionConfigAuditoria,
  useSearchClasesProducto, useSearchVendedoresComision,
  useTramosCobranza, useReplaceTramosCobranza, useFormulas, useReplaceFormulaComponentes,
} from '../../hooks/commissionConfig';
import type {
  ClaseBusqueda, ComisionConfigAuditoriaEntrada, ConfigVendedor, FactorCreditoPayload, GrupoComision,
  MatrizCategoria, TipoVendedor, VendedorBusqueda, TramoCobranzaPayload, FormulaComponentePayload,
  ComponenteFormula, OperadorFormula,
} from '../../types/commissionConfig';
import { Tabs } from '../ui/Tabs';
import { Button } from '../ui/Button';
import { Select } from '../ui/Select';
import { DataTable, type DataTableColumn } from '../ui/DataTable';
import { Badge } from '../ui/Badge';
import { Autocomplete } from '../ui/Autocomplete';
import { ConfirmDialog } from '../ui/ConfirmDialog';
import { useToast } from '../../store/toastStore';
import { getApiErrorMessage } from '../../utils/apiError';

const PERFILES_COBRANZA: TipoVendedor[] = ['externo', 'interno', 'jefe_agencia'];
const PERFIL_LABEL: Record<TipoVendedor, string> = {
  externo: 'Externo', interno: 'Interno', jefe_agencia: 'Jefe de agencia',
};
const COMPONENTE_LABEL: Record<ComponenteFormula, string> = {
  base_lineas_venta: 'Líneas de venta (margen/categoría)',
  base_cobranza: 'Cobranza (por tramo de días de cobro)',
  contado_agencia: 'Ventas de contado de la agencia',
  factor_tipo_vendedor: 'Factor de tipo de vendedor',
  multiplicador_cumplimiento: 'Multiplicador de cumplimiento de meta',
  devoluciones: 'Devoluciones estimadas',
  bonos: 'Bonos (cross-sell, cliente nuevo, cobranza sana)',
};
const OPERADORES: OperadorFormula[] = ['sumar', 'restar', 'multiplicar'];
const OPERADOR_LABEL: Record<OperadorFormula, string> = {
  sumar: '+ Sumar', restar: '− Restar', multiplicar: '× Multiplicar',
};

const GRUPOS: GrupoComision[] = ['A', 'B', 'C', 'S', 'X'];
const GRUPO_VARIANT: Record<GrupoComision, 'success' | 'info' | 'warning' | 'danger'> = {
  A: 'success', B: 'info', C: 'warning', S: 'info', X: 'danger',
};

/** Panel de configuración de gerencia para el sistema de Comisiones Variables
 * (docs/features/plan_integracion_comisiones_variables.md §3.5, Fase 5: "gerencia
 * ajusta la matriz sin programar"). 3 pestañas: matriz de categorías, factores de
 * crédito y tipo de vendedor -- cada una es un CRUD directo contra los endpoints
 * `/gerencia/goals/commission-config/*`. */
export function CommissionConfigPanel() {
  const [tab, setTab] = useState<'matriz' | 'credito' | 'vendedores' | 'cobranza' | 'formula' | 'auditoria'>('matriz');

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
          { value: 'cobranza', label: 'Comisión sobre cobros' },
          { value: 'formula', label: 'Fórmula' },
          { value: 'auditoria', label: 'Bitácora de cambios' },
        ]}
      />

      {tab === 'matriz' && <MatrizTab />}
      {tab === 'credito' && <CreditoTab />}
      {tab === 'vendedores' && <VendedoresTab />}
      {tab === 'cobranza' && <CobranzaTab />}
      {tab === 'formula' && <FormulaTab />}
      {tab === 'auditoria' && <AuditoriaTab />}
    </div>
  );
}

// ── Matriz de categorías ────────────────────────────────────────────────────────
function MatrizTab() {
  const matriz = useMatrizCategorias();
  const upsertMut = useUpsertMatrizCategoria();
  const deleteMut = useDeleteMatrizCategoria();
  const toast = useToast();

  const emptyForm = { clase: '', subclase: '', grupo: 'B' as GrupoComision, tasa_pct: 8, base: 'margen' as 'margen' | 'valor', factor_estrategico: 1.0 };
  const [form, setForm] = useState(emptyForm);
  const [editing, setEditing] = useState<MatrizCategoria | null>(null);
  const [claseQuery, setClaseQuery] = useState('');
  const claseSearch = useSearchClasesProducto(claseQuery);
  const [pendingDelete, setPendingDelete] = useState<MatrizCategoria | null>(null);

  const handleEdit = (r: MatrizCategoria) => {
    setEditing(r);
    setForm({
      clase: r.clase, subclase: r.subclase ?? '', grupo: r.grupo,
      tasa_pct: r.tasa_pct, base: r.base, factor_estrategico: r.factor_estrategico,
    });
  };

  const handleCancelEdit = () => {
    setEditing(null);
    setForm(emptyForm);
  };

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
      toast(editing ? 'Regla de categoría actualizada. La vigencia anterior quedó cerrada.' : 'Regla de categoría guardada.', 'success');
      setEditing(null);
      setForm(emptyForm);
    } catch {
      toast('No se pudo guardar la regla de categoría.', 'error');
    }
  };

  const handleConfirmDelete = async () => {
    if (!pendingDelete) return;
    try {
      await deleteMut.remove(pendingDelete.id);
      toast(`Regla de ${pendingDelete.clase}${pendingDelete.subclase ? ` / ${pendingDelete.subclase}` : ''} eliminada.`, 'success');
      if (editing?.id === pendingDelete.id) handleCancelEdit();
      setPendingDelete(null);
    } catch {
      toast('No se pudo eliminar la regla de categoría.', 'error');
    }
  };

  const columns: DataTableColumn<MatrizCategoria>[] = [
    { key: 'clase', header: 'Clase', headerTitle: 'Código de producto (dim_producto.clase). * = comodín default.', render: (r) => <span className="font-mono text-slate-200">{r.clase}</span> },
    { key: 'subclase', header: 'Subclase', headerTitle: 'Código de subclase; vacío = aplica a toda la clase.', render: (r) => <span className="font-mono text-slate-500">{r.subclase ?? 'Toda la clase'}</span> },
    { key: 'grupo', header: 'Grupo', headerTitle: 'A/B/C = categorías normales, S = servicio, X = excluido (no comisiona).', render: (r) => <Badge variant={GRUPO_VARIANT[r.grupo]}>{r.grupo}</Badge> },
    { key: 'tasa_pct', header: 'Tasa', headerTitle: '% aplicado sobre la base para calcular la comisión de la línea.', numeric: true, render: (r) => <span className="font-mono">{r.tasa_pct.toFixed(2)}%</span> },
    { key: 'base', header: 'Base', headerTitle: 'Monto sobre el que se aplica la tasa: margen bruto o valor de venta.', render: (r) => <span className="text-slate-400">{r.base === 'margen' ? 'Margen bruto' : 'Valor de venta'}</span> },
    { key: 'factor_estrategico', header: 'Factor estratégico', headerTitle: 'Multiplicador 0.5x-1.5x sobre la comisión ya calculada; 1.00x = neutro.', numeric: true, render: (r) => <span className="font-mono">{r.factor_estrategico.toFixed(2)}x</span> },
    { key: 'vigente_desde', header: 'Vigente desde', headerTitle: 'Fecha desde la que rige esta regla; la anterior queda cerrada, nunca se sobreescribe.', render: (r) => <span className="text-slate-500">{r.vigente_desde}</span> },
    {
      key: 'acciones', header: '', render: (r) => (
        <div className="flex items-center gap-1.5">
          <Button variant="ghost" size="sm" onClick={() => handleEdit(r)} icon={<Pencil className="w-3.5 h-3.5" aria-hidden="true" />}>
            Editar
          </Button>
          <Button
            variant="ghost" size="sm" onClick={() => setPendingDelete(r)}
            icon={<Trash2 className="w-3.5 h-3.5" aria-hidden="true" />}
            className="text-danger hover:text-danger"
          >
            Eliminar
          </Button>
        </div>
      ),
    },
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
        {editing && (
          <div className="w-full flex items-center justify-between gap-3 -mb-1">
            <span className="text-xs text-info font-medium">
              Editando regla de {editing.clase}{editing.subclase ? ` / ${editing.subclase}` : ''} — al guardar se cierra la vigencia actual y se crea una nueva.
            </span>
            <button type="button" onClick={handleCancelEdit} className="text-xs text-slate-500 hover:text-slate-300 flex items-center gap-1 cursor-pointer focus-ring rounded">
              <X className="w-3.5 h-3.5" aria-hidden="true" /> Cancelar edición
            </button>
          </div>
        )}
        <Field label="Clase (código)" help="Código de dim_producto.clase, ej. BAT (baterías). Busca por código para elegir la clase; usa '*' como regla comodín escribiéndolo en el buscador.">
          <div className="w-52 flex flex-col gap-1.5">
            {editing ? (
              <div className="input-field w-52 flex items-center font-mono text-slate-300">
                {form.clase}{form.subclase ? ` / ${form.subclase}` : ''}
              </div>
            ) : (
              <>
                <Autocomplete<ClaseBusqueda>
                  placeholder="Buscar clase existente… (o escribe '*' para el comodín)"
                  minChars={1}
                  loading={claseSearch.loading}
                  options={claseSearch.data}
                  getKey={(c) => c.clase}
                  renderOption={(c) => (
                    <span className="flex items-center justify-between gap-3">
                      <span className="font-mono text-slate-200">{c.clase}</span>
                      <span className="text-slate-500 text-xs">{c.productos} producto{c.productos === 1 ? '' : 's'}</span>
                    </span>
                  )}
                  onQueryChange={(q) => { setClaseQuery(q); if (q) setForm({ ...form, clase: q.toUpperCase() }); }}
                  onSelect={(c) => setForm({ ...form, clase: c.clase })}
                />
                {form.clase && <span className="text-xs text-info font-mono">Seleccionada: {form.clase}</span>}
              </>
            )}
          </div>
        </Field>
        <Field label="Subclase (opcional)" help="Código de dim_producto.subclase. Déjalo vacío para que la regla aplique a toda la clase, sin distinguir subclase.">
          <input value={form.subclase} onChange={(e) => setForm({ ...form, subclase: e.target.value })}
            placeholder="Toda la clase" className="input-field w-28" disabled={!!editing} />
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
          {editing ? 'Guardar cambios' : 'Guardar regla'}
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

      <ConfirmDialog
        open={pendingDelete !== null}
        title="Eliminar regla de categoría"
        message={
          pendingDelete && (
            <>
              Se cerrará la vigencia de <span className="font-mono text-slate-200">{pendingDelete.clase}{pendingDelete.subclase ? ` / ${pendingDelete.subclase}` : ''}</span> a
              partir de hoy. Las liquidaciones ya calculadas con esta regla no se ven afectadas (siguen consultándola
              por su fecha histórica); desde ahora esa clase caerá al comodín <code className="font-mono">*</code> si
              existe, o quedará sin regla propia.
            </>
          )
        }
        confirmLabel="Eliminar regla"
        loading={deleteMut.loading}
        onConfirm={handleConfirmDelete}
        onCancel={() => setPendingDelete(null)}
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
    dias_desde: f.dias_desde, dias_hasta: f.dias_hasta, factor: f.factor,
  }));

  const updateRow = (idx: number, patch: Partial<FactorCreditoPayload>) => {
    const next = [...activos];
    next[idx] = { ...next[idx], ...patch };
    setRows(next);
  };

  const addRow = () => setRows([...activos, { dias_desde: 0, dias_hasta: null, factor: 1.0 }]);
  const removeRow = (idx: number) => setRows(activos.filter((_, i) => i !== idx));

  const handleSave = async () => {
    try {
      await replaceMut.replace(activos);
      toast('Matriz de crédito actualizada.', 'success');
      setRows(null);
    } catch (err) {
      toast(getApiErrorMessage(err) ?? 'No se pudo guardar la matriz de crédito.', 'error');
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
              <th className="px-4 py-2" title="Multiplicador (0-2.0x) que se aplica a la comisión de la línea. 1.00 = sin penalización; menor a 1 reduce la comisión por el riesgo de cobranza a más plazo, mayor a 1 la premia.">Factor</th>
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
                  <input type="number" step="0.01" min={0} max={2} value={r.factor} className="input-field w-20"
                    onChange={(e) => updateRow(idx, { factor: parseFloat(e.target.value) || 0 })} />
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
  const [nuevo, setNuevo] = useState({ vendedor: '', tipo: 'externo' as TipoVendedor, factor: 1.0, agencia: '' });
  const [nuevoNombre, setNuevoNombre] = useState<string | null>(null);
  const [vendedorQuery, setVendedorQuery] = useState('');
  const vendedorSearch = useSearchVendedoresComision(vendedorQuery);

  const handleAdd = async () => {
    if (!nuevo.vendedor.trim()) {
      toast('El código de vendedor (id_vendedor_origen) es obligatorio.', 'error');
      return;
    }
    if (nuevo.tipo === 'jefe_agencia' && !nuevo.agencia.trim()) {
      toast("El perfil 'Jefe de agencia' requiere indicar la agencia.", 'error');
      return;
    }
    try {
      await upsertMut.upsert({
        vendedorOrigen: nuevo.vendedor.trim(), tipo: nuevo.tipo, factor_tipo: nuevo.factor,
        agencia: nuevo.tipo === 'jefe_agencia' ? nuevo.agencia.trim() : null,
      });
      toast('Configuración de vendedor guardada.', 'success');
      setNuevo({ vendedor: '', tipo: 'externo', factor: 1.0, agencia: '' });
      setNuevoNombre(null);
    } catch (err) {
      toast(getApiErrorMessage(err) ?? 'No se pudo guardar la configuración del vendedor.', 'error');
    }
  };

  const handleUpdate = async (v: ConfigVendedor, patch: Partial<{ tipo: TipoVendedor; factor_tipo: number; agencia: string | null }>) => {
    if ((patch.tipo ?? v.tipo) === 'jefe_agencia' && !(patch.agencia ?? v.agencia)) {
      toast("El perfil 'Jefe de agencia' requiere indicar la agencia.", 'error');
      return;
    }
    try {
      await upsertMut.upsert({
        vendedorOrigen: v.id_vendedor_origen, tipo: patch.tipo ?? v.tipo, factor_tipo: patch.factor_tipo ?? v.factor_tipo,
        fecha_ingreso: v.fecha_ingreso, agencia: patch.agencia !== undefined ? patch.agencia : v.agencia,
      });
      toast(`Vendedor ${v.id_vendedor_origen} actualizado.`, 'success');
    } catch (err) {
      toast(getApiErrorMessage(err) ?? 'No se pudo actualizar el vendedor.', 'error');
    }
  };

  const columns: DataTableColumn<ConfigVendedor>[] = [
    { key: 'id_vendedor_origen', header: 'Vendedor (código SAP)', render: (v) => <span className="font-mono text-slate-200">{v.id_vendedor_origen}</span> },
    { key: 'nombre_vendedor', header: 'Nombre', render: (v) => <span className="text-slate-300">{v.nombre_vendedor ?? '—'}</span> },
    {
      key: 'tipo', header: 'Tipo',
      render: (v) => (
        <Select
          size="sm"
          value={v.tipo}
          disabled={upsertMut.pendingVendedor === v.id_vendedor_origen}
          onChange={(e) => {
            const tipo = e.target.value as TipoVendedor;
            handleUpdate(v, { tipo, factor_tipo: tipo === 'externo' ? 1.0 : 0.70 });
          }}
        >
          <option value="externo">Externo</option>
          <option value="interno">Interno</option>
          <option value="jefe_agencia">Jefe de agencia</option>
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
    {
      key: 'agencia', header: 'Agencia', headerTitle: 'establ -- solo aplica a Jefe de agencia (componente "ventas de contado de la agencia").',
      render: (v) => v.tipo === 'jefe_agencia' ? (
        <input
          type="text" maxLength={3} value={v.agencia ?? ''}
          disabled={upsertMut.pendingVendedor === v.id_vendedor_origen}
          onChange={(e) => handleUpdate(v, { agencia: e.target.value.trim() || null })}
          className="input-field w-16 font-mono"
        />
      ) : <span className="text-slate-600">N/A</span>,
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
        <Field label="Código de vendedor" help="id_vendedor_origen tal como aparece en el ERP (dim_vendedor). Busca por código o nombre para identificar a quién pertenece.">
          <div className="w-56 flex flex-col gap-1.5">
            <Autocomplete<VendedorBusqueda>
              placeholder="Buscar por código o nombre…"
              loading={vendedorSearch.loading}
              options={vendedorSearch.data}
              getKey={(v) => v.codven}
              renderOption={(v) => (
                <span className="flex items-center justify-between gap-3">
                  <span className="font-mono text-slate-200">{v.codven}</span>
                  <span className="text-slate-500 text-xs truncate">{v.nombre_vendedor ?? 'Sin nombre'}</span>
                </span>
              )}
              onQueryChange={setVendedorQuery}
              onSelect={(v) => { setNuevo({ ...nuevo, vendedor: v.codven }); setNuevoNombre(v.nombre_vendedor); }}
            />
            {nuevo.vendedor && (
              <span className="text-xs text-info font-mono">
                Seleccionado: {nuevo.vendedor}{nuevoNombre ? ` — ${nuevoNombre}` : ''}
              </span>
            )}
          </div>
        </Field>
        <Field label="Tipo" help="Externo = vendedor de campo/distribuidor (factor típico 1.0x); Interno = vendedor de mostrador/oficina (factor típico 0.70x); Jefe de agencia = perfil real de la empresa (auditoría 44), con tramos de cobranza propios y 1% de las ventas de contado de SU agencia.">
          <Select
            value={nuevo.tipo}
            onChange={(e) => {
              const tipo = e.target.value as TipoVendedor;
              setNuevo({ ...nuevo, tipo, factor: tipo === 'externo' ? 1.0 : 0.70 });
            }}
          >
            <option value="externo">Externo</option>
            <option value="interno">Interno</option>
            <option value="jefe_agencia">Jefe de agencia</option>
          </Select>
        </Field>
        <Field label="Factor de comisión" help="Multiplicador (0-1.5x) sobre el total de comisión del vendedor en el mes. 1.00x = sin ajuste por tipo.">
          <input type="number" step="0.05" min={0} max={1.5} value={nuevo.factor}
            onChange={(e) => setNuevo({ ...nuevo, factor: parseFloat(e.target.value) || 0 })} className="input-field w-20" />
        </Field>
        {nuevo.tipo === 'jefe_agencia' && (
          <Field label="Agencia (establ)" help="Código de sucursal (edw.dim_sucursal.establ) de la agencia que este jefe supervisa -- base del componente de ventas de contado.">
            <input type="text" maxLength={3} value={nuevo.agencia}
              onChange={(e) => setNuevo({ ...nuevo, agencia: e.target.value })} className="input-field w-20 font-mono" placeholder="003" />
          </Field>
        )}
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

// ── Comisión sobre COBROS (auditoría 44, docs/features/plan_comisiones_sobre_cobros.md) ──
function CobranzaTab() {
  const tramos = useTramosCobranza();
  const replaceMut = useReplaceTramosCobranza();
  const toast = useToast();
  const [perfil, setPerfil] = useState<TipoVendedor>('externo');
  const [rows, setRows] = useState<TramoCobranzaPayload[] | null>(null);

  const vigentes = tramos.data[perfil] ?? [];
  const activos = rows ?? vigentes.map((t) => ({ dias_hasta: t.dias_hasta, tasa_pct: t.tasa_pct }));

  const handleSelectPerfil = (p: TipoVendedor) => {
    setPerfil(p);
    setRows(null);
  };

  const updateRow = (idx: number, patch: Partial<TramoCobranzaPayload>) => {
    const next = [...activos];
    next[idx] = { ...next[idx], ...patch };
    setRows(next);
  };
  const addRow = () => setRows([...activos, { dias_hasta: null, tasa_pct: 0 }]);
  const removeRow = (idx: number) => setRows(activos.filter((_, i) => i !== idx));

  const handleSave = async () => {
    try {
      await replaceMut.replace({ perfil, tramos: activos });
      toast(`Tramos de cobranza de "${PERFIL_LABEL[perfil]}" actualizados.`, 'success');
      setRows(null);
    } catch (err) {
      toast(getApiErrorMessage(err) ?? 'No se pudo guardar los tramos de cobranza.', 'error');
    }
  };

  return (
    <div className="space-y-4">
      <p className="text-xs text-slate-500">
        Regla realmente vigente en la empresa (auditoría 44, docs/auditoria/44_comisiones_sobre_cobros.md): la
        comisión se calcula sobre la COBRANZA efectivamente realizada (no sobre la venta facturada), según los días
        transcurridos entre la emisión de la factura y la fecha en que el cobro se hace efectivo. Los cheques
        postfechados comisionan en el mes en que se COBRAN, no en el que se reciben. Estos tramos solo se aplican si
        la fórmula vigente (pestaña "Fórmula") incluye el componente "Cobranza".
      </p>
      <div className="flex gap-2">
        {PERFILES_COBRANZA.map((p) => (
          <button
            key={p} type="button" onClick={() => handleSelectPerfil(p)}
            className={`px-3 py-1.5 rounded-md text-sm font-medium cursor-pointer transition-colors focus-ring ${
              perfil === p ? 'bg-info/20 text-info border border-info/40' : 'bg-slate-800/50 text-slate-400 border border-slate-700/50 hover:text-slate-200'
            }`}
          >
            {PERFIL_LABEL[p]}
          </button>
        ))}
      </div>
      <div className="card overflow-hidden">
        <table className="w-full text-left text-sm">
          <thead className="bg-slate-950/60 text-slate-500 text-xs uppercase tracking-widest">
            <tr>
              <th className="px-4 py-2" title="Techo del tramo en días de cobro (banfec - fecemi). Vacío = sin tope superior.">Días hasta</th>
              <th className="px-4 py-2" title="Porcentaje de comisión sobre lo cobrado dentro de este tramo.">Tasa %</th>
              <th className="px-4 py-2 text-right">Acciones</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-800/80">
            {activos.map((r, idx) => (
              <tr key={idx}>
                <td className="px-4 py-2">
                  <input type="number" min={0} value={r.dias_hasta ?? ''} placeholder="Sin tope" className="input-field w-24"
                    onChange={(e) => updateRow(idx, { dias_hasta: e.target.value ? parseInt(e.target.value) : null })} />
                </td>
                <td className="px-4 py-2">
                  <input type="number" step="0.01" min={0} max={100} value={r.tasa_pct} className="input-field w-20"
                    onChange={(e) => updateRow(idx, { tasa_pct: parseFloat(e.target.value) || 0 })} />
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
        <Button variant="primary" onClick={handleSave} loading={replaceMut.loading} icon={<Percent className="w-4 h-4" aria-hidden="true" />}>
          Guardar tramos de "{PERFIL_LABEL[perfil]}"
        </Button>
      </div>
    </div>
  );
}

// ── Fórmula de comisión (auditoría 44 §2.2: estructura editable, no quemada) ─────
// Corrección de diseño (petición explícita del usuario): las Comisiones Variables son
// UN SOLO TOTAL por vendedor -- líneas de venta + cobranza + contado de agencia se
// SUMAN, nunca se elige entre "un esquema u otro". Hay una única fórmula (sin
// selector ni botón "activar"); lo único editable es su estructura (qué componentes
// suma/resta/multiplica y en qué orden).
function FormulaTab() {
  const formulas = useFormulas();
  const replaceMut = useReplaceFormulaComponentes();
  const toast = useToast();
  const formula = formulas.data.formulas[0] ?? null;
  const [editando, setEditando] = useState(false);
  const [componentes, setComponentes] = useState<FormulaComponentePayload[]>([]);

  // El orden se gestiona SOLO por la posición en la lista (botones subir/bajar) -- nunca
  // como número editable a mano: dejarlo editable era la causa más común de que "no
  // guarde" (dos filas con el mismo número de orden, rechazado por el backend sin que el
  // usuario entendiera por qué). Al guardar se renumera 1..N según el orden visual.
  const renumerar = (lista: FormulaComponentePayload[]) => lista.map((c, i) => ({ ...c, orden: i + 1 }));

  const handleEdit = () => {
    if (!formula) return;
    setEditando(true);
    setComponentes(renumerar(formula.componentes.map((c) => ({
      orden: c.orden, componente: c.componente, operador: c.operador, activo: c.activo, parametros: c.parametros,
    }))));
  };

  const updateComponente = (idx: number, patch: Partial<FormulaComponentePayload>) => {
    const next = [...componentes];
    next[idx] = { ...next[idx], ...patch };
    setComponentes(next);
  };
  const addComponente = () => setComponentes(renumerar([
    ...componentes,
    { orden: 0, componente: formulas.data.catalogo_componentes[0], operador: 'sumar', activo: true, parametros: {} },
  ]));
  const removeComponente = (idx: number) => setComponentes(renumerar(componentes.filter((_, i) => i !== idx)));
  const moveComponente = (idx: number, direccion: -1 | 1) => {
    const destino = idx + direccion;
    if (destino < 0 || destino >= componentes.length) return;
    const next = [...componentes];
    [next[idx], next[destino]] = [next[destino], next[idx]];
    setComponentes(renumerar(next));
  };

  const handleSave = async () => {
    if (!formula) return;
    try {
      await replaceMut.replace({ formulaId: formula.id, componentes });
      toast('Fórmula actualizada.', 'success');
      setEditando(false);
    } catch (err) {
      toast(getApiErrorMessage(err) ?? 'No se pudo guardar la fórmula.', 'error');
    }
  };

  if (!formula) {
    return <p className="text-sm text-slate-500">Sin fórmula configurada.</p>;
  }

  return (
    <div className="space-y-5">
      <p className="text-xs text-slate-500">
        Las Comisiones Variables son UN SOLO TOTAL por vendedor: las líneas de venta (margen/categoría), la cobranza
        (por tramo de días de cobro) y las ventas de contado de agencia se SUMAN -- no son esquemas alternativos entre
        los que se elige. Lo que sí es configuración (no código) es la ESTRUCTURA de esa suma: qué componentes
        participan, en qué orden y con qué operador.
      </p>
      <div className="p-4 rounded-lg border border-info/50 bg-info/10">
        <div className="flex items-center justify-between gap-3 mb-3">
          <span className="font-semibold text-slate-100">{formula.nombre}</span>
          {editando ? (
            <button type="button" onClick={() => setEditando(false)} className="text-xs text-slate-500 hover:text-slate-300 flex items-center gap-1 cursor-pointer focus-ring rounded">
              <X className="w-3.5 h-3.5" aria-hidden="true" /> Cancelar
            </button>
          ) : (
            <Button variant="ghost" size="sm" onClick={handleEdit} icon={<Pencil className="w-3.5 h-3.5" aria-hidden="true" />}>
              Editar componentes
            </Button>
          )}
        </div>

        {editando ? (
          <div className="space-y-3">
            <table className="w-full text-left text-sm">
              <thead className="text-slate-500 text-xs uppercase tracking-widest">
                <tr>
                  <th className="py-1 pr-2" title="Sube o baja el paso con las flechas -- el orden se renumera solo.">Orden</th>
                  <th className="py-1 pr-2">Componente</th>
                  <th className="py-1 pr-2" title="+ suma este componente al total, − lo resta, × multiplica el total acumulado hasta este paso.">Operador</th>
                  <th className="py-1 pr-2" title="Si está desmarcado, este paso se ignora en el cálculo (queda guardado, pero no participa).">Activo</th>
                  <th className="py-1 pr-2 text-right">Acciones</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800/60">
                {componentes.map((c, idx) => (
                  <tr key={idx}>
                    <td className="py-1.5 pr-2">
                      <div className="flex items-center gap-1">
                        <span className="w-5 text-center text-slate-500 font-mono">{c.orden}</span>
                        <button type="button" disabled={idx === 0} onClick={() => moveComponente(idx, -1)}
                          className="p-1 rounded text-slate-400 hover:text-slate-100 disabled:opacity-20 disabled:cursor-not-allowed cursor-pointer focus-ring">
                          <ArrowUp className="w-3.5 h-3.5" aria-hidden="true" />
                        </button>
                        <button type="button" disabled={idx === componentes.length - 1} onClick={() => moveComponente(idx, 1)}
                          className="p-1 rounded text-slate-400 hover:text-slate-100 disabled:opacity-20 disabled:cursor-not-allowed cursor-pointer focus-ring">
                          <ArrowDown className="w-3.5 h-3.5" aria-hidden="true" />
                        </button>
                      </div>
                    </td>
                    <td className="py-1.5 pr-2">
                      <Select size="sm" value={c.componente} onChange={(e) => updateComponente(idx, { componente: e.target.value as ComponenteFormula })}>
                        {formulas.data.catalogo_componentes.map((cc) => (
                          <option key={cc} value={cc}>{COMPONENTE_LABEL[cc] ?? cc}</option>
                        ))}
                      </Select>
                    </td>
                    <td className="py-1.5 pr-2">
                      <Select size="sm" value={c.operador} onChange={(e) => updateComponente(idx, { operador: e.target.value as OperadorFormula })}>
                        {OPERADORES.map((op) => <option key={op} value={op}>{OPERADOR_LABEL[op]}</option>)}
                      </Select>
                    </td>
                    <td className="py-1.5 pr-2">
                      <input type="checkbox" checked={c.activo} onChange={(e) => updateComponente(idx, { activo: e.target.checked })} className="w-4 h-4" />
                    </td>
                    <td className="py-1.5 pr-2 text-right">
                      <Button variant="danger" size="sm" onClick={() => removeComponente(idx)}>Quitar</Button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            <div className="flex gap-3">
              <Button variant="ghost" size="sm" onClick={addComponente} icon={<Plus className="w-4 h-4" aria-hidden="true" />}>Agregar componente</Button>
              <Button variant="primary" size="sm" onClick={handleSave} loading={replaceMut.loading} icon={<Sigma className="w-4 h-4" aria-hidden="true" />}>
                Guardar componentes
              </Button>
            </div>
          </div>
        ) : (
          <ol className="text-sm text-slate-400 space-y-1 list-decimal list-inside">
            {formula.componentes.filter((c) => c.activo).map((c) => (
              <li key={c.id}>
                <span className="text-slate-300">{c.operador === 'sumar' ? '+ ' : c.operador === 'restar' ? '− ' : '× '}</span>
                {COMPONENTE_LABEL[c.componente] ?? c.componente}
              </li>
            ))}
          </ol>
        )}
      </div>
    </div>
  );
}

// ── Bitácora de cambios (Fase 2 ítem 2) ──────────────────────────────────────────
const TABLA_LABEL: Record<string, string> = {
  comision_matriz_categorias: 'Matriz de categorías',
  comision_factores_credito: 'Factores de crédito',
  comision_config_vendedor: 'Tipo de vendedor',
  comision_tramos_cobranza: 'Comisión sobre cobros',
  comision_formula: 'Fórmula',
};

const ACCION_LABEL: Record<string, string> = {
  upsert: 'Creó/actualizó',
  replace: 'Reemplazó',
  reemplazar_componentes: 'Reemplazó componentes',
  activar: 'Activó',
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
