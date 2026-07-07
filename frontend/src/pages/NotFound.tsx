import { SearchX } from 'lucide-react';
import { Link } from 'react-router-dom';

export const NotFound = () => {
  return (
    <div className="flex flex-col items-center justify-center h-full min-h-[60vh] relative z-10 w-full text-center">
      <div className="w-24 h-24 rounded-2xl bg-blue-500/10 border border-blue-500/20 flex items-center justify-center mb-8 shadow-[0_0_30px_rgba(59,130,246,0.15)] relative">
        <SearchX size={48} className="text-blue-500" />
      </div>
      <h1 className="text-4xl font-display font-bold text-slate-100 mb-4 tracking-tight">404 - Not Found</h1>
      <p className="text-slate-400 max-w-md mb-10 text-lg">
        La sección que estás buscando no existe o fue movida.
      </p>
      
      <Link 
        to="/" 
        className="px-6 py-3 bg-blue-600 hover:bg-blue-500 text-white rounded-lg shadow-[0_0_20px_rgba(59,130,246,0.3)] transition-all font-medium border border-blue-500/50 flex items-center"
      >
        Volver al Dashboard
      </Link>
    </div>
  );
};
