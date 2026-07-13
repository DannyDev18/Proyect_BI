interface TabItem {
  value: string;
  label: string;
}

interface TabsProps {
  items: TabItem[];
  value: string;
  onChange: (value: string) => void;
  className?: string;
}

/** Vistas alternas dentro de una card (P2) — subrayado que se desliza, no reaparece.
 * Uso: <Tabs items={[{value:'recomendados',label:'Recomendados'}, ...]} value={tab} onChange={setTab} /> */
export const Tabs = ({ items, value, onChange, className = '' }: TabsProps) => (
  <div role="tablist" className={`relative flex gap-1 border-b border-slate-800 ${className}`}>
    {items.map((item) => {
      const active = item.value === value;
      return (
        <button
          key={item.value}
          type="button"
          role="tab"
          aria-selected={active}
          onClick={() => onChange(item.value)}
          className={`relative px-4 py-2.5 text-sm font-medium transition-colors duration-150 focus-ring cursor-pointer ${
            active ? 'text-cyan-400' : 'text-slate-500 hover:text-slate-300'
          }`}
        >
          {item.label}
          {active && (
            <span className="absolute left-0 right-0 -bottom-px h-0.5 bg-cyan-400 rounded-full animate-tab-indicator" />
          )}
        </button>
      );
    })}
  </div>
);
