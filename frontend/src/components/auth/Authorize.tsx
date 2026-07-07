import { useAuthStore, type Role } from '../../store/authStore';

interface AuthorizeProps {
  allowedRoles: Role[];
  children: React.ReactNode;
  fallback?: React.ReactNode;
}

/**
 * Renders children only when the current user's role is in allowedRoles.
 * This is a client-side display guard — backend remains the source of truth.
 */
export const Authorize = ({ allowedRoles, children, fallback = null }: AuthorizeProps) => {
  const { user } = useAuthStore();
  if (!user || !allowedRoles.includes(user.role)) return <>{fallback}</>;
  return <>{children}</>;
};
