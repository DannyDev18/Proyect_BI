import { Search, X } from 'lucide-react';
import { useState } from 'react';

interface SearchInputProps {
  placeholder?: string;
  onSearch: (value: string) => void;
  loading?: boolean;
  label?: string;
}

export const SearchInput = ({
  placeholder = 'Buscar…',
  onSearch,
  loading = false,
  label,
}: SearchInputProps) => {
  const [value, setValue] = useState('');

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (value.trim()) onSearch(value.trim());
  };

  const handleClear = () => {
    setValue('');
  };

  return (
    <form onSubmit={handleSubmit} className="w-full">
      {label && <label className="text-xs uppercase tracking-widest text-slate-500 font-semibold mb-2 block">{label}</label>}
      <div className="flex gap-2">
        <div className="relative flex-1">
          <Search size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-500 pointer-events-none" />
          <input
            value={value}
            onChange={(e) => setValue(e.target.value)}
            placeholder={placeholder}
            className="w-full bg-slate-900 border border-slate-700 rounded-lg pl-9 pr-8 py-2.5 text-sm text-slate-200 placeholder-slate-600 focus:outline-none focus:border-cyan-500/50 focus:ring-1 focus:ring-cyan-500/20 transition-all"
          />
          {value && (
            <button
              type="button"
              onClick={handleClear}
              className="absolute right-2.5 top-1/2 -translate-y-1/2 text-slate-500 hover:text-slate-300 transition-colors"
            >
              <X size={13} />
            </button>
          )}
        </div>
        <button
          type="submit"
          disabled={loading || !value.trim()}
          className="px-4 py-2.5 bg-cyan-600 hover:bg-cyan-500 disabled:opacity-40 disabled:cursor-not-allowed text-white text-sm font-semibold rounded-lg transition-colors glow-accent-sm"
        >
          {loading ? '…' : 'Buscar'}
        </button>
      </div>
    </form>
  );
};
