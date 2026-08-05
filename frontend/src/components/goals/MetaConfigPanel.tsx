import { useState } from 'react';
import { SlidersHorizontal, ChevronDown, ChevronUp } from 'lucide-react';

import {
  useMetaConfigCatalogo, useMetaConfigModulos, useUpdateMetaConfigModulo,
} from '../../hooks/goals';
import type { MetaConfigModulo, MetaConfigModuloParametro } from '../../types/goals';
import { Button } from '../ui/Button';
import { Badge } from '../ui/Badge';
import { useToast } from '../../store/toastStore';
import { getApiErrorMessage } from '../../utils/apiError';

/** Fórmula de metas -- motor v3 modular (docs/features/plan_motor_metas_v3_y_comisiones_
 * unificadas.md §9/§18, Fase 6): una tarjeta por etapa del pipeline de 14 etapas, con su
 * método (catálogo cerrado -- solo se puede activar un método realmente implementado,
 * nunca uno solo declarado en la arquitectura), su interruptor de activación y un
 * formulario dinámico de parámetros (campo por campo, con su rango real) -- nunca un
 * editor de JSON crudo, petición explícita del usuario ("estos json se deben construir
 * de forma dinamica en el frontend... el usuario no va a entender que es un json"). Los
 * cambios solo afectan a las metas que se generen A PARTIR de ahora -- las ya generadas
 * guardan su propia trazabilidad completa y no se recalculan (mismo principio que
 * Comisiones Variables).
 *
 * La bitácora de cambios de esta configuración vive únicamente en la pantalla "Bitácora
 * de cambios" (BitacoraPanel.tsx) -- ambas leen la MISMA tabla append-only
 * (`public.comision_config_auditoria`, tabla='metas_config_modulos'), así que
 * duplicarla aquí no aportaba información nueva, solo la misma lista dos veces. */
export function MetaConfigPanel() {
  const { data: catalogo, loading: loadingCatalogo } = useMetaConfigCatalogo();
  const { data: modulos, loading: loadingModulos } = useMetaConfigModulos();
  const { update, pendingEtapa } = useUpdateMetaConfigModulo();
  const [expandido, setExpandido] = useState<string | null>(null);
  const toast = useToast();

  const loading = loadingCatalogo || loadingModulos;

  return (
    <div className="space-y-5">
      <div className="p-4 bg-info/30 border border-info/50 rounded-lg text-sm text-slate-300">
        <p className="font-semibold text-info flex items-center gap-2">
          <SlidersHorizontal size={16} aria-hidden="true" /> Fórmula de metas -- motor v3 (pipeline modular)
        </p>
        <p className="mt-1.5">
          Cada etapa se puede activar/desactivar y editar de forma independiente. El orden de
          ejecución es fijo; lo editable es el método y los parámetros de cada etapa. Una
          etapa desactivada por falta de datos muestra la razón. Los cambios solo afectan a
          las metas que se generen a partir de ahora -- cada cambio queda registrado en la
          pestaña "Bitácora de cambios".
        </p>
      </div>

      {loading && <p className="text-sm text-slate-400">Cargando configuración...</p>}

      <div className="space-y-3">
        {modulos.map((modulo) => {
          const info = catalogo[modulo.etapa];
          const abierto = expandido === modulo.etapa;
          return (
            <EtapaCard
              key={modulo.etapa}
              modulo={modulo}
              nombre={info?.nombre ?? modulo.etapa}
              metodos={info?.metodos ?? {}}
              parametrosSchema={info?.parametros ?? []}
              abierto={abierto}
              pendiente={pendingEtapa === modulo.etapa}
              onToggleAbierto={() => setExpandido(abierto ? null : modulo.etapa)}
              onGuardar={async (payload) => {
                try {
                  await update({ etapa: modulo.etapa, ...payload });
                  toast(`Etapa "${info?.nombre ?? modulo.etapa}" actualizada.`, 'success');
                } catch (err) {
                  toast(getApiErrorMessage(err) ?? 'No se pudo actualizar la etapa.', 'error');
                }
              }}
            />
          );
        })}
      </div>
    </div>
  );
}

interface EtapaCardProps {
  modulo: MetaConfigModulo;
  nombre: string;
  metodos: Record<string, { implementado: boolean; descripcion: string; motivo: string | null }>;
  parametrosSchema: MetaConfigModuloParametro[];
  abierto: boolean;
  pendiente: boolean;
  onToggleAbierto: () => void;
  onGuardar: (payload: { metodo: string | null; activo: boolean; parametros: Record<string, unknown> }) => void;
}

function EtapaCard({
  modulo, nombre, metodos, parametrosSchema, abierto, pendiente, onToggleAbierto, onGuardar,
}: EtapaCardProps) {
  const [metodo, setMetodo] = useState(modulo.metodo ?? '');
  const [activo, setActivo] = useState(modulo.activo);
  const [parametros, setParametros] = useState<Record<string, number>>(() => {
    const inicial: Record<string, number> = {};
    for (const p of parametrosSchema) {
      const valorGuardado = modulo.parametros[p.clave];
      inicial[p.clave] = typeof valorGuardado === 'number' ? valorGuardado : p.default;
    }
    return inicial;
  });

  const hayCambios =
    metodo !== (modulo.metodo ?? '') ||
    activo !== modulo.activo ||
    parametrosSchema.some((p) => parametros[p.clave] !== (typeof modulo.parametros[p.clave] === 'number' ? modulo.parametros[p.clave] : p.default));

  const handleGuardar = () => {
    // Se conservan también las claves no numéricas ya guardadas (ej. E3 `prioridad`,
    // una lista, no un campo de formulario) -- el formulario dinámico solo controla los
    // parámetros numéricos declarados en el catálogo.
    onGuardar({ metodo: metodo || null, activo, parametros: { ...modulo.parametros, ...parametros } });
  };

  return (
    <div className="bg-slate-800/50 rounded-lg border border-slate-700/50 overflow-hidden">
      <button
        type="button"
        onClick={onToggleAbierto}
        className="w-full flex items-center justify-between p-3.5 text-left hover:bg-slate-800 focus-ring"
      >
        <div className="flex items-center gap-3">
          <span
            className={`w-2.5 h-2.5 rounded-full ${modulo.activo ? 'bg-success' : 'bg-slate-600'}`}
            aria-hidden="true"
          />
          <div>
            <p className="font-semibold text-slate-200">{nombre}</p>
            <p className="text-xs text-slate-500">
              {modulo.activo ? `Activa · ${metodos[modulo.metodo ?? '']?.descripcion ?? modulo.metodo ?? 'sin método'}` : (modulo.razon_desactivacion ?? 'Desactivada')}
            </p>
          </div>
        </div>
        {abierto ? <ChevronUp size={16} aria-hidden="true" /> : <ChevronDown size={16} aria-hidden="true" />}
      </button>

      {abierto && (
        <div className="p-4 border-t border-slate-700/50 space-y-4">
          <label className="flex items-center gap-2 text-sm text-slate-300">
            <input type="checkbox" checked={activo} onChange={(e) => setActivo(e.target.checked)} className="focus-ring" />
            Etapa activa
          </label>

          {Object.keys(metodos).length > 0 && (
            <div>
              <label htmlFor={`metodo-${modulo.etapa}`} className="block text-xs text-slate-400 mb-1">Método</label>
              <select
                id={`metodo-${modulo.etapa}`}
                value={metodo}
                onChange={(e) => setMetodo(e.target.value)}
                className="bg-slate-900 w-full p-2 rounded border border-slate-700 focus-ring text-sm"
              >
                <option value="">-- ninguno --</option>
                {Object.entries(metodos).map(([clave, m]) => (
                  <option key={clave} value={clave} disabled={!m.implementado}>
                    {clave}{!m.implementado ? ' (no disponible todavía)' : ''}
                  </option>
                ))}
              </select>
              {metodo && metodos[metodo] && (
                <p className="text-xs text-slate-500 mt-1">
                  {metodos[metodo].descripcion}
                  {metodos[metodo].motivo && <span className="text-warning"> -- {metodos[metodo].motivo}</span>}
                </p>
              )}
            </div>
          )}

          {parametrosSchema.length > 0 && (
            <div className="space-y-3">
              {parametrosSchema.map((p) => (
                <div key={p.clave}>
                  <div className="flex items-center justify-between mb-1">
                    <label htmlFor={`param-${modulo.etapa}-${p.clave}`} className="text-xs text-slate-400">{p.label}</label>
                    <span className="text-xs font-mono text-slate-300">{parametros[p.clave]}</span>
                  </div>
                  <input
                    id={`param-${modulo.etapa}-${p.clave}`}
                    type="range"
                    min={p.min}
                    max={p.max}
                    step={p.paso}
                    value={parametros[p.clave]}
                    onChange={(e) => {
                      const valor = p.tipo === 'int' ? Math.round(Number(e.target.value)) : Number(e.target.value);
                      setParametros((prev) => ({ ...prev, [p.clave]: valor }));
                    }}
                    className="w-full h-2 bg-slate-900 rounded-lg appearance-none cursor-pointer accent-teal-400 focus-ring"
                  />
                  <div className="flex justify-between text-[10px] text-slate-600">
                    <span>{p.min}</span>
                    <span>{p.max}</span>
                  </div>
                </div>
              ))}
            </div>
          )}

          {modulo.razon_desactivacion && !activo && (
            <div className="text-xs text-slate-500 bg-slate-900/60 rounded p-2">
              <Badge variant="neutral">Sin datos</Badge> {modulo.razon_desactivacion}
            </div>
          )}

          <div className="flex justify-end">
            <Button variant="secondary" size="sm" loading={pendiente} disabled={!hayCambios} onClick={handleGuardar}>
              Guardar
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}
