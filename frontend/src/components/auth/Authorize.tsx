import { useAuthStore, type Role } from '../../store/authStore';
import { canAccess, type RouteKey } from '../../constants/permissions';

type AuthorizeProps = {
  children: React.ReactNode;
  fallback?: React.ReactNode;
} & ({ allowedRoles: Role[]; routeKey?: never } | { routeKey: RouteKey; allowedRoles?: never });

/**
 * Renders children only when the current user's role is authorized — either via an
 * explicit allowedRoles list (one-off cases), or via routeKey (mirrors an existing
 * route's permissions from constants/permissions.ts, preferred when applicable).
 * This is a client-side display guard — backend remains the source of truth.
 */
export const Authorize = ({ allowedRoles, routeKey, children, fallback = null }: AuthorizeProps) => {
  const { user } = useAuthStore();
  if (!user) return <>{fallback}</>;

  const authorized = routeKey ? canAccess(user.role, routeKey) : allowedRoles.includes(user.role);
  if (!authorized) return <>{fallback}</>;

  return <>{children}</>;
};
