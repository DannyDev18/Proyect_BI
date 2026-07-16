import { forwardRef, type InputHTMLAttributes, type ReactNode } from 'react';

interface InputProps extends InputHTMLAttributes<HTMLInputElement> {
  state?: 'default' | 'error' | 'success';
  iconLeft?: ReactNode;
  iconRight?: ReactNode;
}

const stateClasses: Record<NonNullable<InputProps['state']>, string> = {
  default: '',
  error: 'border-danger/60 focus-visible:shadow-[0_0_0_2px_var(--color-bg-base),0_0_0_4px_rgb(239_68_68_/_0.4)]',
  success: 'border-success/60',
};

/** Input base del sistema (F4, D-7): mismo lenguaje visual que `Select`/`.input-field`,
 * con soporte de icono izquierdo/derecho y estado de validación. Se compone con
 * `FormField` para label + helper/error. */
export const Input = forwardRef<HTMLInputElement, InputProps>(
  ({ state = 'default', iconLeft, iconRight, className = '', ...rest }, ref) => (
    <div className="relative">
      {iconLeft && (
        <span className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none text-slate-500">
          {iconLeft}
        </span>
      )}
      <input
        ref={ref}
        className={`input-field w-full ${iconLeft ? 'pl-10' : ''} ${iconRight ? 'pr-10' : ''} ${stateClasses[state]} ${className}`}
        {...rest}
      />
      {iconRight && (
        <span className="absolute inset-y-0 right-0 pr-3 flex items-center text-slate-500">
          {iconRight}
        </span>
      )}
    </div>
  ),
);
Input.displayName = 'Input';
