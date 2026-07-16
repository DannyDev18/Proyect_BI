import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Lock, User, ArrowRight, ShieldAlert } from 'lucide-react';
import { useAuthStore } from '../store/authStore';
import { authLogin, getMe } from '../services/auth';
import { Button } from '../components/ui/Button';
import { Input } from '../components/ui/Input';
import { FormField } from '../components/ui/FormField';

export const Login = () => {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  const login = useAuthStore(state => state.login);
  const navigate = useNavigate();

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!username || !password) {
      setError('Completa usuario y contraseña para continuar.');
      return;
    }

    setLoading(true);
    setError('');

    try {
      // 1. Obtener Token
      const resToken = await authLogin(username, password);
      const token = resToken.data.access_token;

      // Setup axios to have token before getMe (handled by Zustand or manual temporarily if not fast enough)
      localStorage.setItem('auth_token', token);

      // 2. Obtener Info del Uusario
      const resMe = await getMe();
      const me = resMe.data;

      login({
        id: me.id,
        name: me.nombre,
        email: me.email,
        role: me.role.nombre,
        sucursalId: me.sucursal
      }, token);

      navigate('/');
    } catch (err: any) {
      console.error(err);
      setError(err.response?.data?.detail || 'Usuario o contraseña incorrectos. Verifica tus datos e intenta de nuevo.');
      localStorage.removeItem('auth_token');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-bg-base flex font-sans">
      {/* Panel "instrumento en vivo" (F6, §2.5) — el riesgo estético del refactor se
          gasta aquí: visualización ambiental abstracta con los tokens del sistema,
          congelada bajo prefers-reduced-motion, oculta en móvil. */}
      <div className="hidden lg:flex lg:w-[45%] xl:w-1/2 relative overflow-hidden border-r border-border bg-bg-sidebar">
        <div
          className="absolute inset-0 opacity-40"
          style={{
            backgroundImage:
              'linear-gradient(var(--color-border) 1px, transparent 1px), linear-gradient(90deg, var(--color-border) 1px, transparent 1px)',
            backgroundSize: '40px 40px',
          }}
          aria-hidden="true"
        />
        <div className="absolute inset-0 bg-gradient-to-t from-bg-sidebar via-transparent to-bg-sidebar" aria-hidden="true" />

        <div className="relative z-10 flex flex-col justify-between p-12 xl:p-16 w-full">
          <div className="flex items-center gap-3">
            <span className="relative flex-shrink-0 w-2.5 h-2.5 rounded-full bg-gradient-to-br from-primary to-accent">
              <span className="absolute inset-0 rounded-full bg-primary animate-pulse-slow" />
            </span>
            <span className="font-display font-semibold tracking-tight text-text-primary text-xl">Signal Deck</span>
          </div>

          <div aria-hidden="true">
            <svg viewBox="0 0 400 120" className="w-full max-w-md" preserveAspectRatio="none">
              <polyline
                points="0,60 40,60 55,20 70,100 85,40 100,60 400,60"
                fill="none"
                stroke="var(--color-info)"
                strokeWidth="1.5"
                strokeLinejoin="round"
                strokeLinecap="round"
                strokeDasharray="6 10"
                className="animate-scope-scan animate-scope-glow"
              />
            </svg>
          </div>

          <div className="max-w-sm">
            <p className="text-text-primary font-medium leading-relaxed">
              Inteligencia comercial en tiempo real sobre el Data Warehouse.
            </p>
            <p className="text-sm text-slate-500 mt-2 leading-relaxed">
              Predicción de ventas, segmentación de clientes, metas y comisiones — datos reales del EDW y modelos ML en un solo tablero por rol.
            </p>
          </div>
        </div>
      </div>

      {/* Panel de formulario */}
      <div className="flex-1 flex items-center justify-center relative p-6 sm:p-10">
        <div className="w-full max-w-md relative z-10">
          <div className="lg:hidden flex items-center justify-center gap-2.5 mb-8 animate-fade-in-up">
            <span className="relative flex-shrink-0 w-2 h-2 rounded-full bg-gradient-to-br from-primary to-accent">
              <span className="absolute inset-0 rounded-full bg-primary animate-pulse-slow" />
            </span>
            <span className="font-display font-semibold tracking-tight text-text-primary text-lg">Signal Deck</span>
          </div>

          <div className="animate-fade-in-up" style={{ animationDelay: '80ms' }}>
            <h1 className="text-2xl font-display font-semibold text-slate-100 mb-2">
              Ingresa a tu tablero
            </h1>
            <p className="text-sm text-slate-500 mb-8 font-medium">
              Analítica empresarial y predicción de ventas multisucursal
            </p>
          </div>

          {error && (
            <div role="alert" className="mb-6 p-4 rounded-lg bg-danger/10 border border-danger/20 text-danger text-sm flex items-center animate-fade-in">
              <ShieldAlert size={16} className="mr-2 shrink-0" />
              {error}
            </div>
          )}

          <form onSubmit={handleLogin} className="space-y-5 animate-fade-in-up" style={{ animationDelay: '160ms' }}>
            <FormField label="Usuario / Email" htmlFor="login-username">
              <Input
                id="login-username"
                type="text"
                autoComplete="username"
                autoFocus
                iconLeft={<User size={18} />}
                placeholder="usuario@empresa.com"
                value={username}
                onChange={e => setUsername(e.target.value)}
              />
            </FormField>

            <FormField label="Contraseña" htmlFor="login-password">
              <Input
                id="login-password"
                type="password"
                autoComplete="current-password"
                iconLeft={<Lock size={18} />}
                placeholder="••••••••"
                value={password}
                onChange={e => setPassword(e.target.value)}
              />
            </FormField>

            <Button
              type="submit"
              variant="primary"
              size="lg"
              loading={loading}
              className="w-full mt-4 glow-accent-sm"
              icon={!loading ? <ArrowRight size={18} /> : undefined}
            >
              {loading ? 'Autenticando…' : 'Ingresar al sistema'}
            </Button>
          </form>

          <p className="text-center text-[11px] text-slate-600 mt-8 animate-fade-in-up" style={{ animationDelay: '240ms' }}>
            Plataforma Inteligente de Analítica Empresarial
          </p>
        </div>
      </div>
    </div>
  );
};
