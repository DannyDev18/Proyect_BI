export const LoadingSpinner = ({ size = 'md', label }: { size?: 'sm' | 'md' | 'lg'; label?: string }) => {
  const sz = { sm: 'h-5 w-5', md: 'h-8 w-8', lg: 'h-12 w-12' };
  return (
    <div className="flex flex-col items-center justify-center gap-3">
      <svg
        className={`${sz[size]} animate-spin text-primary`}
        xmlns="http://www.w3.org/2000/svg"
        fill="none"
        viewBox="0 0 24 24"
      >
        <circle className="opacity-20" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="3" />
        <path className="opacity-80" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
      </svg>
      {label && <p className="text-xs text-slate-500 font-medium">{label}</p>}
    </div>
  );
};

export const FullPageSpinner = () => (
  <div className="flex h-64 w-full items-center justify-center">
    <LoadingSpinner size="lg" label="Cargando datos…" />
  </div>
);
