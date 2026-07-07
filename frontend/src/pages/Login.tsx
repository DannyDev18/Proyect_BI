import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Lock, User, ArrowRight, Building2, ShieldAlert } from 'lucide-react';
import { useAuthStore } from '../store/authStore';
import { authLogin, getMe } from '../services/api';

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
      setError('Por favor complete todos los campos');
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
      setError(err.response?.data?.detail || 'Credenciales incorrectas o error en el servidor');
      localStorage.removeItem('auth_token');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-slate-950 flex items-center justify-center relative overflow-hidden font-sans">
      {/* Background Orbs */}
      <div className="absolute top-1/4 left-1/4 w-96 h-96 bg-blue-600/20 rounded-full blur-[120px] pointer-events-none" />
      <div className="absolute bottom-1/4 right-1/4 w-[500px] h-[500px] bg-slate-800/40 rounded-full blur-[150px] pointer-events-none" />

      <div className="w-full max-w-md relative z-10 p-8 sm:p-10 bg-slate-900/50 backdrop-blur-xl rounded-2xl border border-slate-800 shadow-2xl">
        <div className="flex justify-center mb-8">
          <div className="w-16 h-16 rounded-2xl bg-blue-500/10 border border-blue-500/20 flex items-center justify-center shadow-[0_0_15px_rgba(59,130,246,0.15)]">
            <Building2 className="text-blue-500 w-8 h-8" />
          </div>
        </div>
        
        <h2 className="text-2xl font-display font-semibold text-center text-slate-100 mb-2">
          BI Platform
        </h2>
        <p className="text-sm text-center text-slate-400 mb-8 font-medium">
          Ingrese a la Inteligencia Comercial
        </p>

        {error && (
          <div className="mb-6 p-4 rounded-lg bg-red-500/10 border border-red-500/20 text-red-400 text-sm flex items-center">
            <ShieldAlert size={16} className="mr-2" />
            {error}
          </div>
        )}

        <form onSubmit={handleLogin} className="space-y-5">
          <div className="space-y-1">
            <label className="text-xs font-semibold uppercase tracking-wider text-slate-500 ml-1">Usuario / Email</label>
            <div className="relative">
              <div className="absolute inset-y-0 left-0 pl-4 flex items-center pointer-events-none text-slate-500">
                <User size={18} />
              </div>
              <input
                type="text"
                autoComplete="off"
                className="block w-full pl-11 px-4 py-3 bg-slate-950/50 border border-slate-800 rounded-lg text-slate-200 focus:ring-1 focus:ring-blue-500 focus:border-blue-500 transition-colors placeholder-slate-600 outline-none"
                placeholder="usuario@empresa.com"
                value={username}
                onChange={e => setUsername(e.target.value)}
              />
            </div>
          </div>

          <div className="space-y-1">
            <label className="text-xs font-semibold uppercase tracking-wider text-slate-500 ml-1">Contraseña</label>
            <div className="relative">
              <div className="absolute inset-y-0 left-0 pl-4 flex items-center pointer-events-none text-slate-500">
                <Lock size={18} />
              </div>
              <input
                type="password"
                className="block w-full pl-11 px-4 py-3 bg-slate-950/50 border border-slate-800 rounded-lg text-slate-200 focus:ring-1 focus:ring-blue-500 focus:border-blue-500 transition-colors placeholder-slate-600 outline-none"
                placeholder="••••••••"
                value={password}
                onChange={e => setPassword(e.target.value)}
              />
            </div>
          </div>

          <button
            type="submit"
            disabled={loading}
            className="w-full relative group bg-blue-600 hover:bg-blue-500 disabled:bg-blue-800 text-white font-medium py-3 rounded-lg mt-4 transition-all overflow-hidden flex items-center justify-center space-x-2 border border-blue-500/50 shadow-[0_4px_20px_rgba(59,130,246,0.3)]"
          >
            <span className="relative z-10">{loading ? 'Autenticando...' : 'Ingresar al Sistema'}</span>
            {!loading && <ArrowRight size={18} className="relative z-10 group-hover:translate-x-1 transition-transform" />}
          </button>
        </form>
      </div>
    </div>
  );
};
