import { useState } from 'react';
import { Button } from '../ui/Button';
import { FormField } from '../ui/FormField';
import { Select } from '../ui/Select';
import { DateField } from '../ui/DateField';
import { useRegistrarGestionRuta } from '../../hooks/cartera360';
import type { CanalGestion, EventoGestionRuta } from '../../types/cartera360';

const EVENTOS: { value: EventoGestionRuta; label: string }[] = [
  { value: 'contactado', label: 'Contactado' },
  { value: 'recompro', label: 'Recompró' },
  { value: 'perdido', label: 'Perdido' },
  { value: 'no_contesto', label: 'No contestó' },
  { value: 'reagendado', label: 'Reagendado' },
  { value: 'interesado_sin_cierre', label: 'Interesado, sin cierre' },
  { value: 'objecion_precio', label: 'Objeción de precio' },
  { value: 'objecion_stock', label: 'Objeción de stock' },
];

const CANALES: { value: CanalGestion; label: string }[] = [
  { value: 'llamada', label: 'Llamada' },
  { value: 'whatsapp', label: 'WhatsApp' },
  { value: 'email', label: 'Email' },
  { value: 'visita', label: 'Visita' },
];

interface QuickLogFormProps {
  clienteId: string;
  onSuccess: () => void;
}

/** Registro de gestión de 1 clic (§4.7, DEC-2: sin react-hook-form/zod -- 4 campos no
 * lo justifican). El canal SÍ se captura aunque DEC-4C descarta *recomendarlo*: es la
 * dimensión del panel de Efectividad Comercial (§4.8). */
export const QuickLogForm = ({ clienteId, onSuccess }: QuickLogFormProps) => {
  const [evento, setEvento] = useState<EventoGestionRuta>('contactado');
  const [canal, setCanal] = useState<CanalGestion | ''>('');
  const [proximaAccionFecha, setProximaAccionFecha] = useState('');
  const [nota, setNota] = useState('');
  const { execute, loading, error, isSuccess, reset } = useRegistrarGestionRuta(clienteId);

  const submit = () => {
    execute(
      {
        cliente_id: clienteId,
        evento,
        canal: canal || null,
        proxima_accion_fecha: proximaAccionFecha || null,
        nota: nota || null,
      },
      {
        onSuccess: () => {
          setNota('');
          setProximaAccionFecha('');
          onSuccess();
        },
      },
    );
  };

  return (
    <div className="space-y-4">
      <FormField label="Resultado de la gestión" htmlFor="qlf-evento" required>
        <Select id="qlf-evento" value={evento} onChange={(e) => { reset(); setEvento(e.target.value as EventoGestionRuta); }}>
          {EVENTOS.map((ev) => <option key={ev.value} value={ev.value}>{ev.label}</option>)}
        </Select>
      </FormField>

      <FormField label="Canal" htmlFor="qlf-canal" helper="Se usa para medir efectividad por canal, no se recomienda uno.">
        <Select id="qlf-canal" value={canal} onChange={(e) => setCanal(e.target.value as CanalGestion | '')}>
          <option value="">Sin especificar</option>
          {CANALES.map((c) => <option key={c.value} value={c.value}>{c.label}</option>)}
        </Select>
      </FormField>

      <FormField label="Próxima acción (fecha)" htmlFor="qlf-fecha">
        <DateField
          id="qlf-fecha" className="w-full"
          value={proximaAccionFecha} onChange={(e) => setProximaAccionFecha(e.target.value)}
        />
      </FormField>

      <FormField label="Nota" htmlFor="qlf-nota">
        <textarea
          id="qlf-nota" className="input-field w-full" rows={3}
          value={nota} onChange={(e) => setNota(e.target.value)}
          placeholder="Detalle opcional de la conversación..."
        />
      </FormField>

      {error && <p className="text-xs text-danger">{error}</p>}
      {isSuccess && <p className="text-xs text-success">Gestión registrada.</p>}

      <Button variant="primary" onClick={submit} loading={loading} className="w-full">
        Registrar gestión
      </Button>
    </div>
  );
};
