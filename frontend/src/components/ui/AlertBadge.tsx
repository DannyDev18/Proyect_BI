import { Badge } from './Badge';

interface AlertBadgeProps {
  variant: 'critical' | 'warning' | 'info' | 'success' | 'neutral';
  children: React.ReactNode;
  className?: string;
  dot?: boolean;
}

/** @deprecated usar <Badge /> (components/ui/Badge.tsx) — se retira en F6. */
export const AlertBadge = ({ variant, children, className = '', dot = false }: AlertBadgeProps) => (
  <Badge variant={variant === 'critical' ? 'danger' : variant} className={className} dot={dot}>
    {children}
  </Badge>
);
