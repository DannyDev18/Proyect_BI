import { useState } from 'react';
import { PhoneCall, TrendingDown, AlertTriangle, ShoppingBag } from 'lucide-react';
import { KpiCard, KpiCardSkeleton } from '../components/ui/KpiCard';
import { DataTable } from '../components/ui/DataTable';
import { Drawer } from '../components/ui/Drawer';
import { Button } from '../components/ui/Button';
import { useListaTrabajo, useDetalleCliente, useRegistrarGestion, useTasaRecuperacion } from '../hooks/cartera360';
import type { ClienteListaTrabajo, EventoGestion } from '../types/cartera360';
import { fmt, fmtMoney, pct } from '../utils/format';

export const VentasCartera360 = () => {
  const [clienteSeleccionado, setClienteSeleccionado] = useState<ClienteListaTrabajo | null>(null);
  const [soloRiesgoAlto, setSoloRiesgoAlto] = useState(false);

  const lista = useListaTrabajo();
  const tasa = useTasaRecuperacion();
  const detalle = useDetalleCliente(clienteSeleccionado?.cliente_id ?? null);
  const gestion = useRegistrarGestion();

  const clientes = lista.data?.clientes ?? [];
  const conAlerta = clientes.filter((c) => c.alerta_caida_frecuencia).length;
  const clientesFiltrados = soloRiesgoAlto ? clientes.filter((c) => c.riesgo_alto) : clientes;

  const registrar = (evento: EventoGestion) => {
    if (!clienteSeleccionado) return;
    gestion.execute({ cliente_id: clienteSeleccionado.cliente_id, evento });
    setClienteSeleccionado(null);
  };

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap justify-between items-center gap-3 animate-fade-in">
        <div>
          <h1 className="text-3xl font-display font-semibold text-slate-100">Cartera de Clientes 360</h1>
          <p className="text-sm text-slate-500 mt-0.5">
            A quién llamar hoy y con qué oferta — priorizado por valor histórico × riesgo de fuga real (churn_rf)
          </p>
        </div>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        {lista.loading ? (
          Array.from({ length: 3 }).map((_, i) => <KpiCardSkeleton key={i} />)
        ) : (
          <>
            <KpiCard title="Clientes en la lista" value={clientes.length} icon={ShoppingBag} />
            <KpiCard
              title="Con caída de frecuencia"
              value={conAlerta}
              icon={AlertTriangle}
              trend={conAlerta > 0 ? 'down' : 'neutral'}
            />
            <KpiCard
              title="Tasa de recuperación"
              value={tasa.data ? pct(tasa.data.tasa_recuperacion_pct) : '—'}
              subValue={tasa.data ? `${tasa.data.recompras}/${tasa.data.total_gestiones} gestiones` : undefined}
              icon={TrendingDown}
            />
          </>
        )}
      </div>

      <div className="card p-6">
        <div className="flex flex-wrap justify-between items-center gap-3 mb-4">
          <h3 className="text-base font-semibold text-slate-200">Lista de trabajo diaria</h3>
          <label className="flex items-center gap-2 text-sm text-slate-300">
            <input
              type="checkbox"
              checked={soloRiesgoAlto}
              onChange={(e) => setSoloRiesgoAlto(e.target.checked)}
              className="rounded border-slate-700 bg-slate-950 text-primary focus-ring"
            />
            Solo riesgo alto
          </label>
        </div>
        <DataTable
          columns={[
            {
              key: 'nombre_cliente', header: 'Cliente',
              render: (r) => (
                <button className="text-left text-primary hover:underline" onClick={() => setClienteSeleccionado(r)}>
                  {r.nombre_cliente}
                  {r.alerta_caida_frecuencia && (
                    <AlertTriangle size={12} className="inline ml-1.5 text-warning" />
                  )}
                </button>
              ),
            },
            { key: 'valor_historico', header: 'Valor histórico', numeric: true, render: (r) => fmtMoney(r.valor_historico) },
            {
              key: 'probabilidad_abandono', header: 'Riesgo de fuga', numeric: true,
              render: (r) => (
                <span className={r.probabilidad_abandono > 50 ? 'text-danger font-semibold' : undefined}>
                  {pct(r.probabilidad_abandono)}
                </span>
              ),
            },
            { key: 'dias_sin_comprar', header: 'Días sin comprar', numeric: true, render: (r) => r.dias_sin_comprar },
            {
              key: 'frecuencia_promedio_dias', header: 'Frecuencia habitual', numeric: true,
              render: (r) => (r.frecuencia_promedio_dias ? `cada ${fmt(r.frecuencia_promedio_dias)} días` : '—'),
            },
            { key: 'num_compras', header: 'Compras', numeric: true, render: (r) => r.num_compras },
          ]}
          data={clientesFiltrados}
          rowKey={(r) => r.cliente_id}
          loading={lista.loading}
          error={lista.error ?? undefined}
          density="compact"
          rowClassName={(r) => (r.alerta_caida_frecuencia ? 'bg-warning/5' : '')}
        />
      </div>

      <Drawer
        open={!!clienteSeleccionado}
        onClose={() => setClienteSeleccionado(null)}
        title={clienteSeleccionado?.nombre_cliente ?? ''}
      >
        {detalle.loading ? (
          <div className="skeleton h-40 rounded" />
        ) : detalle.error ? (
          <p className="text-sm text-danger">{detalle.error}</p>
        ) : detalle.data ? (
          <div className="space-y-5">
            <div className="grid grid-cols-2 gap-3">
              <div className="card p-3">
                <p className="text-xs text-slate-500">Riesgo de fuga</p>
                <p className={`text-lg font-semibold ${detalle.data.riesgo_alto ? 'text-danger' : 'text-slate-200'}`}>
                  {pct(detalle.data.probabilidad_abandono)}
                </p>
              </div>
              <div className="card p-3">
                <p className="text-xs text-slate-500">Segmento RFM</p>
                <p className="text-lg font-semibold text-slate-200">{detalle.data.nombre_segmento}</p>
              </div>
            </div>

            <div>
              <p className="text-xs font-semibold uppercase tracking-widest text-slate-500 mb-2">Productos recomendados</p>
              <ul className="space-y-1">
                {detalle.data.productos_recomendados.map((p) => (
                  <li key={p.producto_cod} className="text-sm text-slate-300 flex justify-between">
                    <span>{p.producto_cod}</span>
                    <span className="text-slate-500">{pct(p.score * 100)}</span>
                  </li>
                ))}
              </ul>
            </div>

            <div>
              <p className="text-xs font-semibold uppercase tracking-widest text-slate-500 mb-2">Registrar gestión</p>
              <div className="flex gap-2">
                <Button size="sm" variant="ghost" icon={<PhoneCall size={14} />} onClick={() => registrar('contactado')} disabled={gestion.loading}>
                  Contactado
                </Button>
                <Button size="sm" variant="primary" onClick={() => registrar('recompro')} disabled={gestion.loading}>
                  Recompró
                </Button>
                <Button size="sm" variant="danger" onClick={() => registrar('perdido')} disabled={gestion.loading}>
                  Perdido
                </Button>
              </div>
            </div>
          </div>
        ) : null}
      </Drawer>
    </div>
  );
};
