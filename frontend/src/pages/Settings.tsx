import { useState } from 'react';
import { Settings as SettingsIcon, Shield, Bell, Palette } from 'lucide-react';
import { useAuthStore } from '../store/authStore';
import { Button } from '../components/ui/Button';
import { useToast } from '../store/toastStore';

const SECTIONS = [
  { key: 'perfil', label: 'Perfil', icon: Shield },
  { key: 'notificaciones', label: 'Notificaciones', icon: Bell },
  { key: 'apariencia', label: 'Apariencia', icon: Palette },
] as const;

export const Settings = () => {
  const { user } = useAuthStore();
  const [section, setSection] = useState<(typeof SECTIONS)[number]['key']>('perfil');
  const toast = useToast();

  const handleSave = () => {
    toast('Cambios guardados correctamente.', 'success');
  };

  return (
    <div className="space-y-6 max-w-4xl">
      <div>
        <h1 className="text-3xl font-display font-semibold">Configuración general</h1>
        <p className="text-slate-400 mt-1">Ajustes de cuenta y preferencias del sistema</p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-4 gap-6">
        <nav className="col-span-1 border-r border-slate-800 pr-4 space-y-2" aria-label="Secciones de configuración">
          {SECTIONS.map(({ key, label, icon: Icon }) => (
            <button
              key={key}
              type="button"
              onClick={() => setSection(key)}
              aria-current={section === key}
              className={`w-full text-left px-4 py-2 rounded-lg font-medium flex items-center transition-colors focus-ring cursor-pointer ${
                section === key
                  ? 'bg-cyan-500/10 text-cyan-400 border border-cyan-500/20'
                  : 'border border-transparent hover:bg-slate-800/50 text-slate-400 hover:text-slate-200'
              }`}
            >
              <Icon size={18} className="mr-3" /> {label}
            </button>
          ))}
        </nav>

        <div className="col-span-3 card p-6">
          {section === 'perfil' && (
            <>
              <h3 className="text-lg font-sans font-semibold text-slate-200 mb-6 flex items-center border-b border-slate-800 pb-4">
                <SettingsIcon className="mr-3 text-slate-400" aria-hidden="true" /> Detalles de la cuenta
              </h3>

              <div className="space-y-4">
                <div>
                  <label htmlFor="settings-nombre" className="block text-xs font-semibold uppercase tracking-wider text-slate-500 mb-2">Nombre completo</label>
                  <input
                    id="settings-nombre" type="text" disabled
                    value={user?.name || ''}
                    className="w-full px-4 py-2 bg-slate-950 border border-slate-800 rounded-lg text-slate-400 outline-none cursor-not-allowed"
                  />
                </div>
                <div>
                  <label htmlFor="settings-email" className="block text-xs font-semibold uppercase tracking-wider text-slate-500 mb-2">Correo electrónico</label>
                  <input
                    id="settings-email" type="email" disabled
                    value={user?.email || ''}
                    className="w-full px-4 py-2 bg-slate-950 border border-slate-800 rounded-lg text-slate-400 outline-none cursor-not-allowed"
                  />
                </div>
                <div>
                  <label htmlFor="settings-rol" className="block text-xs font-semibold uppercase tracking-wider text-slate-500 mb-2">Rol asignado</label>
                  <input
                    id="settings-rol" type="text" disabled
                    value={(user?.role || '').toUpperCase()}
                    className="w-full px-4 py-2 bg-slate-950 border border-slate-800 rounded-lg text-slate-400 outline-none cursor-not-allowed font-mono"
                  />
                </div>
              </div>

              <div className="mt-8 flex justify-end">
                <Button variant="primary" onClick={handleSave}>Guardar cambios</Button>
              </div>
            </>
          )}

          {section === 'notificaciones' && (
            <div className="text-sm text-slate-500">
              Las preferencias de notificaciones aún no están disponibles para este rol.
            </div>
          )}

          {section === 'apariencia' && (
            <div className="text-sm text-slate-500">
              El tema Signal Deck (consola oscura) es el único disponible por ahora.
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
