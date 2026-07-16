import type { ReactNode } from 'react';

interface FormFieldProps {
  label: string;
  htmlFor: string;
  error?: string;
  helper?: string;
  required?: boolean;
  className?: string;
  children: ReactNode;
}

/** Composición label + control + helper/error (F4, D-7). El control (`Input`/`Select`)
 * debe recibir `id={htmlFor}` y, si aplica, `aria-invalid`/`aria-describedby` apuntando
 * a los ids que expone este componente (`${htmlFor}-error` / `${htmlFor}-helper`). */
export const FormField = ({ label, htmlFor, error, helper, required = false, className = '', children }: FormFieldProps) => (
  <div className={`space-y-1.5 ${className}`}>
    <label htmlFor={htmlFor} className="block text-xs font-semibold uppercase tracking-wider text-slate-500">
      {label}
      {required && <span className="text-danger ml-0.5" aria-hidden="true">*</span>}
    </label>
    {children}
    {error ? (
      <p id={`${htmlFor}-error`} role="alert" className="text-xs text-danger">{error}</p>
    ) : helper ? (
      <p id={`${htmlFor}-helper`} className="text-xs text-slate-500">{helper}</p>
    ) : null}
  </div>
);
