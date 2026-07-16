import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Lock, User, ArrowRight, Building2, ShieldAlert } from 'lucide-react';
import { useAuthStore } from '../store/authStore';
import { authLogin, getMe } from '../services/auth';
import { Button } from '../components/ui/Button';

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
    <div className="min-h-screen bg-slate-950 flex items-center justify-center relative overflow-hidden font-sans">
      <div className="w-full max-w-md relative z-10 p-8 sm:p-10 bg-slate-900 rounded-2xl border border-slate-800">
        <div className="flex justify-center mb-8 animate-fade-in-up" style={{ animationDelay: '0ms' }}>
          <div className="w-16 h-16 rounded-2xl bg-info/10 border border-info/20 flex items-center justify-center">
            <Building2 className="text-info w-8 h-8" />
          </div>
        </div>

        <div className="animate-fade-in-up" style={{ animationDelay: '80ms' }}>
          <h1 className="text-2xl font-display font-semibold text-center text-slate-100 mb-2">
            BI Platform
          </h1>
          <p className="text-sm text-center text-slate-400 mb-8 font-medium">
            Ingresa a la Inteligencia Comercial
          </p>
        </div>

        {error && (
          <div role="alert" className="mb-6 p-4 rounded-lg bg-danger/10 border border-danger/20 text-danger text-sm flex items-center animate-fade-in">
            <ShieldAlert size={16} className="mr-2 shrink-0" />
            {error}
          </div>
        )}

        <form onSubmit={handleLogin} className="space-y-5 animate-fade-in-up" style={{ animationDelay: '160ms' }}>
          <div className="space-y-1">
            <label htmlFor="login-username" className="text-xs font-semibold uppercase tracking-wider text-slate-500 ml-1">Usuario / Email</label>
            <div className="relative">
              <div className="absolute inset-y-0 left-0 pl-4 flex items-center pointer-events-none text-slate-500">
                <User size={18} />
              </div>
              <input
                id="login-username"
                type="text"
                autoComplete="username"
                autoFocus
                className="block w-full pl-11 px-4 py-3 bg-slate-950/50 border border-slate-800 rounded-lg text-slate-200 transition-colors placeholder-slate-600 outline-none focus-ring"
                placeholder="usuario@empresa.com"
                value={username}
                onChange={e => setUsername(e.target.value)}
              />
            </div>
          </div>

          <div className="space-y-1">
            <label htmlFor="login-password" className="text-xs font-semibold uppercase tracking-wider text-slate-500 ml-1">Contraseña</label>
            <div className="relative">
              <div className="absolute inset-y-0 left-0 pl-4 flex items-center pointer-events-none text-slate-500">
                <Lock size={18} />
              </div>
              <input
                id="login-password"
                type="password"
                autoComplete="current-password"
                className="block w-full pl-11 px-4 py-3 bg-slate-950/50 border border-slate-800 rounded-lg text-slate-200 transition-colors placeholder-slate-600 outline-none focus-ring"
                placeholder="••••••••"
                value={password}
                onChange={e => setPassword(e.target.value)}
              />
            </div>
          </div>

          <Button
            type="submit"
            variant="primary"
            loading={loading}
            className="w-full mt-4 py-3 shadow-[0_4px_20px_rgba(8,145,178,0.3)]"
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
  );
};
